"""
Geocode hospitals (ZIP → lat/lon) and infer parent health system.

Inputs:
  - data/cms_hospitals.csv (5,432 hospitals with 5-digit ZIPs)
  - data/2024_Gaz_zcta_national.txt (Census 2024 ZCTA gazetteer with lat/lon)

Outputs:
  - data/hospital_geocodes.csv (ccn, lat, lon, health_system, system_confidence)

Health-system inference is name-based with an expanding keyword table. In
production, swap this for AHA (American Hospital Association) parent-system
mappings — they license a definitive crosswalk.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
CMS_ROSTER = DATA_DIR / "cms_hospitals.csv"
ZCTA_FILE = DATA_DIR / "2024_Gaz_zcta_national.txt"
OUTPUT = DATA_DIR / "hospital_geocodes.csv"

# ---------------------------------------------------------------------------
# Health system inference — keyword → canonical system name
# Order matters: more-specific patterns first.
# ---------------------------------------------------------------------------
SYSTEM_PATTERNS: list[tuple[str, str]] = [
    # Kaiser
    ("KAISER", "Kaiser Permanente"),
    ("KFH", "Kaiser Permanente"),

    # Top non-profit systems
    ("COMMONSPIRIT", "CommonSpirit"),
    ("DIGNITY HEALTH", "CommonSpirit"),
    ("CATHOLIC HEALTH INITIATIVES", "CommonSpirit"),
    ("CHI ST", "CommonSpirit"),
    ("CHI-", "CommonSpirit"),

    ("ASCENSION", "Ascension"),
    ("PROVIDENCE", "Providence"),
    ("SAINT JOSEPH HEALTH", "Providence"),
    ("ADVENTHEALTH", "AdventHealth"),
    ("ADVENTIST HEALTH", "Adventist Health"),
    ("INTERMOUNTAIN", "Intermountain Health"),
    ("BANNER", "Banner Health"),
    ("SUTTER", "Sutter Health"),
    ("TRINITY HEALTH", "Trinity Health"),
    ("BON SECOURS", "Bon Secours Mercy Health"),
    ("MERCY HEALTH", "Bon Secours Mercy Health"),
    ("HSHS", "HSHS"),
    ("GEISINGER", "Geisinger"),
    ("INOVA", "Inova"),
    ("LIFEPOINT", "LifePoint Health"),
    ("SSM HEALTH", "SSM Health"),
    ("MEMORIAL HERMANN", "Memorial Hermann"),
    ("HOUSTON METHODIST", "Houston Methodist"),
    ("ORLANDO HEALTH", "Orlando Health"),
    ("BAPTIST HEALTH", "Baptist Health"),
    ("BAYLOR SCOTT", "Baylor Scott & White"),
    ("BJC", "BJC HealthCare"),
    ("NORTHWELL", "Northwell Health"),
    ("MOUNT SINAI", "Mount Sinai"),
    ("NYU LANGONE", "NYU Langone"),
    ("NEWYORK-PRESBYTERIAN", "NewYork-Presbyterian"),
    ("PRESBYTERIAN HEALTHCARE", "Presbyterian Healthcare"),
    ("CHRISTIANACARE", "ChristianaCare"),
    ("INDIANA UNIVERSITY HEALTH", "IU Health"),
    ("IU HEALTH", "IU Health"),
    ("CLEVELAND CLINIC", "Cleveland Clinic"),
    ("MAYO CLINIC", "Mayo Clinic"),
    ("MASS GENERAL", "Mass General Brigham"),
    ("BRIGHAM AND WOMEN", "Mass General Brigham"),
    ("PARTNERS HEALTHCARE", "Mass General Brigham"),
    ("BETH ISRAEL DEACONESS", "Beth Israel Lahey Health"),
    ("LAHEY HOSPITAL", "Beth Israel Lahey Health"),
    ("HOSPITAL OF THE UNIVERSITY OF PENNSYLVANIA", "Penn Medicine"),
    ("PENN MEDICINE", "Penn Medicine"),
    ("UPMC", "UPMC"),
    ("JOHNS HOPKINS", "Johns Hopkins"),
    ("DUKE UNIVERSITY", "Duke Health"),
    ("UNC HEALTH", "UNC Health"),
    ("ATRIUM", "Advocate Health"),
    ("ADVOCATE", "Advocate Health"),
    ("AURORA HEALTH", "Advocate Health"),
    ("BAYHEALTH", "Bayhealth"),
    ("EMORY", "Emory Healthcare"),
    ("PIEDMONT", "Piedmont Healthcare"),
    ("WELLSTAR", "Wellstar"),
    ("OCHSNER", "Ochsner"),
    ("CHRISTUS", "CHRISTUS Health"),
    ("METHODIST LE BONHEUR", "Methodist Le Bonheur"),
    ("STORMONT", "Stormont Vail"),
    ("CARILION", "Carilion"),
    ("SENTARA", "Sentara"),
    ("VIDANT", "ECU Health"),
    ("ECU HEALTH", "ECU Health"),
    ("ALLEGHENY HEALTH", "Allegheny Health"),
    ("UAB HOSPITAL", "UAB Health"),
    ("UAMS", "UAMS"),
    ("STANFORD", "Stanford Health"),
    ("CEDARS-SINAI", "Cedars-Sinai"),
    ("UCSF", "UCSF Health"),
    ("UCLA", "UCLA Health"),
    ("UCSD", "UC San Diego Health"),
    ("UC DAVIS", "UC Davis Health"),
    ("UC IRVINE", "UC Irvine Health"),
    ("KECK", "Keck Medicine of USC"),
    ("CITY OF HOPE", "City of Hope"),
    ("NORTHWESTERN MEMORIAL", "Northwestern Medicine"),
    ("NORTHWESTERN MEDICINE", "Northwestern Medicine"),
    ("RUSH UNIVERSITY", "Rush"),
    ("UNIVERSITY OF CHICAGO MED", "University of Chicago Medicine"),
    ("ROBERT WOOD JOHNSON", "RWJBarnabas Health"),
    ("RWJ", "RWJBarnabas Health"),
    ("BARNABAS", "RWJBarnabas Health"),
    ("HACKENSACK", "Hackensack Meridian Health"),
    ("ATLANTIC HEALTH", "Atlantic Health System"),
    ("MAINE MEDICAL", "MaineHealth"),

    # For-profit chains
    ("HCA HEALTHCARE", "HCA"),
    ("HCA ", "HCA"),
    ("MEDICAL CITY", "HCA"),
    ("OAK HILL HOSPITAL", "HCA"),
    ("TENET", "Tenet"),
    ("UNIVERSAL HEALTH SERVICES", "Universal Health Services"),
    ("UHS", "Universal Health Services"),
    ("COMMUNITY HEALTH SYSTEMS", "Community Health Systems"),
    ("STEWARD", "Steward Health Care"),
    ("PRIME HEALTHCARE", "Prime Healthcare"),

    # Public / state systems
    ("VETERANS AFFAIRS", "VA"),
    ("VA MEDICAL", "VA"),
    ("HARRIS HEALTH", "Harris Health (Texas)"),
    ("PARKLAND", "Parkland Health (Texas)"),
    ("NYC HEALTH", "NYC Health + Hospitals"),
    ("METROPOLITAN HOSPITAL", "NYC Health + Hospitals"),
    ("BELLEVUE HOSPITAL", "NYC Health + Hospitals"),
    ("KINGS COUNTY HOSPITAL", "NYC Health + Hospitals"),
    ("LA COUNTY", "LA County DHS"),
    ("HARBOR-UCLA", "LA County DHS"),
    ("ZUCKERBERG SAN FRANCISCO", "San Francisco DPH"),
    ("COOK COUNTY", "Cook County Health"),
    ("BAYLOR COLLEGE", "Baylor College of Medicine"),
]


def infer_system(name: str) -> tuple[str, float]:
    """Return (canonical_system_name, confidence)."""
    if not name:
        return ("Independent / Unknown", 0.0)
    n = name.upper()
    for keyword, canonical in SYSTEM_PATTERNS:
        if keyword in n:
            return (canonical, 0.85)  # name-based inference; ~15% miss rate
    return ("Independent / Unknown", 0.0)


def system_id(canonical_name: str) -> str:
    """Stable snake_case ID for a canonical system name. Used as the join key
    for filtering and proposal rollups (per Product Plan MVP Acceptance:
    'Health system filtering uses Health System ID, not substring matching').

    Production version should be replaced by a curated CCN → health_system_id
    table sourced from AHA Annual Survey or Definitive Healthcare.
    """
    if not canonical_name or canonical_name == "Independent / Unknown":
        return "independent"
    import re
    s = canonical_name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def load_zcta_centroids() -> pd.DataFrame:
    df = pd.read_csv(ZCTA_FILE, sep="\t", dtype={"GEOID": str})
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "GEOID": "zip",
        "INTPTLAT": "lat",
        "INTPTLONG": "lon",
    })[["zip", "lat", "lon"]]
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)
    return df


def main() -> None:
    print("Geocoding hospitals + inferring health systems...")
    cms = pd.read_csv(CMS_ROSTER, dtype=str)
    cms = cms.rename(columns={
        "Facility ID": "ccn", "Facility Name": "name",
        "City/Town": "city", "State": "state", "ZIP Code": "zip",
    })
    cms["ccn"] = cms["ccn"].str.zfill(6)
    cms["zip"] = cms["zip"].str[:5].str.zfill(5)
    cms["name_upper"] = cms["name"].str.upper().str.strip()

    zcta = load_zcta_centroids()
    print(f"  ZCTA centroids: {len(zcta):,}")

    # Geocode — primary join on exact ZIP
    geocoded = cms.merge(zcta, on="zip", how="left")
    n_with_latlon = geocoded["lat"].notna().sum()
    print(f"  Geocoded (exact ZIP): {n_with_latlon:,} / {len(cms):,} hospitals")

    # Fallback 1: nearest 3-digit ZIP prefix (sectional center facility) average
    miss_mask = geocoded["lat"].isna()
    if miss_mask.any():
        zcta["zip3"] = zcta["zip"].str[:3]
        zip3_avg = zcta.groupby("zip3").agg(
            lat=("lat", "mean"), lon=("lon", "mean")
        ).reset_index()
        geocoded["zip3"] = geocoded["zip"].str[:3]
        fallback = geocoded[miss_mask][["ccn", "zip3"]].merge(zip3_avg, on="zip3", how="left")
        geocoded.loc[miss_mask, "lat"] = fallback["lat"].values
        geocoded.loc[miss_mask, "lon"] = fallback["lon"].values
        geocoded.drop(columns=["zip3"], inplace=True)
        new_total = geocoded["lat"].notna().sum()
        print(f"  After 3-digit ZIP fallback: {new_total:,} / {len(cms):,}")

    # Health system inference + stable ID
    inferred = geocoded["name_upper"].apply(infer_system)
    geocoded["health_system"] = inferred.apply(lambda x: x[0])
    geocoded["system_confidence"] = inferred.apply(lambda x: x[1])
    geocoded["health_system_id"] = geocoded["health_system"].apply(system_id)

    n_sys = (geocoded["health_system"] != "Independent / Unknown").sum()
    print(f"  Health system inferred: {n_sys:,} / {len(geocoded):,} hospitals "
          f"({n_sys/len(geocoded)*100:.1f}%)")

    print("\n  Top 15 health systems by hospital count:")
    sys_counts = geocoded["health_system"].value_counts().head(15)
    for sys, n in sys_counts.items():
        print(f"    {sys:35} {n:>4}")

    out = geocoded[["ccn", "lat", "lon", "health_system", "health_system_id", "system_confidence"]]
    out.to_csv(OUTPUT, index=False)
    print(f"\n  Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
