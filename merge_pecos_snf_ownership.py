"""
Merge CMS PECOS / Nursing Home Ownership data into non_hospital_facilities.csv.

NH_Ownership.csv (CMS Provider Data Catalog dataset y2hd-n93e) has 232K rows
covering all 14,700 Medicare-certified SNFs. Each row = one ownership stake.

For each SNF CCN, we identify the PRIMARY OPERATING ORGANIZATION:
  - Filter to Owner Type = "Organization" (not Individual)
  - Filter to operational roles (5%+ ownership, operator, management)
  - Exclude accounting firms, banks, REIT holding cos, advisory firms
  - Use the largest ownership stake as the primary operator

Then normalize operator names → Florence chain slugs and apply to the
non_hospital_facilities.csv universe.
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
PECOS_NH = DATA / "raw_cms_non_hospital" / "NH_Ownership.csv"
FACILITIES = DATA / "non_hospital_facilities.csv"

# Patterns to EXCLUDE — these orgs aren't operators (accounting, banks, REITs)
EXCLUSION_PATTERNS = re.compile(
    r"\b(LLP|LP$|TRUST\b|TRUSTEE|"
    r"BANK|FINANCIAL|CAPITAL|INVEST|FUND|HOLDING|HOLDINGS|"
    r"ACCOUNTING|ADVISOR|ADVISORS|ADVISORY|CONSULT|CPA|"
    r"MAZARS|FORVIS|WIPFLI|BAKER TILLY|CITRIN COOPERMAN|"
    r"CLIFTONLARSONALLEN|CRAIG FLASHNER|FAM TR|GENERATION TRUST|"
    r"REIT|REALTY|REAL ESTATE|NNN|PROPERTY|PROPERTIES|"
    r"FLASHNER|MERGER SUB|GROUP NH|HCCF\b)",
    re.IGNORECASE,
)

# Curated map: PECOS owner name pattern → (Florence slug, display name)
# These match the major SNF operating chains
CHAIN_NORMALIZATIONS = [
    # Largest national operators
    (re.compile(r"^ENSIGN\s+(SERVICES|GROUP)\b|\bENSIGN\s+GROUP\b", re.I),
     ("ensign_group", "The Ensign Group")),
    (re.compile(r"\bLIFE\s+CARE\s+CENTERS\b", re.I),
     ("life_care_centers", "Life Care Centers of America")),
    (re.compile(r"\bGENESIS\s+HEALTHCARE\b|\bGENESIS\s+HEALTH\b", re.I),
     ("genesis_healthcare", "Genesis Healthcare")),
    (re.compile(r"\bTRILOGY\s+(MANAGEMENT|HEALTH|SERVICES)\b", re.I),
     ("trilogy_health_services", "Trilogy Health Services")),
    (re.compile(r"\bAMERICAN\s+SENIOR\s+COMMUNITIES\b", re.I),
     ("american_senior_communities", "American Senior Communities")),
    (re.compile(r"\bEVANGELICAL\s+LUTHERAN\s+GOOD\s+SAMARITAN\b|^GOOD\s+SAMARITAN\s+SOCIETY", re.I),
     ("good_samaritan_society", "Good Samaritan Society")),
    (re.compile(r"\bSANFORD\b", re.I),
     ("sanford_health", "Sanford Health")),
    (re.compile(r"\bLEGACY\s+HEALTHCARE\b", re.I),
     ("legacy_healthcare", "Legacy Healthcare")),
    (re.compile(r"\bPRESTIGE\s+(ADMIN|CARE|HEALTHCARE)\b", re.I),
     ("prestige_care", "Prestige Care")),
    (re.compile(r"\bPROVIDENCE\s+GROUP\s+NH\b", re.I),
     ("providence_group_snf", "Providence Group SNF")),

    # Other major operators / brands
    (re.compile(r"\bSABER\s+GOVERN|\bSABER\s+HEALTH\b", re.I),
     ("saber_healthcare", "Saber Healthcare Group")),
    (re.compile(r"\bCONSULATE\s+HEALTH", re.I),
     ("consulate_health_care", "Consulate Health Care")),
    (re.compile(r"\bPRUITTHEALTH\b|\bPRUITT\s+HEALTH\b", re.I),
     ("pruitt_health", "PruittHealth")),
    (re.compile(r"\bMANOR\s*CARE\b|\bMANORCARE\b|\bPROMEDICA\s+SENIOR\b|\bHCR\s+MANOR", re.I),
     ("promedica_manorcare", "ProMedica / ManorCare")),
    (re.compile(r"\bSAVA(SENIOR)?\s*CARE\b|\bSAVA\s+SENIOR\b", re.I),
     ("sava_senior_care", "SavaSeniorCare")),
    (re.compile(r"\bDIVERSICARE\b", re.I),
     ("diversicare", "Diversicare")),
    (re.compile(r"\bSIGNATURE\s+HEALTHCARE\b|\bSIGNATURE\s+HEALTH\b", re.I),
     ("signature_healthcare", "Signature HealthCARE")),
    (re.compile(r"\bCOMMUNICARE\b", re.I),
     ("communicare", "CommuniCare Health Services")),
    (re.compile(r"\bBROOKDALE\b", re.I),
     ("brookdale_senior_living", "Brookdale Senior Living")),
    (re.compile(r"\bFIVE\s+STAR\s+(SENIOR|QUALITY)\b", re.I),
     ("five_star_senior_living", "Five Star Senior Living")),
    (re.compile(r"\bSHG\s+(MANAGEMENT|HEALTHCARE)\b", re.I),
     ("shg_management", "SHG Management")),
    (re.compile(r"\bCURIS\s+SERVICES\b", re.I),
     ("curis_health", "Curis Health")),
    (re.compile(r"\bCODY\s+HEALTHCARE\b", re.I),
     ("cody_healthcare", "Cody Healthcare")),
    (re.compile(r"\bCTR\s+PARTNERSHIP\b", re.I),
     ("ctr_partnership", "CTR Partnership")),
    (re.compile(r"\bATRIA\s+SENIOR\b|^ATRIA\b", re.I),
     ("atria_senior_living", "Atria Senior Living")),
    (re.compile(r"\bSUNRISE\s+SENIOR\b", re.I),
     ("sunrise_senior_living", "Sunrise Senior Living")),

    # Hospital-system extensions into SNF
    (re.compile(r"\bKAISER\s+(FOUNDATION|PERMANENTE)\b", re.I),
     ("kaiser_permanente", "Kaiser Permanente")),
    (re.compile(r"\bSUTTER\b", re.I),
     ("sutter_health", "Sutter Health")),
    (re.compile(r"\bPROVIDENCE\s+(HEALTH|SERVICES|HOSPICE)\b", re.I),
     ("providence", "Providence")),
    (re.compile(r"\bCLEVELAND\s+CLINIC\b", re.I),
     ("cleveland_clinic", "Cleveland Clinic")),
    (re.compile(r"\bMAYO\s+CLINIC\b", re.I),
     ("mayo_clinic", "Mayo Clinic")),
    (re.compile(r"\bASCENSION\b", re.I),
     ("ascension", "Ascension")),
    (re.compile(r"\bTRINITY\s+HEALTH\b", re.I),
     ("trinity_health", "Trinity Health")),
    (re.compile(r"\bCOMMONSPIRIT\b|\bDIGNITY\s+HEALTH\b", re.I),
     ("commonspirit", "CommonSpirit Health")),
    (re.compile(r"\bMASS\s+GENERAL\s+BRIGHAM\b", re.I),
     ("mass_general_brigham", "Mass General Brigham")),
    (re.compile(r"\bUPMC\b", re.I),
     ("upmc", "UPMC")),
    (re.compile(r"\bHCA\s+(HEALTHCARE|HOSPICE|HOME)\b", re.I),
     ("hca", "HCA")),
    (re.compile(r"\bINTERMOUNTAIN\b", re.I),
     ("intermountain_health", "Intermountain Health")),
]


def normalize_owner(name: str) -> tuple[str, str] | None:
    """Map a PECOS owner name to a Florence chain slug. None if no match."""
    if not isinstance(name, str):
        return None
    if EXCLUSION_PATTERNS.search(name):
        return None
    for pat, (slug, display) in CHAIN_NORMALIZATIONS:
        if pat.search(name):
            return (slug, display)
    return None


def primary_operator_for(group: pd.DataFrame) -> tuple[str, str] | None:
    """Given all owner-rows for a single CCN, return the (slug, display)
    of the primary chain operator, or None if no chain matched."""
    org_rows = group[group["owner_type"] == "Organization"].copy()
    if len(org_rows) == 0:
        return None

    # Parse ownership_pct ("5%" → 5.0)
    def parse_pct(s: object) -> float:
        if not isinstance(s, str):
            return 0.0
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        return float(m.group(1)) if m else 0.0

    org_rows["pct_num"] = org_rows["ownership_pct"].apply(parse_pct)
    # Try chain matching on each org name; pick the highest-stake match
    matches: list[tuple[float, tuple[str, str]]] = []
    for _, row in org_rows.iterrows():
        result = normalize_owner(row["owner_name"])
        if result is not None:
            matches.append((float(row["pct_num"]), result))
    if not matches:
        return None
    # Highest-stake match wins
    matches.sort(key=lambda x: -x[0])
    return matches[0][1]


def main() -> None:
    print(f"Reading PECOS ownership: {PECOS_NH}")
    ownership = pd.read_csv(
        PECOS_NH,
        dtype={"CMS Certification Number (CCN)": str},
        low_memory=False,
    )
    ownership.columns = [
        "ccn", "name", "address", "city", "state", "zip", "role",
        "owner_type", "owner_name", "ownership_pct",
        "association_date", "location", "processing_date",
    ]
    ownership["ccn"] = ownership["ccn"].astype(str).str.zfill(6)
    print(f"  {len(ownership):,} ownership rows for {ownership['ccn'].nunique():,} unique SNFs")

    # Group by CCN and find the primary operator
    print("Resolving primary operator per CCN...")
    operator_map: dict[str, tuple[str, str]] = {}
    for ccn, group in ownership.groupby("ccn"):
        result = primary_operator_for(group)
        if result is not None:
            operator_map[ccn] = result
    print(f"  PECOS-confirmed chain operators: {len(operator_map):,} SNFs")
    print()

    # Apply to non_hospital_facilities.csv
    fac = pd.read_csv(FACILITIES, dtype={"ccn": str})
    fac["ccn"] = fac["ccn"].astype(str).str.zfill(6)
    n_before = (fac["health_system_id"] != "independent").sum()

    # Back up
    backup = FACILITIES.with_suffix(f".bak_pecos_{date.today().isoformat()}.csv")
    if not backup.exists():
        shutil.copy(FACILITIES, backup)
        print(f"Backed up → {backup}")

    # Apply (only to SNFs)
    snf_mask = fac["facility_type"] == "SNF"
    n_updated = 0
    for idx in fac[snf_mask].index:
        ccn = fac.at[idx, "ccn"]
        if ccn in operator_map:
            slug, display = operator_map[ccn]
            fac.at[idx, "health_system_id"] = slug
            fac.at[idx, "health_system"] = display
            n_updated += 1
    print(f"Applied {n_updated:,} PECOS-derived chain assignments to SNFs")

    n_after = (fac["health_system_id"] != "independent").sum()
    print()
    print("=== Top 25 SNF chains after PECOS merge ===")
    snfs = fac[fac["facility_type"] == "SNF"]
    top = (
        snfs[snfs["health_system_id"] != "independent"]
        .groupby(["health_system_id", "health_system"])
        .size()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
        .head(25)
    )
    for _, r in top.iterrows():
        print(f"  {r['n']:>5,}  {r['health_system']}")

    print()
    print(f"Total non-hospital chain-assigned: {n_before:,} → {n_after:,} (+{n_after-n_before:,})")

    fac.to_csv(FACILITIES, index=False)
    print(f"\n✓ Updated {FACILITIES}")
    print(f"  Backup retained at {backup}")

    # Also regen non_hospital_priced.parquet
    print("\nRegenerating non_hospital_priced.parquet...")
    from non_hospital_pricing import price_non_hospital, NonHospitalCalibration
    priced = price_non_hospital(fac, NonHospitalCalibration(target_offset_pct=0.40))
    priced_path = DATA / "non_hospital_priced.parquet"
    priced.to_parquet(priced_path, index=False)
    print(f"✓ Wrote {priced_path}")


if __name__ == "__main__":
    main()
