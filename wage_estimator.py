"""
Per-hospital RN wage estimator — three-tier fallback model.

Tier 1 (highest confidence): HCRIS per-hospital "total_avg_hourly_wage" × RN multiplier.
  Each hospital's S-3 Part II line 00100 col 00600 is the hospital's blended
  all-workforce avg hourly wage. We multiply by an RN-specific multiplier
  calibrated against BLS national norms (~1.4× blended wage = RN wage).
  Confidence: 0.85 — real per-hospital signal, RN-specific via multiplier.

Tier 2: BLS OEWS MSA-level (top 50 MSAs hardcoded from May 2024 release).
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
# MSA-level RN mean hourly wage table (BLS OEWS May 2024 published values).
# Top 60 MSAs by RN employment + selected high-wage markets.
# Production should ingest live BLS via API.
# ---------------------------------------------------------------------------
MSA_RN_WAGE = {
    # California — high-wage markets
    "41860": ("San Francisco-Oakland-Hayward, CA",    78.95),
    "41940": ("San Jose-Sunnyvale-Santa Clara, CA",    81.46),
    "31080": ("Los Angeles-Long Beach-Anaheim, CA",    66.85),
    "41740": ("San Diego-Carlsbad, CA",                65.20),
    "40140": ("Riverside-San Bernardino-Ontario, CA",  62.10),
    "40900": ("Sacramento-Roseville-Arden-Arcade, CA", 73.45),
    "41500": ("Salinas, CA",                           71.10),
    "23420": ("Fresno, CA",                            61.55),
    "12540": ("Bakersfield, CA",                       57.05),
    "47300": ("Visalia-Porterville, CA",               55.85),
    "32900": ("Modesto, CA",                           63.40),
    "44700": ("Stockton-Lodi, CA",                     65.80),
    "42100": ("Santa Rosa, CA",                        72.75),
    "42220": ("Santa Maria-Santa Barbara, CA",         65.95),

    # Hawaii / Alaska
    "26180": ("Urban Honolulu, HI",                    60.45),
    "11260": ("Anchorage, AK",                         57.30),

    # Pacific Northwest
    "42660": ("Seattle-Tacoma-Bellevue, WA",           61.50),
    "38900": ("Portland-Vancouver-Hillsboro, OR-WA",   58.80),

    # Mountain
    "19740": ("Denver-Aurora-Lakewood, CO",            46.20),
    "38060": ("Phoenix-Mesa-Scottsdale, AZ",           48.95),
    "46060": ("Tucson, AZ",                            46.30),
    "39900": ("Reno, NV",                              52.40),
    "29820": ("Las Vegas-Henderson-Paradise, NV",      54.65),

    # Texas
    "26420": ("Houston-The Woodlands-Sugar Land, TX",  46.85),
    "19100": ("Dallas-Fort Worth-Arlington, TX",       45.20),
    "12420": ("Austin-Round Rock, TX",                 45.95),
    "41700": ("San Antonio-New Braunfels, TX",         42.65),
    "21340": ("El Paso, TX",                           40.10),

    # South Atlantic
    "33100": ("Miami-Fort Lauderdale-West Palm Beach, FL", 40.30),
    "36740": ("Orlando-Kissimmee-Sanford, FL",         39.95),
    "45300": ("Tampa-St. Petersburg-Clearwater, FL",   40.55),
    "27260": ("Jacksonville, FL",                      39.40),
    "12060": ("Atlanta-Sandy Springs-Roswell, GA",     42.85),
    "16740": ("Charlotte-Concord-Gastonia, NC-SC",     39.95),
    "39580": ("Raleigh, NC",                           39.30),

    # Midwest
    "16980": ("Chicago-Naperville-Elgin, IL-IN-WI",    45.50),
    "19820": ("Detroit-Warren-Dearborn, MI",           40.85),
    "33340": ("Milwaukee-Waukesha-West Allis, WI",     42.70),
    "33460": ("Minneapolis-St. Paul-Bloomington, MN-WI", 47.80),
    "17460": ("Cleveland-Elyria, OH",                  39.20),
    "18140": ("Columbus, OH",                          39.55),
    "17140": ("Cincinnati, OH-KY-IN",                  38.85),
    "28140": ("Kansas City, MO-KS",                    38.30),
    "41180": ("St. Louis, MO-IL",                      37.70),
    "26900": ("Indianapolis-Carmel-Anderson, IN",      38.45),

    # Northeast
    "35620": ("New York-Newark-Jersey City, NY-NJ-PA", 56.10),
    "37980": ("Philadelphia-Camden-Wilmington, PA-NJ-DE-MD", 47.30),
    "14460": ("Boston-Cambridge-Newton, MA-NH",        56.95),
    "47900": ("Washington-Arlington-Alexandria, DC-VA-MD-WV", 50.20),
    "12580": ("Baltimore-Columbia-Towson, MD",         48.30),
    "37980": ("Philadelphia",                           47.30),
    "35614": ("New York-Jersey City-White Plains, NY-NJ", 56.10),
    "39300": ("Providence-Warwick, RI-MA",             47.55),
    "31700": ("Manchester-Nashua, NH",                 44.65),
    "13780": ("Burlington-South Burlington, VT",       43.95),

    # Other selected markets
    "12260": ("Augusta-Richmond County, GA-SC",        36.45),
    "31140": ("Louisville/Jefferson County, KY-IN",    37.55),
    "34980": ("Nashville-Davidson--Murfreesboro--Franklin, TN", 36.85),
    "32820": ("Memphis, TN-MS-AR",                     35.60),
    "13820": ("Birmingham-Hoover, AL",                 36.30),
    "33340": ("Milwaukee-Waukesha-West Allis, WI",     42.70),
    "40060": ("Richmond, VA",                          40.55),
    "47260": ("Virginia Beach-Norfolk-Newport News, VA-NC", 39.75),
    "13140": ("Beaumont-Port Arthur, TX",              41.05),
    "44060": ("Spokane-Spokane Valley, WA",            51.85),
    "31540": ("Madison, WI",                           43.85),
    "26420": ("Houston",                               46.85),

    # Critical access / sample rural markets retain state defaults
}


# State-level fallback (same as previous BLS state-level table)
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
    "PR": 22.00, "VI": 30.00, "GU": 32.00, "MP": 25.00, "AS": 22.00,
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
                    "source_year": "2024",
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
