"""
Build the v2 §3 market_rate_observations table.

Each rate observation gets its own row with full provenance:
  observation_id, as_of_date, source_type, source_name, source_url_or_file,
  geography, specialty, shift, employment_type,
  hourly_pay, weekly_pay, scheduled_weekly_hours,
  estimated_bill_rate_factor, posting_count,
  confidence_tier  (High / Medium / Directional / Low)

This replaces the flat hospital_universe.csv as the source-of-truth for rates.
The universe builder + pricing engine read from here when pricing.

In production this becomes a Supabase table. For now it's a CSV.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_CSV = DATA_DIR / "market_rate_observations.csv"


def confidence_tier(score: float) -> str:
    if score >= 0.90: return "High"
    if score >= 0.70: return "Medium"
    if score >= 0.50: return "Directional"
    return "Low"


def build_observations() -> pd.DataFrame:
    today = date.today().isoformat()
    obs = []

    # ── HCRIS NMRC contract-labor rates (per-hospital, real) ──
    hcris = pd.read_csv(DATA_DIR / "hcris_agency_rates.csv", dtype={"ccn": str})
    for _, r in hcris.iterrows():
        if pd.notna(r["contract_labor_hourly_rate"]):
            obs.append({
                "observation_id": str(uuid.uuid4()),
                "as_of_date": r["fy_end"],
                "source_type": "hcris_nmrc",
                "source_name": "CMS HCRIS Hospital 2552-10 Worksheet S-3 Part II line 01100",
                "source_url_or_file": "https://downloads.cms.gov/Files/hcris/",
                "geography_type": "ccn",
                "geography": str(r["ccn"]).zfill(6),
                "specialty": "rn_contract_labor_dpc",
                "shift": "blended",
                "employment_type": "contract",
                "hourly_pay": float(r["contract_labor_hourly_rate"]),
                "weekly_pay": None,
                "scheduled_weekly_hours": None,
                "estimated_bill_rate_factor": 1.0,
                "posting_count": None,
                "confidence_score": 0.92,
                "confidence_tier": "High",
                "rate_type": "agency",
            })

    # ── BLS OEWS MSA-level RN wages ──
    wages = pd.read_csv(DATA_DIR / "per_hospital_rn_wages.csv", dtype={"ccn": str, "cbsa_code": str})
    msa_wages = wages[wages["wage_source"] == "bls_oews_msa"].drop_duplicates("cbsa_code")
    for _, r in msa_wages.iterrows():
        obs.append({
            "observation_id": str(uuid.uuid4()),
            "as_of_date": "2024-05-01",
            "source_type": "bls_oews",
            "source_name": "BLS Occupational Employment and Wage Statistics, May 2024",
            "source_url_or_file": "https://www.bls.gov/oes/tables.htm",
            "geography_type": "cbsa",
            "geography": str(r["cbsa_code"]),
            "specialty": "rn_29-1141",
            "shift": "all",
            "employment_type": "staff",
            "hourly_pay": float(r["taxable_wage_per_hour"]),
            "weekly_pay": None,
            "scheduled_weekly_hours": None,
            "estimated_bill_rate_factor": None,
            "posting_count": None,
            "confidence_score": 0.90,
            "confidence_tier": "High",
            "rate_type": "wage",
        })

    # ── State-level BLS placeholders ──
    from wage_estimator import STATE_RN_WAGE
    for state, wage in STATE_RN_WAGE.items():
        obs.append({
            "observation_id": str(uuid.uuid4()),
            "as_of_date": "2024-05-01",
            "source_type": "bls_oews_state_placeholder",
            "source_name": "BLS OEWS May 2024 state-level estimate (hardcoded fallback)",
            "source_url_or_file": "https://www.bls.gov/oes/tables.htm",
            "geography_type": "state",
            "geography": state,
            "specialty": "rn_29-1141",
            "shift": "all",
            "employment_type": "staff",
            "hourly_pay": float(wage),
            "weekly_pay": None,
            "scheduled_weekly_hours": None,
            "estimated_bill_rate_factor": None,
            "posting_count": None,
            "confidence_score": 0.40,
            "confidence_tier": "Low",
            "rate_type": "wage",
        })

    # ── System-level overlays (Kaiser etc.) ──
    overlays_path = DATA_DIR / "system_level_overlays.csv"
    if overlays_path.exists():
        overlays = pd.read_csv(overlays_path, dtype={"ccn": str})
        for _, r in overlays.iterrows():
            obs.append({
                "observation_id": str(uuid.uuid4()),
                "as_of_date": f"{int(r['overlay_as_of_year'])}-12-31",
                "source_type": "system_msp_overlay",
                "source_name": "Health-system-level MSP markup not captured in HCRIS",
                "source_url_or_file": str(r["overlay_source"])[:200],
                "geography_type": "ccn",
                "geography": str(r["ccn"]).zfill(6),
                "specialty": "msp_markup",
                "shift": "all",
                "employment_type": "contract",
                "hourly_pay": float(r["overlay_per_hour"]),
                "weekly_pay": None,
                "scheduled_weekly_hours": None,
                "estimated_bill_rate_factor": None,
                "posting_count": None,
                "confidence_score": 0.95,
                "confidence_tier": "High",
                "rate_type": "agency_overlay",
            })

    # ── CommonSpirit demo anchor data (legacy customer-disclosed-ish) ──
    universe = pd.read_csv(DATA_DIR / "hospital_universe.csv", dtype={"ccn": str})
    cs = universe[universe["data_source"].str.contains("commonspirit_demo", na=False)]
    for _, r in cs.iterrows():
        obs.append({
            "observation_id": str(uuid.uuid4()),
            "as_of_date": "2024-06-30",
            "source_type": "commonspirit_demo",
            "source_name": "CommonSpirit internal facility-level disclosure (seed dataset)",
            "source_url_or_file": "florenceos/supabase/functions/demo-ingest-data-v2",
            "geography_type": "ccn",
            "geography": str(r["ccn"]).zfill(6),
            "specialty": "rn",
            "shift": "blended",
            "employment_type": "contract",
            "hourly_pay": float(r["all_in_agency_per_hour"]),
            "weekly_pay": None,
            "scheduled_weekly_hours": None,
            "estimated_bill_rate_factor": None,
            "posting_count": None,
            "confidence_score": 0.85,
            "confidence_tier": "High",
            "rate_type": "agency",
        })

    df = pd.DataFrame(obs)
    df["confidence_tier"] = df["confidence_score"].apply(confidence_tier)
    return df


def main() -> None:
    print("Building market_rate_observations...")
    df = build_observations()
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"  Wrote {OUTPUT_CSV}")
    print(f"  Total observations: {len(df):,}")
    print()
    print("By source type:")
    print(df.groupby(["source_type", "rate_type"]).size().to_string())
    print()
    print("By confidence tier:")
    print(df["confidence_tier"].value_counts().to_string())


if __name__ == "__main__":
    main()
