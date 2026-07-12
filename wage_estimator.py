"""
Per-hospital RN wage estimator — three-tier fallback model.

Tier 1 (highest confidence): HCRIS per-hospital "total_avg_hourly_wage" × RN multiplier.
  Each hospital's S-3 Part II line 00100 col 00600 is the hospital's blended
  all-workforce avg hourly wage. We multiply by an RN-specific multiplier
  calibrated against BLS national norms (~1.4× blended wage = RN wage).
  Confidence: 0.85 — real per-hospital signal, RN-specific via multiplier.

Tier 2: BLS OEWS MSA-level (top 50 MSAs hardcoded from May 2025 release).
  Real BLS data for major metros. Production version pulls live from BLS API.
  Confidence: 0.80

Tier 3: BLS state-level RN wage (existing STATE_RN_WAGE table).
  Fallback for hospitals without HCRIS wage data and outside top-50 MSAs.
  Confidence: 0.40

Output: data/per_hospital_rn_wages.csv keyed by CCN with:
  ccn, taxable_wage_per_hour, source, confidence, msa_code, source_year
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
HCRIS_AGENCY_RATES_CSV = DATA_DIR / "hcris_agency_rates.csv"
HOSPITAL_GEOCODES_CSV = DATA_DIR / "hospital_geocodes.csv"
CMS_ROSTER_CSV = DATA_DIR / "cms_hospitals.csv"
ZIP_CBSA_CSV = DATA_DIR / "geo" / "zip_cbsa.csv"
OUTPUT_CSV = DATA_DIR / "per_hospital_rn_wages.csv"

# RN wage / blended-hospital-wage ratio.
# BLS national May 2024: hospital all-workforce ~$36/hr; RN ~$50/hr → ratio ≈ 1.39.
RN_TO_BLENDED_MULTIPLIER = 1.40

# ---------------------------------------------------------------------------
# MSA-level RN mean hourly wage table (BLS OEWS May 2025 published values).
# Top 60 MSAs by RN employment + selected high-wage markets.
# Production should ingest live BLS via API.
# ---------------------------------------------------------------------------
MSA_RN_WAGE = {
    # California — high-wage markets
    "41860": ("San Francisco-Oakland-Hayward, CA",  85.05),
    "41940": ("San Jose-Sunnyvale-Santa Clara, CA",  93.73),
    "31080": ("Los Angeles-Long Beach-Anaheim, CA",  67.48),
    "41740": ("San Diego-Carlsbad, CA",  69.74),
    "40140": ("Riverside-San Bernardino-Ontario, CA",  65.71),
    "40900": ("Sacramento-Roseville-Arden-Arcade, CA",  78.94),
    "41500": ("Salinas, CA",  66.73),
    "23420": ("Fresno, CA",  61.00),
    "12540": ("Bakersfield, CA",  61.63),
    "47300": ("Visalia-Porterville, CA",  59.67),
    "32900": ("Modesto, CA",  62.35),
    "44700": ("Stockton-Lodi, CA",  69.91),
    "42100": ("Santa Rosa, CA",  76.84),
    "42220": ("Santa Maria-Santa Barbara, CA",  81.73),
    "26180": ("Urban Honolulu, HI",  60.45),  # May 2024 carryover (2025 unpublished)
    "11260": ("Anchorage, AK",  56.09),
    "42660": ("Seattle-Tacoma-Bellevue, WA",  60.76),
    "38900": ("Portland-Vancouver-Hillsboro, OR-WA",  60.21),
    "19740": ("Denver-Aurora-Lakewood, CO",  48.52),
    "38060": ("Phoenix-Mesa-Scottsdale, AZ",  48.60),
    "46060": ("Tucson, AZ",  46.06),
    "39900": ("Reno, NV",  50.42),
    "29820": ("Las Vegas-Henderson-Paradise, NV",  51.13),
    "26420": ("Houston-The Woodlands-Sugar Land, TX",  48.21),
    "19100": ("Dallas-Fort Worth-Arlington, TX",  48.47),
    "12420": ("Austin-Round Rock, TX",  46.93),
    "41700": ("San Antonio-New Braunfels, TX",  45.08),
    "21340": ("El Paso, TX",  42.51),
    "33100": ("Miami-Fort Lauderdale-West Palm Beach, FL",  45.67),
    "36740": ("Orlando-Kissimmee-Sanford, FL",  42.87),
    "45300": ("Tampa-St. Petersburg-Clearwater, FL",  44.56),
    "27260": ("Jacksonville, FL",  42.94),
    "12060": ("Atlanta-Sandy Springs-Roswell, GA",  47.96),
    "16740": ("Charlotte-Concord-Gastonia, NC-SC",  44.83),
    "39580": ("Raleigh, NC",  44.18),
    "16980": ("Chicago-Naperville-Elgin, IL-IN-WI",  47.08),
    "19820": ("Detroit-Warren-Dearborn, MI",  45.90),
    "33340": ("Milwaukee-Waukesha-West Allis, WI",  46.18),
    "33460": ("Minneapolis-St. Paul-Bloomington, MN-WI",  51.19),
    "17460": ("Cleveland-Elyria, OH",  39.20),  # May 2024 carryover (2025 unpublished)
    "18140": ("Columbus, OH",  42.68),
    "17140": ("Cincinnati, OH-KY-IN",  43.24),
    "28140": ("Kansas City, MO-KS",  42.18),
    "41180": ("St. Louis, MO-IL",  42.46),
    "26900": ("Indianapolis-Carmel-Anderson, IN",  43.09),
    "35620": ("New York-Newark-Jersey City, NY-NJ-PA",  57.50),
    "37980": ("Philadelphia-Camden-Wilmington, PA-NJ-DE-MD",  48.75),
    "14460": ("Boston-Cambridge-Newton, MA-NH",  58.57),
    "47900": ("Washington-Arlington-Alexandria, DC-VA-MD-WV",  50.28),
    "12580": ("Baltimore-Columbia-Towson, MD",  47.64),
    "37980": ("Philadelphia",  48.75),
    "35614": ("New York-Jersey City-White Plains, NY-NJ",  56.10),  # May 2024 carryover (2025 unpublished)
    "39300": ("Providence-Warwick, RI-MA",  49.06),
    "31700": ("Manchester-Nashua, NH",  46.58),
    "13780": ("Burlington-South Burlington, VT",  47.81),
    "12260": ("Augusta-Richmond County, GA-SC",  44.00),
    "31140": ("Louisville/Jefferson County, KY-IN",  43.36),
    "34980": ("Nashville-Davidson--Murfreesboro--Franklin, TN",  44.40),
    "32820": ("Memphis, TN-MS-AR",  42.01),
    "13820": ("Birmingham-Hoover, AL",  37.95),
    "33340": ("Milwaukee-Waukesha-West Allis, WI",  46.18),
    "40060": ("Richmond, VA",  44.24),
    "47260": ("Virginia Beach-Norfolk-Newport News, VA-NC",  42.96),
    "13140": ("Beaumont-Port Arthur, TX",  41.30),
    "44060": ("Spokane-Spokane Valley, WA",  54.46),
    "31540": ("Madison, WI",  48.29),
    "26420": ("Houston",  48.21),
}


# State-level fallback (same as previous BLS state-level table)
STATE_RN_WAGE = {
    "AK": 55.23, "AL": 37.03, "AR": 39.19, "AZ": 47.95, "CA": 72.25,
    "CO": 47.78, "CT": 50.60, "DC": 51.43, "DE": 47.82, "FL": 43.58,
    "GA": 45.71, "HI": 59.78, "IA": 38.72, "ID": 44.57, "IL": 45.36,
    "IN": 42.86, "KS": 39.60, "KY": 41.41, "LA": 40.48, "MA": 56.71,
    "MD": 47.60, "ME": 44.09, "MI": 45.34, "MN": 49.72, "MO": 41.30,
    "MS": 37.96, "MT": 43.99, "NC": 43.50, "ND": 40.19, "NE": 42.47,
    "NH": 47.07, "NJ": 52.93, "NM": 45.81, "NV": 50.82, "NY": 54.54,
    "OH": 42.18, "OK": 40.90, "OR": 59.20, "PA": 45.20, "RI": 48.68,
    "SC": 42.15, "SD": 37.09, "TN": 41.05, "TX": 45.86, "UT": 43.72,
    "VA": 45.12, "VT": 46.47, "WA": 58.43, "WI": 45.53, "WV": 41.81,
    "WY": 42.60,
    # Territories (GU/MP/AS unpublished in May 2025 — prior values kept)
    "PR": 22.21, "VI": 43.23, "GU": 32.00, "MP": 25.00, "AS": 22.00,
}
NATIONAL_RN_WAGE = sum(STATE_RN_WAGE.values()) / len(STATE_RN_WAGE)


def main() -> None:
    print("Building per-hospital RN wage estimates...")
    # Load CMS hospital roster (CCN + ZIP + state)
    cms = pd.read_csv(CMS_ROSTER_CSV, dtype=str)
    cms = cms.rename(columns={
        "Facility ID": "ccn", "ZIP Code": "zip", "State": "state",
    })
    cms["ccn"] = cms["ccn"].str.zfill(6)
    cms["zip"] = cms["zip"].str[:5].str.zfill(5)
    print(f"  CMS roster: {len(cms):,} hospitals")

    # Load HCRIS NMRC for per-hospital blended wage
    hcris = pd.read_csv(HCRIS_AGENCY_RATES_CSV, dtype={"ccn": str})
    hcris["ccn"] = hcris["ccn"].str.zfill(6)
    hcris = hcris[["ccn", "total_avg_hourly_wage"]].rename(
        columns={"total_avg_hourly_wage": "hcris_blended_wage"}
    )
    print(f"  HCRIS blended wage: {len(hcris):,} hospitals")

    # Load ZIP → CBSA crosswalk
    zip_cbsa = pd.read_csv(ZIP_CBSA_CSV, dtype=str)
    zip_cbsa = zip_cbsa[["zip", "cbsa_code", "cbsa_title", "rural_flag"]]
    print(f"  ZIP-CBSA crosswalk: {len(zip_cbsa):,} ZIPs")

    # Join
    df = cms[["ccn", "zip", "state"]].merge(zip_cbsa, on="zip", how="left")
    df = df.merge(hcris, on="ccn", how="left")
    print(f"  Joined: {len(df):,} rows, {df['hcris_blended_wage'].notna().sum():,} with HCRIS wage")

    # Tier 1 (preferred): BLS OEWS MSA-level — canonical RN-specific wage source.
    def tier1(row):
        cbsa = row.get("cbsa_code")
        if cbsa and cbsa in MSA_RN_WAGE:
            return MSA_RN_WAGE[cbsa][1], "bls_oews_msa", 0.90
        return None

    # Tier 2: HCRIS-derived per-hospital blended wage × RN multiplier.
    # Lower confidence than MSA-level BLS because the 1.4× multiplier may
    # over-correct for RN-heavy systems (e.g., Kaiser blended is already high).
    # Sanity bounds: $18-$95/hr blended → $25-$133/hr after multiplier.
    def tier2(row):
        w = row.get("hcris_blended_wage")
        if pd.notna(w) and 18 <= w <= 95:
            return round(w * RN_TO_BLENDED_MULTIPLIER, 2), "hcris_blended_x_multiplier", 0.70
        return None

    # Tier 3: State-level fallback.
    def tier3(row):
        wage = STATE_RN_WAGE.get(row.get("state"), NATIONAL_RN_WAGE)
        return wage, "bls_oews_state_placeholder", 0.40

    results = []
    for _, r in df.iterrows():
        for tier_fn in (tier1, tier2, tier3):
            res = tier_fn(r)
            if res:
                wage, source, conf = res
                results.append({
                    "ccn": r["ccn"], "zip": r["zip"], "state": r["state"],
                    "cbsa_code": r.get("cbsa_code") or "",
                    "cbsa_title": r.get("cbsa_title") or "",
                    "taxable_wage_per_hour": wage,
                    "wage_source": source,
                    "wage_confidence": conf,
                    "source_year": "2025",
                })
                break

    out = pd.DataFrame(results)
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"\n  Wrote {OUTPUT_CSV}")
    print(f"  Total: {len(out):,} hospitals")
    print()
    print("Wage source distribution:")
    for src, n in out["wage_source"].value_counts().items():
        avg = out[out["wage_source"] == src]["taxable_wage_per_hour"].mean()
        print(f"  {src:38} {n:>5}  avg=${avg:,.2f}/hr")
    print()
    print("Wage percentiles (US national):")
    for p in [10, 25, 50, 75, 90, 99]:
        v = out["taxable_wage_per_hour"].quantile(p/100)
        print(f"  P{p}: ${v:.2f}/hr")


if __name__ == "__main__":
    main()
