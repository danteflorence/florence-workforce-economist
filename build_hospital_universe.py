"""
Build the unified hospital universe table from:
  1) CMS Hospital General Information roster (5,432 Medicare-registered facilities)
  2) CommonSpirit demo dataset (136 facilities with real staff/agency rates)
  3) HCRIS Hospital Provider Cost Report 2023 (~5,867 hospitals with FTE,
     salaries, wage-related costs, contract labor)
  4) State-level RN mean hourly wage benchmarks (placeholder; BLS OEWS May 2024)
  5) State-level agency-rate benchmarks (derived from CommonSpirit + imputed)

Output: hospital_universe.csv with one row per hospital. Key fields:
  ccn, name, city, state, county, hospital_type, ownership,
  taxable_wage_per_hour, benefit_load_per_hour, loaded_staff_cost_per_hour,
  all_in_agency_per_hour, agency_premium_per_hour,
  estimated_rn_need_fte, contract_labor_dollars, contract_labor_intensity,
  operating_margin, data_source, confidence

Confidence is now layered:
  1.00 — CommonSpirit direct match (real customer-disclosed/HCRIS-derived)
  0.85 — HCRIS-derived W/B/RN-need + state-imputed agency rate
  0.60 — state-level imputation (CommonSpirit anchor available for state)
  0.40 — national-median imputation
  0.20 — coarse fallback

HCRIS gives us:
  ✓ Per-hospital salary, benefit-load, FTE, RN-need estimate
  ✓ Contract labor DOLLARS (the targeting signal — high-CL hospitals are
    where Florence creates the most value)
  ✗ Contract labor HOURS (would let us compute per-hospital hourly agency
    rate; not in the aggregated file — see hcris_parser.py docstring)
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
CMS_ROSTER_CSV = DATA_DIR / "cms_hospitals.csv"
HCRIS_METRICS_CSV = DATA_DIR / "hcris_hospital_metrics.csv"
HCRIS_AGENCY_RATES_CSV = DATA_DIR / "hcris_agency_rates.csv"
PER_HOSPITAL_WAGES_CSV = DATA_DIR / "per_hospital_rn_wages.csv"
ZIP_CBSA_CSV = DATA_DIR / "geo" / "zip_cbsa.csv"
HOSPITAL_GEOCODES_CSV = DATA_DIR / "hospital_geocodes.csv"
SYSTEM_OVERLAYS_CSV = DATA_DIR / "system_level_overlays.csv"
DEMO_TS = Path(
    "/Users/dantetolbedantert/florence-work/extracted/florenceos/"
    "supabase/functions/demo-ingest-data-v2/data.ts"
)
OUTPUT_CSV = DATA_DIR / "hospital_universe.csv"
BENCHMARKS_CSV = DATA_DIR / "state_benchmarks.csv"

# ---------------------------------------------------------------------------
# State-level RN mean hourly wage — BLS OEWS May 2024 (placeholder estimates)
# Replace with real BLS ingest in production. These are within ~$2/hr of
# public BLS OEWS values and should not be used for binding quotes.
# ---------------------------------------------------------------------------
STATE_RN_WAGE = {
    "AK": 55.10, "AL": 36.80, "AR": 38.40, "AZ": 47.20, "CA": 65.95,
    "CO": 44.60, "CT": 47.20, "DC": 50.15, "DE": 43.50, "FL": 39.50,
    "GA": 41.30, "HI": 60.45, "IA": 36.95, "ID": 41.40, "IL": 43.75,
    "IN": 37.75, "KS": 36.40, "KY": 38.30, "LA": 39.20, "MA": 53.20,
    "MD": 45.75, "ME": 43.20, "MI": 40.60, "MN": 46.85, "MO": 38.10,
    "MS": 35.45, "MT": 39.80, "NC": 38.80, "ND": 38.95, "NE": 38.45,
    "NH": 44.65, "NJ": 50.95, "NM": 42.75, "NV": 53.10, "NY": 52.85,
    "OH": 40.25, "OK": 39.45, "OR": 53.85, "PA": 42.50, "RI": 47.40,
    "SC": 39.10, "SD": 34.70, "TN": 35.80, "TX": 44.05, "UT": 40.05,
    "VA": 42.40, "VT": 42.95, "WA": 51.85, "WI": 41.70, "WV": 38.35,
    "WY": 38.65,
    # Territories — coarse defaults
    "PR": 22.00, "VI": 30.00, "GU": 32.00, "MP": 25.00, "AS": 22.00,
}
NATIONAL_RN_WAGE = sum(STATE_RN_WAGE.values()) / len(STATE_RN_WAGE)

# Benefit load — assume 30% of taxable wage as non-FICA benefits/PTO/etc.
# Production version pulls this from CMS Worksheet S-3 Part II line ratios.
BENEFIT_LOAD_FRACTION = 0.30

# ---------------------------------------------------------------------------
# Parse the CommonSpirit demo data
# ---------------------------------------------------------------------------

FACILITY_RECORD_RE = re.compile(
    r"\{\s*name:\s*\"([^\"]+)\""
    r",\s*city:\s*\"([^\"]+)\""
    r",\s*state:\s*\"([A-Z]{2})\""
    r",\s*contracted_spend:\s*([\d.\-]+)"
    r",\s*agency_hours:\s*([\d.\-]+)"
    r",\s*staff_cost:\s*([\d.\-]+)"
    r",\s*staff_hours:\s*([\d.\-]+)"
    r",\s*agency_rate:\s*([\d.\-]+)"
    r",\s*staff_rate:\s*([\d.\-]+)"
    r",\s*percentage_premium:\s*([\d.\-]+)"
    r",\s*rn_need_fte:\s*([\d.\-]+)"
    r",\s*per_rn_year_savings:\s*([\d.\-]+)"
    r",\s*savings_3yr:\s*([\d.\-]+)\s*\}"
)


def parse_demo_data() -> pd.DataFrame:
    text = DEMO_TS.read_text()
    rows = []
    for m in FACILITY_RECORD_RE.finditer(text):
        name, city, state, *nums = m.groups()
        (contracted_spend, agency_hours, staff_cost, staff_hours,
         agency_rate, staff_rate, pct_prem, rn_need_fte,
         per_rn_year_savings, savings_3yr) = (float(x) for x in nums)
        rows.append({
            "name_demo": name.upper().strip(),
            "city_demo": city.upper().strip(),
            "state": state,
            "contracted_spend": contracted_spend,
            "agency_hours": agency_hours,
            "staff_cost": staff_cost,
            "staff_hours": staff_hours,
            "agency_rate": agency_rate,           # all-in
            "staff_rate": staff_rate,             # loaded
            "pct_premium": pct_prem,
            "rn_need_fte": rn_need_fte,
            "per_rn_year_savings": per_rn_year_savings,
            "savings_3yr": savings_3yr,
        })
    df = pd.DataFrame(rows)
    print(f"  Parsed {len(df)} demo facilities across {df['state'].nunique()} states.")
    return df


def build_state_benchmarks(demo: pd.DataFrame) -> pd.DataFrame:
    """Median agency / staff rates by state, derived from CommonSpirit demo."""
    agg = demo.groupby("state").agg(
        med_agency_rate=("agency_rate", "median"),
        med_staff_rate=("staff_rate", "median"),
        n_facilities=("agency_rate", "size"),
    ).reset_index()

    # National medians as fallback for non-demo states
    nat_agency = demo["agency_rate"].median()
    nat_staff = demo["staff_rate"].median()
    nat_premium_ratio = nat_agency / nat_staff

    # Build a full 50-state + DC table
    all_states = sorted(set(STATE_RN_WAGE.keys()))
    rows = []
    for st in all_states:
        wage = STATE_RN_WAGE[st]
        if st in agg["state"].values:
            row = agg[agg["state"] == st].iloc[0]
            rows.append({
                "state": st,
                "rn_wage": wage,
                "agency_rate_benchmark": row["med_agency_rate"],
                "staff_rate_benchmark_loaded": row["med_staff_rate"],
                "benchmark_confidence": 0.60,
                "n_facilities_in_demo": int(row["n_facilities"]),
            })
        else:
            # Impute agency rate as state_wage × (national_premium_ratio × benefit_uplift)
            # Loaded staff rate = wage × (1 + benefit_frac + employer FICA)
            loaded_staff = wage * (1 + BENEFIT_LOAD_FRACTION + 0.0765)
            agency_imp = loaded_staff * nat_premium_ratio
            rows.append({
                "state": st,
                "rn_wage": wage,
                "agency_rate_benchmark": round(agency_imp, 2),
                "staff_rate_benchmark_loaded": round(loaded_staff, 2),
                "benchmark_confidence": 0.40,
                "n_facilities_in_demo": 0,
            })
    df = pd.DataFrame(rows)
    df.to_csv(BENCHMARKS_CSV, index=False)
    print(f"  Wrote state benchmarks: {BENCHMARKS_CSV}")
    return df


# ---------------------------------------------------------------------------
# Join CMS roster to demo + state benchmarks
# ---------------------------------------------------------------------------

def load_cms_roster() -> pd.DataFrame:
    df = pd.read_csv(CMS_ROSTER_CSV, dtype=str)
    df = df.rename(columns={
        "Facility ID": "ccn",
        "Facility Name": "name",
        "Address": "address",
        "City/Town": "city",
        "State": "state",
        "ZIP Code": "zip",
        "County/Parish": "county",
        "Hospital Type": "hospital_type",
        "Hospital Ownership": "ownership",
        "Emergency Services": "emergency_services",
        "Hospital overall rating": "cms_rating",
    })
    keep = ["ccn", "name", "address", "city", "state", "zip", "county",
            "hospital_type", "ownership", "emergency_services", "cms_rating"]
    df = df[keep]
    df["name"] = df["name"].str.upper().str.strip()
    df["city"] = df["city"].str.upper().str.strip()
    print(f"  Loaded CMS roster: {len(df):,} hospitals, "
          f"{df['hospital_type'].nunique()} hospital types.")
    return df


def match_to_demo(roster: pd.DataFrame, demo: pd.DataFrame) -> pd.DataFrame:
    """Match CMS hospitals to demo facilities by (state, city, name) where possible."""
    # Best-effort fuzzy match: exact (state, city) + name substring overlap
    demo_keyed = demo.set_index(["state", "city_demo"], drop=False)
    matches = {}
    for _, demo_row in demo.iterrows():
        cand = roster[
            (roster["state"] == demo_row["state"])
            & (roster["city"] == demo_row["city_demo"])
        ]
        if cand.empty:
            continue
        # Try to find a CMS hospital whose name overlaps with the demo name
        for _, cms_row in cand.iterrows():
            demo_tokens = set(demo_row["name_demo"].split())
            cms_tokens = set(cms_row["name"].split())
            # ignore common words
            stop = {"HOSPITAL", "MEDICAL", "CENTER", "HEALTH", "THE", "OF",
                    "AND", "ST.", "ST", "SAINT", "REGIONAL", "MEMORIAL"}
            overlap = (demo_tokens - stop) & (cms_tokens - stop)
            if overlap:
                matches[cms_row["ccn"]] = demo_row.to_dict()
                break
    print(f"  Matched {len(matches)} CMS hospitals to demo data.")
    return matches


def load_hcris_metrics() -> dict:
    """Load HCRIS per-hospital metrics, keyed by CCN (zero-padded to 6)."""
    if not HCRIS_METRICS_CSV.exists():
        print("  HCRIS metrics not found — run hcris_parser.py first.")
        return {}
    df = pd.read_csv(HCRIS_METRICS_CSV, dtype={"ccn": str})
    df["ccn"] = df["ccn"].str.zfill(6)
    by_ccn = df.set_index("ccn").to_dict("index")
    print(f"  Loaded HCRIS aggregated metrics for {len(by_ccn):,} hospitals.")
    return by_ccn


def load_hcris_agency_rates() -> dict:
    """Load HCRIS-NMRC-derived per-hospital agency hourly rates."""
    if not HCRIS_AGENCY_RATES_CSV.exists():
        print("  HCRIS agency rates not found — run hcris_nmrc_parser.py first.")
        return {}
    df = pd.read_csv(HCRIS_AGENCY_RATES_CSV, dtype={"ccn": str})
    df["ccn"] = df["ccn"].str.zfill(6)
    by_ccn = df.set_index("ccn").to_dict("index")
    print(f"  Loaded HCRIS-NMRC agency rates for {len(by_ccn):,} hospitals.")
    return by_ccn


def load_per_hospital_wages() -> dict:
    """Load per-hospital RN wages from the three-tier estimator."""
    if not PER_HOSPITAL_WAGES_CSV.exists():
        print("  Per-hospital wages not found — run wage_estimator.py first.")
        return {}
    df = pd.read_csv(PER_HOSPITAL_WAGES_CSV, dtype={"ccn": str, "cbsa_code": str})
    df["ccn"] = df["ccn"].str.zfill(6)
    by_ccn = df.set_index("ccn").to_dict("index")
    print(f"  Loaded per-hospital RN wages for {len(by_ccn):,} hospitals.")
    return by_ccn


def load_cbsa_crosswalk() -> dict:
    """Load ZIP → CBSA crosswalk."""
    if not ZIP_CBSA_CSV.exists():
        print("  ZIP-CBSA crosswalk not found.")
        return {}
    df = pd.read_csv(ZIP_CBSA_CSV, dtype=str)
    by_zip = df.set_index("zip").to_dict("index")
    print(f"  Loaded ZIP-CBSA crosswalk: {len(by_zip):,} ZIPs.")
    return by_zip


def load_system_overlays() -> dict:
    """Load per-facility MSP-overlay $/hr from system-level fee allocations."""
    if not SYSTEM_OVERLAYS_CSV.exists():
        print("  System-level overlays not found — run system_overlays.py first.")
        return {}
    df = pd.read_csv(SYSTEM_OVERLAYS_CSV, dtype={"ccn": str})
    df["ccn"] = df["ccn"].str.zfill(6)
    by_ccn = df.set_index("ccn").to_dict("index")
    print(f"  Loaded system-level overlays for {len(by_ccn):,} facilities.")
    return by_ccn


def load_geocodes() -> dict:
    """Load lat/lon + health-system inference, keyed by CCN."""
    if not HOSPITAL_GEOCODES_CSV.exists():
        print("  Geocodes not found — run geocode_and_systems.py first.")
        return {}
    df = pd.read_csv(HOSPITAL_GEOCODES_CSV, dtype={"ccn": str})
    df["ccn"] = df["ccn"].str.zfill(6)
    by_ccn = df.set_index("ccn").to_dict("index")
    print(f"  Loaded geocodes + systems for {len(by_ccn):,} hospitals.")
    return by_ccn


def assemble_universe(
    roster: pd.DataFrame,
    demo: pd.DataFrame,
    benchmarks: pd.DataFrame,
    matched: dict,
    hcris: dict,
    geocodes: dict,
    hcris_rates: dict = None,
    per_hospital_wages: dict = None,
    cbsa_crosswalk: dict = None,
    system_overlays: dict = None,
) -> pd.DataFrame:
    bench_by_state = benchmarks.set_index("state").to_dict("index")
    hcris_rates = hcris_rates or {}
    per_hospital_wages = per_hospital_wages or {}
    cbsa_crosswalk = cbsa_crosswalk or {}
    system_overlays = system_overlays or {}

    rows = []
    for _, h in roster.iterrows():
        ccn = str(h["ccn"]).zfill(6)
        state = h["state"]
        zip_code = (h.get("zip") or "")[:5].zfill(5) if h.get("zip") else ""
        bench = bench_by_state.get(state)
        hcris_row = hcris.get(ccn)
        nmrc_rate_row = hcris_rates.get(ccn)
        nmrc_rate = nmrc_rate_row.get("contract_labor_hourly_rate") if nmrc_rate_row else None

        # CBSA crosswalk
        cbsa_row = cbsa_crosswalk.get(zip_code) or {}
        cbsa_code = cbsa_row.get("cbsa_code") or ""
        cbsa_title = cbsa_row.get("cbsa_title") or "Rural / Nonmetro"
        rural_flag = (cbsa_row.get("rural_flag") or "True") == "True"

        # ----- Wage / benefit / loaded-staff cost -----
        # Prefer per-hospital RN wage from wage_estimator (3-tier: HCRIS blended ×
        # multiplier > MSA BLS > state BLS). Falls back to state-level if no row.
        wage_row = per_hospital_wages.get(ccn)
        if wage_row:
            wage = float(wage_row.get("taxable_wage_per_hour") or STATE_RN_WAGE.get(state, NATIONAL_RN_WAGE))
            wage_source = wage_row.get("wage_source", "state_fallback")
            wage_confidence = float(wage_row.get("wage_confidence") or 0.40)
        else:
            wage = STATE_RN_WAGE.get(state, NATIONAL_RN_WAGE)
            wage_source = "state_fallback"
            wage_confidence = 0.40

        if ccn in matched:
            # CommonSpirit direct match — highest confidence for staff cost,
            # but PREFER HCRIS NMRC agency rate over CS state-imputed value
            # if available (HCRIS NMRC is per-hospital real data).
            m = matched[ccn]
            taxable_wage = round(m["staff_rate"] / (1 + BENEFIT_LOAD_FRACTION + 0.0765), 2)
            benefit_load = round(m["staff_rate"] - taxable_wage * 1.0765, 2)
            loaded_staff = m["staff_rate"]
            if nmrc_rate and nmrc_rate > 0:
                agency_rate = round(nmrc_rate, 2)
                source = "commonspirit_staff_hcris_nmrc_agency"
                base_confidence = 0.95
            else:
                agency_rate = m["agency_rate"]
                source = "commonspirit_demo"
                base_confidence = 1.00
            rn_need = m["rn_need_fte"]
        elif hcris_row and bench:
            # HCRIS-derived staff cost. Agency rate: prefer NMRC if available,
            # else state-median fallback.
            taxable_wage = wage
            if pd.notna(hcris_row.get("benefit_load_per_hour")) and hcris_row["benefit_load_per_hour"] > 0:
                hcris_wage = hcris_row.get("taxable_wage_per_hour", 0) or 0
                if hcris_wage > 0:
                    benefit_load = round(
                        hcris_row["benefit_load_per_hour"] * (wage / hcris_wage), 2
                    )
                else:
                    benefit_load = round(wage * BENEFIT_LOAD_FRACTION, 2)
            else:
                benefit_load = round(wage * BENEFIT_LOAD_FRACTION, 2)
            loaded_staff = round(wage + benefit_load + wage * 0.0765, 2)
            if nmrc_rate and nmrc_rate > 0:
                agency_rate = round(nmrc_rate, 2)
                base_confidence = 0.92
                source = "hcris_nmrc_agency_per_hospital"
            else:
                agency_rate = bench["agency_rate_benchmark"]
                base_confidence = 0.85
                source = "hcris_derived_with_state_agency"
            rn_need = hcris_row.get("estimated_rn_need_fte") or estimate_rn_need(h)
        elif nmrc_rate and nmrc_rate > 0:
            # Have NMRC agency rate but no other HCRIS metrics — still high signal
            taxable_wage = wage
            benefit_load = round(wage * BENEFIT_LOAD_FRACTION, 2)
            loaded_staff = round(wage * (1 + BENEFIT_LOAD_FRACTION + 0.0765), 2)
            agency_rate = round(nmrc_rate, 2)
            rn_need = estimate_rn_need(h)
            base_confidence = 0.85
            source = "hcris_nmrc_agency_only"
        elif bench:
            # State-imputed only
            taxable_wage = wage
            benefit_load = round(wage * BENEFIT_LOAD_FRACTION, 2)
            loaded_staff = round(wage * (1 + BENEFIT_LOAD_FRACTION + 0.0765), 2)
            agency_rate = bench["agency_rate_benchmark"]
            rn_need = estimate_rn_need(h)
            base_confidence = bench["benchmark_confidence"]
            source = (
                "state_imputed_with_commonspirit_anchor"
                if bench["n_facilities_in_demo"] > 0
                else "national_imputed"
            )
        else:
            taxable_wage = NATIONAL_RN_WAGE
            benefit_load = round(taxable_wage * BENEFIT_LOAD_FRACTION, 2)
            loaded_staff = round(taxable_wage * (1 + BENEFIT_LOAD_FRACTION + 0.0765), 2)
            agency_rate = round(loaded_staff * 1.70, 2)
            rn_need = estimate_rn_need(h)
            base_confidence = 0.20
            source = "coarse_fallback"

        # HCRIS overlay (always pulled if present; doesn't override CommonSpirit
        # rates but does add the contract-labor and margin signals)
        contract_labor_dollars = None
        contract_labor_intensity = None
        operating_margin = None
        hcris_fte = None
        if hcris_row:
            contract_labor_dollars = hcris_row.get("contract_labor")
            contract_labor_intensity = hcris_row.get("contract_labor_intensity")
            operating_margin = hcris_row.get("operating_margin")
            hcris_fte = hcris_row.get("fte")
            # Bump confidence slightly when HCRIS is also present alongside any
            # other source
            base_confidence = min(1.0, base_confidence + 0.05) \
                if source == "commonspirit_demo" else base_confidence
        confidence = base_confidence

        # Geocode + system pull-through
        geo = geocodes.get(ccn, {})
        # ── System-level MSP overlay (v2 §5.2) ──
        # If this facility belongs to a system with documented additional
        # agency fees (e.g., Kaiser $622M AMN markup not captured in HCRIS),
        # bump the per-hour agency rate by the allocated overlay.
        overlay_row = system_overlays.get(ccn)
        overlay_per_hour = float(overlay_row.get("overlay_per_hour", 0)) if overlay_row else 0.0
        msp_overlay_source = overlay_row.get("overlay_source", "") if overlay_row else ""
        agency_rate_pre_overlay = agency_rate
        if overlay_per_hour > 0:
            agency_rate = round(agency_rate + overlay_per_hour, 2)
            # Lift confidence — this is real disclosed data (e.g. AMN 10-K filings)
            if confidence < 0.95:
                confidence = 0.95
                source = f"{source}+msp_overlay"

        rows.append({
            "ccn": ccn,
            "name": h["name"],
            "city": h["city"],
            "state": state,
            "county": h["county"],
            "hospital_type": h["hospital_type"],
            "ownership": h["ownership"],
            "emergency_services": h["emergency_services"],
            "cms_rating": h["cms_rating"],
            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "health_system": geo.get("health_system") or "Independent / Unknown",
            "health_system_id": geo.get("health_system_id") or "independent",
            "system_confidence": geo.get("system_confidence") or 0.0,
            "taxable_wage_per_hour": taxable_wage,
            "benefit_load_per_hour": benefit_load,
            "loaded_staff_cost_per_hour": loaded_staff,
            "all_in_agency_per_hour": agency_rate,
            "all_in_agency_per_hour_pre_overlay": agency_rate_pre_overlay,
            "msp_overlay_per_hour": overlay_per_hour,
            "msp_overlay_source": msp_overlay_source,
            "agency_premium_per_hour": round(agency_rate - loaded_staff, 2),
            "estimated_rn_need_fte": round(rn_need, 1),
            # HCRIS-derived signals (the targeting columns)
            "contract_labor_dollars": (
                round(contract_labor_dollars, 0)
                if contract_labor_dollars is not None and pd.notna(contract_labor_dollars)
                else None
            ),
            "contract_labor_intensity": (
                round(contract_labor_intensity, 4)
                if contract_labor_intensity is not None and pd.notna(contract_labor_intensity)
                else None
            ),
            "operating_margin": (
                round(operating_margin, 4)
                if operating_margin is not None and pd.notna(operating_margin)
                else None
            ),
            "hcris_total_fte": (
                round(hcris_fte, 0)
                if hcris_fte is not None and pd.notna(hcris_fte)
                else None
            ),
            # CBSA / MSA crosswalk
            "cbsa_code": cbsa_code,
            "cbsa_title": cbsa_title,
            "rural_flag": rural_flag,
            # Wage source tracking (v2 §3)
            "wage_source": wage_source,
            "wage_confidence": wage_confidence,
            "data_source": source,
            "confidence": confidence,
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    return df


def estimate_rn_need(h: pd.Series) -> float:
    """Coarse RN-need-FTE proxy. Production version uses CMS PBJ + HCRIS contract labor."""
    htype = (h.get("hospital_type") or "").lower()
    if "critical access" in htype:
        return 8.0
    if "acute care" in htype:
        # Vague proxy from ownership/type; reality requires PBJ data
        return 30.0
    if "psychiatric" in htype or "rehab" in htype:
        return 12.0
    if "children" in htype:
        return 40.0
    return 15.0


def main() -> None:
    print("Building Florence hospital universe...")
    demo = parse_demo_data()
    benchmarks = build_state_benchmarks(demo)
    roster = load_cms_roster()
    matched = match_to_demo(roster, demo)
    hcris = load_hcris_metrics()
    hcris_rates = load_hcris_agency_rates()
    per_hospital_wages = load_per_hospital_wages()
    cbsa_crosswalk = load_cbsa_crosswalk()
    system_overlays = load_system_overlays()
    geocodes = load_geocodes()
    universe = assemble_universe(
        roster, demo, benchmarks, matched, hcris, geocodes, hcris_rates,
        per_hospital_wages=per_hospital_wages,
        cbsa_crosswalk=cbsa_crosswalk,
        system_overlays=system_overlays,
    )
    print(f"\n  Wrote {OUTPUT_CSV}")
    print(f"  Total hospitals: {len(universe):,}")

    print(f"\n  Confidence distribution:")
    for conf, n in universe["confidence"].value_counts().sort_index(ascending=False).items():
        share = n / len(universe) * 100
        print(f"    conf={conf:.2f}  →  {n:,} hospitals ({share:.1f}%)")

    print(f"\n  Data-source distribution:")
    for src, n in universe["data_source"].value_counts().items():
        print(f"    {src}: {n:,}")

    print(f"\n  HCRIS coverage:")
    has_cl = universe["contract_labor_dollars"].notna().sum()
    has_margin = universe["operating_margin"].notna().sum()
    has_fte = universe["hcris_total_fte"].notna().sum()
    print(f"    Hospitals with HCRIS contract labor reported: {has_cl:,}")
    print(f"    Hospitals with HCRIS operating margin:         {has_margin:,}")
    print(f"    Hospitals with HCRIS FTE:                      {has_fte:,}")

    print(f"\n  Top 20 hospitals by contract labor intensity (targeting list):")
    targets = universe[universe["contract_labor_intensity"].notna()].nlargest(
        20, "contract_labor_intensity"
    )
    for _, r in targets.iterrows():
        cl_m = (r["contract_labor_dollars"] or 0) / 1e6
        print(f"    {r['name'][:45]:45} {r['state']}  "
              f"CL=${cl_m:6.1f}M  share={r['contract_labor_intensity']*100:5.1f}%")


if __name__ == "__main__":
    main()
