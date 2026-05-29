"""
Merge NASHP HCT (Hospital Cost Tool) system ownership into hospital_universe.csv.

NASHP's HCT dataset includes curated `Health System` + `Health System ID` fields
for ~4,700 US hospitals — coverage we don't get from any other public source.
This script:

  1. Loads NASHP 2020-2024 multi-year ownership (most-recent year per CCN)
  2. Maps NASHP system names → Florence slug ids
       - Curated mapping for the 30+ systems we already track
       - Auto-slugified fallback for everything else
  3. Backs up the current hospital_universe.csv
  4. Overrides health_system_id + health_system in our universe with NASHP data
       - Skips CCNs marked "Independent" in NASHP (preserves our existing assignment)
  5. Reports the delta (HCA was 64 → ???, etc.)

Run once after dropping new NASHP files in ~/Downloads.
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
UNIVERSE_PATH = DATA_DIR / "hospital_universe.csv"
NASHP_MULTIYEAR = Path("/Users/dantetolbedantert/Downloads/NASHP 2020-2024 HCT Data 2025 Dec.xlsx")

# --- Curated NASHP → Florence slug map -------------------------------------
# For systems where we already have a canonical slug (and possibly MSP overlay
# data), use the exact slug we're already using. For everything else, the
# auto-slugifier handles it.
CURATED_SLUG_MAP: dict[str, tuple[str, str]] = {
    # NASHP name → (slug, display_name)
    "HCA Healthcare": ("hca", "HCA"),
    "CommonSpirit Health": ("commonspirit", "CommonSpirit Health"),
    "Ascension Health": ("ascension", "Ascension"),
    "Providence": ("providence", "Providence"),
    "Kaiser Permanente": ("kaiser_permanente", "Kaiser Permanente"),
    "AdventHealth": ("adventhealth", "AdventHealth"),
    "Christus Health": ("christus_health", "CHRISTUS Health"),
    "Sutter Health": ("sutter_health", "Sutter Health"),
    "Banner Health": ("banner_health", "Banner Health"),
    "Beth Israel Lahey Health": ("beth_israel_lahey_health", "Beth Israel Lahey Health"),
    "RWJBarnabas Health": ("rwjbarnabas_health", "RWJBarnabas Health"),
    "UPMC": ("upmc", "UPMC"),
    "Ochsner Health System": ("ochsner", "Ochsner"),
    "Adventist Health": ("adventist_health", "Adventist Health"),
    # New systems — keep NASHP's exact name as display, slugified id
    "Trinity Health MI": ("trinity_health", "Trinity Health"),
    "Community Health Systems": ("community_health_systems", "Community Health Systems"),
    "Tenet Healthcare": ("tenet_healthcare", "Tenet Healthcare"),
    "Lifepoint Health": ("lifepoint_health", "Lifepoint Health"),
    "Advocate Health": ("advocate_health", "Advocate Health"),
    "Prime Healthcare Services": ("prime_healthcare", "Prime Healthcare"),
    "Mayo Clinic Health System": ("mayo_clinic", "Mayo Clinic"),
    "Cleveland Clinic": ("cleveland_clinic", "Cleveland Clinic"),
    "Baylor Scott and White Health": ("baylor_scott_white", "Baylor Scott & White"),
    "Intermountain Healthcare": ("intermountain_health", "Intermountain Health"),
    "Bon Secours Mercy Health": ("bon_secours_mercy_health", "Bon Secours Mercy Health"),
    "Mass General Brigham": ("mass_general_brigham", "Mass General Brigham"),
    "Northwell Health": ("northwell_health", "Northwell Health"),
    "Sanford Health": ("sanford_health", "Sanford Health"),
    "Quorum Health Corporation": ("quorum_health", "Quorum Health"),
    "Mercy": ("mercy_health", "Mercy"),
    "SSM Health": ("ssm_health", "SSM Health"),
    "Avera Health": ("avera_health", "Avera Health"),
    "Universal Health Services": ("universal_health_services", "Universal Health Services"),
    "Unitypoint Health": ("unitypoint_health", "UnityPoint Health"),
    "Steward Health Care System": ("steward_health_care", "Steward Health Care"),
    "Ardent Health Services": ("ardent_health", "Ardent Health"),
}


def slugify(name: str) -> str:
    """Slugify a system name for a stable system_id."""
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"^_+|_+$", "", s)
    return s or "independent"


def map_system(nashp_name: str) -> tuple[str, str]:
    """Return (slug, display_name) for a NASHP system_name."""
    if pd.isna(nashp_name) or not nashp_name or nashp_name == "Independent":
        return ("independent", "Independent / Unknown")
    if nashp_name in CURATED_SLUG_MAP:
        return CURATED_SLUG_MAP[nashp_name]
    return (slugify(nashp_name), nashp_name)


def load_nashp_ownership() -> pd.DataFrame:
    """Load NASHP multi-year data, latest year per CCN."""
    df = pd.read_excel(
        NASHP_MULTIYEAR,
        sheet_name="Downloadable_2020-24",
        usecols=["CCN#", "Year", "Health System", "Hospital Ownership Type"],
    )
    df.columns = ["ccn", "year", "system_name", "ownership_type"]
    df = df.dropna(subset=["ccn"])
    df["ccn"] = df["ccn"].astype(str).str.split(".").str[0].str.zfill(6)
    df = df.sort_values("year").drop_duplicates("ccn", keep="last")
    df["system_slug"], df["system_display"] = zip(*df["system_name"].apply(map_system))
    return df[["ccn", "system_slug", "system_display", "ownership_type", "year"]]


def main():
    print(f"Loading current universe from {UNIVERSE_PATH}")
    u = pd.read_csv(UNIVERSE_PATH, dtype={"ccn": str})
    u["ccn"] = u["ccn"].astype(str).str.zfill(6)
    n_before = u["health_system_id"].value_counts()

    # Back up
    backup = UNIVERSE_PATH.with_suffix(f".bak_{date.today().isoformat()}.csv")
    if not backup.exists():
        shutil.copy(UNIVERSE_PATH, backup)
        print(f"Backed up universe → {backup}")

    print("Loading NASHP ownership…")
    nashp = load_nashp_ownership()
    print(f"  NASHP has {len(nashp):,} hospitals with system data")
    print(f"  NASHP independent: {(nashp['system_slug'] == 'independent').sum():,}")
    print(f"  NASHP system-affiliated: {(nashp['system_slug'] != 'independent').sum():,}")

    # Merge: take NASHP wherever NASHP says something specific (not "independent")
    u = u.merge(nashp, on="ccn", how="left", suffixes=("", "_nashp"))
    mask_nashp_named = (
        u["system_slug"].notna()
        & (u["system_slug"] != "independent")
    )
    print(f"  CCNs that NASHP names + we already have: {mask_nashp_named.sum():,}")

    # Apply
    u.loc[mask_nashp_named, "health_system_id"] = u.loc[mask_nashp_named, "system_slug"]
    u.loc[mask_nashp_named, "health_system"] = u.loc[mask_nashp_named, "system_display"]

    # Drop NASHP join columns before writing
    u = u.drop(columns=["system_slug", "system_display", "ownership_type", "year"], errors="ignore")
    u.to_csv(UNIVERSE_PATH, index=False)

    n_after = u["health_system_id"].value_counts()
    print()
    print("=== System-count delta (top systems) ===")
    print(f"{'system_id':<32} {'before':>8} {'after':>8} {'delta':>8}")
    print("-" * 60)
    interesting = ["hca", "commonspirit", "ascension", "trinity_health",
                   "tenet_healthcare", "community_health_systems",
                   "lifepoint_health", "providence", "kaiser_permanente",
                   "ascension", "adventhealth", "advocate_health",
                   "prime_healthcare", "ochsner", "sutter_health",
                   "banner_health", "mayo_clinic", "cleveland_clinic",
                   "baylor_scott_white", "intermountain_health", "independent"]
    seen = set()
    for sid in interesting:
        if sid in seen: continue
        seen.add(sid)
        b = int(n_before.get(sid, 0))
        a = int(n_after.get(sid, 0))
        d = a - b
        marker = "  ⭐" if abs(d) > 0 else ""
        print(f"{sid:<32} {b:>8,} {a:>8,} {d:+8,}{marker}")

    print()
    print(f"Total assigned: {(u['health_system_id'] != 'independent').sum():,} "
          f"(was {(n_before.drop('independent', errors='ignore').sum()):,})")
    print(f"Independent: {(u['health_system_id'] == 'independent').sum():,}")
    print(f"Total: {len(u):,}")
    print()
    print(f"✓ Updated {UNIVERSE_PATH}")
    print(f"  Backup retained at {backup}")


if __name__ == "__main__":
    main()
