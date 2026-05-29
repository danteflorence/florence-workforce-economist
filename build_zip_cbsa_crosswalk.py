"""
Build ZIP → County → CBSA/MSA crosswalk.

Sources:
  - data/geo/zcta_county_2020.txt — Census 2020 ZCTA-to-County relationship file
  - data/geo/cbsa_list_2023.xlsx   — Census 2023 CBSA delineation list

Output:
  data/geo/zip_cbsa.csv with columns:
    zip, county_fips, county_name, state_fips,
    cbsa_code, cbsa_title, cbsa_type (Metro/Micro/None), rural_flag
"""

from pathlib import Path

import pandas as pd

GEO = Path(__file__).parent / "data" / "geo"
OUTPUT = GEO / "zip_cbsa.csv"


def main() -> None:
    print("Building ZIP → CBSA crosswalk...")

    # ── ZCTA → County (some ZCTAs span multiple counties; pick dominant) ──
    zc = pd.read_csv(GEO / "zcta_county_2020.txt", sep="|", dtype=str)
    zc = zc[["GEOID_ZCTA5_20", "GEOID_COUNTY_20", "NAMELSAD_COUNTY_20", "AREALAND_PART"]]
    zc.columns = ["zip", "county_fips", "county_name", "areal_part"]
    zc = zc.dropna(subset=["zip", "county_fips"])
    zc["areal_part"] = pd.to_numeric(zc["areal_part"], errors="coerce").fillna(0)
    # For ZIPs spanning multiple counties, keep the one with largest land area
    zc = zc.sort_values("areal_part", ascending=False).drop_duplicates("zip")
    zc["state_fips"] = zc["county_fips"].str[:2]
    print(f"  ZCTA → County: {len(zc):,} unique ZIPs.")

    # ── County → CBSA ──
    # Cols (0-indexed): 0=CBSA Code, 3=CBSA Title, 4=CBSA Type, 7=County name,
    #                   9=FIPS State Code, 10=FIPS County Code
    cbsa = pd.read_excel(GEO / "cbsa_list_2023.xlsx", header=None, skiprows=3,
                         usecols=[0, 3, 4, 7, 9, 10])
    cbsa.columns = ["cbsa_code", "cbsa_title", "cbsa_type", "county_name",
                    "fips_state", "fips_county"]
    cbsa = cbsa.dropna(subset=["cbsa_code", "fips_state", "fips_county"]).copy()
    cbsa["cbsa_code"] = cbsa["cbsa_code"].astype(int).astype(str)
    cbsa["fips_state_county"] = (
        cbsa["fips_state"].astype(int).astype(str).str.zfill(2)
        + cbsa["fips_county"].astype(int).astype(str).str.zfill(3)
    )
    cbsa = cbsa[["cbsa_code", "cbsa_title", "cbsa_type", "fips_state_county"]]
    print(f"  County → CBSA: {len(cbsa):,} county-rows ({cbsa['cbsa_code'].nunique():,} unique CBSAs).")

    # ── Join ZIP → County → CBSA ──
    merged = zc.merge(cbsa, left_on="county_fips", right_on="fips_state_county", how="left")
    merged["rural_flag"] = merged["cbsa_code"].isna() | (
        merged["cbsa_type"].fillna("").str.contains("Micropolitan", case=False)
    )
    merged["cbsa_code"] = merged["cbsa_code"].fillna("")
    merged["cbsa_title"] = merged["cbsa_title"].fillna("Rural / Nonmetro")
    merged["cbsa_type"] = merged["cbsa_type"].fillna("Nonmetro")

    out = merged[["zip", "county_fips", "county_name", "state_fips",
                  "cbsa_code", "cbsa_title", "cbsa_type", "rural_flag"]]
    out.to_csv(OUTPUT, index=False)
    print(f"  Wrote {OUTPUT}")
    print()
    print("Coverage:")
    print(f"  Total ZIPs:       {len(out):,}")
    print(f"  With CBSA:        {(~out['rural_flag']).sum():,}")
    print(f"  Rural / Nonmetro: {out['rural_flag'].sum():,}")
    print()
    print("Sample:")
    print(out.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
