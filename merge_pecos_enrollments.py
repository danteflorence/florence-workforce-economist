"""
Merge CMS PECOS enrollment data into non_hospital_facilities.csv.

PECOS enrollment files have the DOING BUSINESS AS NAME (DBA) which is the
chain brand even when the facility's CMS-registered name is different.
This catches chains like Gentiva (125 hospices, invisible to name matching).

Files used:
  - HHA_Enrollments.csv    — 11.5K Home Health Agency enrollments
  - Hospice_Enrollments.csv — 6K Hospice enrollments
  - SNF_Enrollments.csv     — 14K SNF enrollments (already covered by NH_Ownership;
                              we use PECOS DBA here for stragglers + AFFILIATION)
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
RAW = DATA / "raw_cms_pecos"
FACILITIES = DATA / "non_hospital_facilities.csv"

# DBA / Org name normalization patterns
# Order matters — first match wins
NORMALIZE = [
    # ── HHA ────────────────────────────────────────────────────────────
    (re.compile(r"\bCENTERWELL\b", re.I), ("centerwell_home_health", "CenterWell Home Health")),
    (re.compile(r"\bENHABIT\s+HOME\s+HEALTH\b", re.I), ("enhabit_home_health", "Enhabit Home Health")),
    (re.compile(r"\bENHABIT\s+HOSPICE\b", re.I), ("enhabit_hospice", "Enhabit Hospice")),
    (re.compile(r"\bENCOMPASS\s+HEALTH\b", re.I), ("encompass_health", "Encompass Health")),
    (re.compile(r"\bAMEDISYS\b", re.I), ("amedisys", "Amedisys")),
    (re.compile(r"\bBAYADA\b", re.I), ("bayada", "BAYADA Home Health Care")),
    (re.compile(r"\bAVEANNA\b", re.I), ("aveanna_healthcare", "Aveanna Healthcare")),
    (re.compile(r"\bADORATION\b", re.I), ("adoration_home_health", "Adoration Home Health")),
    (re.compile(r"\bMAXIM\s+HEALTHCARE\b", re.I), ("maxim_healthcare", "Maxim Healthcare")),
    (re.compile(r"\bVITALCARING\b", re.I), ("vitalcaring_group", "VitalCaring Group")),
    (re.compile(r"\bANGELS\s+CARE\b", re.I), ("angels_care_home_health", "Angels Care Home Health")),
    (re.compile(r"\bCONCIERGE\s+HOME\b", re.I), ("concierge_home_care", "Concierge Home Care")),
    (re.compile(r"\bELITE\s+HOME\s+HEALTH\b", re.I), ("elite_home_health", "Elite Home Health")),
    (re.compile(r"\bELITE\s+HOSPICE\b", re.I), ("elite_hospice", "Elite Hospice")),
    (re.compile(r"\bINTERIM\s+HEALTH(CARE)?\b", re.I), ("interim_healthcare", "Interim HealthCare")),
    (re.compile(r"\bACCENTCARE\b", re.I), ("accentcare", "AccentCare")),
    (re.compile(r"\bLHC\s+(GROUP|HOME)\b", re.I), ("lhc_group", "LHC Group")),
    (re.compile(r"\bELARA\s+CARING\b", re.I), ("elara_caring", "Elara Caring")),
    (re.compile(r"\bCOMPASSUS\b", re.I), ("compassus", "Compassus")),

    # ── Hospice ─────────────────────────────────────────────────────────
    (re.compile(r"^GENTIVA\b|\bGENTIVA\s+(HOSPICE|HEALTH)\b", re.I),
     ("gentiva", "Gentiva")),
    (re.compile(r"\bTRADITIONS\s+HEALTH\b", re.I),
     ("traditions_health", "Traditions Health")),
    (re.compile(r"\bST\.?\s+CROIX\s+HOSPICE\b", re.I),
     ("st_croix_hospice", "St Croix Hospice")),
    (re.compile(r"\bASERACARE\b", re.I),
     ("aseracare", "AseraCare")),
    (re.compile(r"\bSUNCREST\s+HOSPICE\b", re.I),
     ("suncrest_hospice", "Suncrest Hospice")),
    (re.compile(r"\bTHREE\s+OAKS\s+HOSPICE\b", re.I),
     ("three_oaks_hospice", "Three Oaks Hospice")),
    (re.compile(r"\bACG\s+HOSPICE\b", re.I),
     ("acg_hospice", "ACG Hospice")),
    (re.compile(r"\bHEART\s+OF\s+HOSPICE\b", re.I),
     ("heart_of_hospice", "Heart of Hospice")),
    (re.compile(r"\bAFFINITY\s+HOSPICE\b", re.I),
     ("affinity_hospice", "Affinity Hospice")),
    (re.compile(r"\bVITAS\b", re.I),
     ("vitas_healthcare", "VITAS Healthcare")),
    (re.compile(r"\bCROSSROADS\s+HOSPICE\b", re.I),
     ("crossroads_hospice", "Crossroads Hospice & Palliative Care")),

    # ── Hospital-system extensions (use existing slugs) ───────────────
    (re.compile(r"\bKAISER\s+(FOUNDATION|PERMANENTE|HOSPICE|HOME)\b", re.I),
     ("kaiser_permanente", "Kaiser Permanente")),
    (re.compile(r"\bSUTTER\s+(CARE|HOME|HOSPICE|HEALTH)\b", re.I),
     ("sutter_health", "Sutter Health")),
    (re.compile(r"\bPROVIDENCE\s+(HOSPICE|HOME|HEALTH|MEDICAL|SAINT)\b", re.I),
     ("providence", "Providence")),
    (re.compile(r"\bASCENSION\s+(AT|HOME|HOSPICE|CARE)\b", re.I),
     ("ascension", "Ascension")),
    (re.compile(r"\bTRINITY\s+HEALTH\b", re.I),
     ("trinity_health", "Trinity Health")),
    (re.compile(r"\bCOMMONSPIRIT\b|\bDIGNITY\s+HEALTH\b", re.I),
     ("commonspirit", "CommonSpirit Health")),
    (re.compile(r"\bUPMC\b", re.I),
     ("upmc", "UPMC")),
    (re.compile(r"\bMAYO\s+CLINIC\b", re.I),
     ("mayo_clinic", "Mayo Clinic")),
    (re.compile(r"\bCLEVELAND\s+CLINIC\b", re.I),
     ("cleveland_clinic", "Cleveland Clinic")),
    (re.compile(r"\bMASS\s+GENERAL\s+BRIGHAM\b", re.I),
     ("mass_general_brigham", "Mass General Brigham")),
    (re.compile(r"\bNORTHWELL\b", re.I),
     ("northwell_health", "Northwell Health")),
    (re.compile(r"\bINTERMOUNTAIN\b", re.I),
     ("intermountain_health", "Intermountain Health")),
]


def normalize_chain(name: str) -> tuple[str, str] | None:
    if not isinstance(name, str):
        return None
    for pat, mapping in NORMALIZE:
        if pat.search(name):
            return mapping
    return None


def build_ccn_to_chain(path: Path, label: str) -> dict[str, tuple[str, str]]:
    """Read PECOS enrollments, return {ccn: (slug, display)} for facilities
    whose DBA or Organization Name matches a known chain pattern."""
    df = pd.read_csv(path, encoding="latin-1", low_memory=False, dtype={"CCN": str})
    df.columns = [c.strip() for c in df.columns]
    df["CCN"] = df["CCN"].astype(str).str.zfill(6)
    # Prefer DBA (chain brand); fall back to Organization Name
    df["chain_signal"] = df["DOING BUSINESS AS NAME"].fillna(df["ORGANIZATION NAME"]).fillna("")
    out: dict[str, tuple[str, str]] = {}
    n_matched = 0
    for _, row in df.iterrows():
        ccn = row["CCN"]
        if ccn in ("000000", "nan", "NaN"):
            continue
        result = normalize_chain(row["chain_signal"])
        if result is not None:
            out[ccn] = result
            n_matched += 1
    print(f"  {label}: {len(df):,} enrollments → {n_matched:,} chain-mapped CCNs")
    return out


def main() -> None:
    print("Loading PECOS enrollments...")
    hha_map = build_ccn_to_chain(RAW / "HHA_Enrollments.csv", "HHA")
    hospice_map = build_ccn_to_chain(RAW / "Hospice_Enrollments.csv", "Hospice")
    print()

    # Merge into non_hospital_facilities.csv
    fac = pd.read_csv(FACILITIES, dtype={"ccn": str})
    fac["ccn"] = fac["ccn"].astype(str).str.zfill(6)
    n_before = (fac["health_system_id"] != "independent").sum()

    # Back up
    backup = FACILITIES.with_suffix(f".bak_pecos_enrollments_{date.today().isoformat()}.csv")
    if not backup.exists():
        shutil.copy(FACILITIES, backup)
        print(f"Backed up → {backup}")

    # Apply per facility type
    n_hha_updated = 0
    n_hospice_updated = 0
    for idx in fac.index:
        ccn = fac.at[idx, "ccn"]
        ft = fac.at[idx, "facility_type"]
        if ft == "HHA" and ccn in hha_map:
            slug, display = hha_map[ccn]
            fac.at[idx, "health_system_id"] = slug
            fac.at[idx, "health_system"] = display
            n_hha_updated += 1
        elif ft == "HOSPICE" and ccn in hospice_map:
            slug, display = hospice_map[ccn]
            fac.at[idx, "health_system_id"] = slug
            fac.at[idx, "health_system"] = display
            n_hospice_updated += 1

    print(f"PECOS-derived chain assignments:")
    print(f"  HHA:     {n_hha_updated:,}")
    print(f"  Hospice: {n_hospice_updated:,}")

    n_after = (fac["health_system_id"] != "independent").sum()
    print()
    print(f"Total non-hospital chain-assigned: {n_before:,} → {n_after:,} (+{n_after-n_before:,})")
    print()
    print("=== Top 15 HHA chains after PECOS merge ===")
    hha_top = (
        fac[(fac["facility_type"] == "HHA") & (fac["health_system_id"] != "independent")]
        .groupby("health_system").size().sort_values(ascending=False).head(15)
    )
    for name, n in hha_top.items():
        print(f"  {n:>4}  {name}")
    print()
    print("=== Top 15 Hospice chains after PECOS merge ===")
    hospice_top = (
        fac[(fac["facility_type"] == "HOSPICE") & (fac["health_system_id"] != "independent")]
        .groupby("health_system").size().sort_values(ascending=False).head(15)
    )
    for name, n in hospice_top.items():
        print(f"  {n:>4}  {name}")

    fac.to_csv(FACILITIES, index=False)
    print(f"\n✓ Updated {FACILITIES}")

    # Regen priced parquet
    print("\nRegenerating non_hospital_priced.parquet...")
    from non_hospital_pricing import price_non_hospital, NonHospitalCalibration
    priced = price_non_hospital(fac, NonHospitalCalibration(target_offset_pct=0.40))
    priced.to_parquet(DATA / "non_hospital_priced.parquet", index=False)
    print(f"✓ Wrote {DATA / 'non_hospital_priced.parquet'}")


if __name__ == "__main__":
    main()
