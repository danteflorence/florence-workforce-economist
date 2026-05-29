"""
Chain-ownership pattern catalog for non-hospital care settings.

CMS data doesn't include chain affiliation for ASCs / HHAs / SNFs / Hospices /
Dialysis. NASHP only covers hospitals. So we name-pattern-match against the
30+ major national chains using their distinctive naming conventions.

Coverage from name matching alone is ~30-40% of the non-hospital universe.
The remainder defaults to Independent / Unknown. Reps can patch the long tail
via the System Ownership tab (search + reassign or bulk CSV import).

Each entry: slug → (display_name, [regex patterns], facility_types it applies to)
Patterns are tested case-insensitively against the facility name.

Hospital-system overlaps (e.g. Sutter Care at Home → sutter_health) intentionally
use the SAME slug as in the hospital universe so cross-setting rollups work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChainPattern:
    slug: str
    display: str
    patterns: tuple[re.Pattern, ...]
    applies_to: tuple[str, ...] = ("ASC", "HHA", "SNF", "HOSPICE", "DIALYSIS")


def _pat(*regex_strings: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(r, re.IGNORECASE) for r in regex_strings)


CHAIN_CATALOG: list[ChainPattern] = [
    # ─── DIALYSIS ──────────────────────────────────────────────────────
    ChainPattern("davita", "DaVita Kidney Care",
                 _pat(r"\bdavita\b"), ("DIALYSIS",)),
    ChainPattern("fresenius_kidney_care", "Fresenius Kidney Care",
                 _pat(r"^FMC\b", r"\bfresenius\b", r"FMC\s*[-—]"),
                 ("DIALYSIS",)),
    ChainPattern("dialysis_clinic_inc", "Dialysis Clinic Inc (DCI)",
                 _pat(r"^DCI\b", r"^DCI\s+", r"Dialysis Clinic.*Inc"),
                 ("DIALYSIS",)),
    ChainPattern("us_renal_care", "U.S. Renal Care",
                 _pat(r"U\.?S\.?\s*Renal\s*Care", r"^US\s+Renal\b"),
                 ("DIALYSIS",)),
    ChainPattern("innovative_renal_care", "Innovative Renal Care",
                 _pat(r"Innovative\s+Renal\s+Care"), ("DIALYSIS",)),
    ChainPattern("satellite_healthcare", "Satellite Healthcare",
                 _pat(r"^Satellite\s+(Health|Dialysis)"), ("DIALYSIS",)),
    ChainPattern("northwest_kidney_centers", "Northwest Kidney Centers",
                 _pat(r"Northwest\s+Kidney\s+Centers?"), ("DIALYSIS",)),

    # ─── HOME HEALTH (HHA) ─────────────────────────────────────────────
    ChainPattern("centerwell_home_health", "CenterWell Home Health",
                 _pat(r"\bCenterWell\b", r"\bKindred\s+at\s+Home\b"), ("HHA",)),
    ChainPattern("enhabit_home_health", "Enhabit Home Health",
                 _pat(r"\bEnhabit\b"), ("HHA", "HOSPICE")),
    ChainPattern("encompass_health", "Encompass Health",
                 _pat(r"\bEncompass\s+Health\b"), ("HHA",)),
    ChainPattern("amedisys", "Amedisys",
                 _pat(r"\bAmedisys\b"), ("HHA", "HOSPICE")),
    ChainPattern("lhc_group", "LHC Group",
                 _pat(r"^LHC\b", r"\bLHC\s+Group\b"), ("HHA", "HOSPICE")),
    ChainPattern("bayada", "BAYADA Home Health Care",
                 _pat(r"\bBAYADA\b"), ("HHA", "HOSPICE")),
    ChainPattern("interim_healthcare", "Interim HealthCare",
                 _pat(r"\bInterim\s+Health\s*[Cc]are\b"), ("HHA", "HOSPICE")),
    ChainPattern("accentcare", "AccentCare",
                 _pat(r"\bAccentCare\b"), ("HHA", "HOSPICE")),
    ChainPattern("aveanna_healthcare", "Aveanna Healthcare",
                 _pat(r"\bAveanna\b"), ("HHA", "HOSPICE")),
    ChainPattern("brookdale_home_health", "Brookdale Healthcare Services",
                 _pat(r"\bBrookdale\s+Health"), ("HHA",)),

    # ─── SKILLED NURSING (SNF) ─────────────────────────────────────────
    ChainPattern("brookdale_senior_living", "Brookdale Senior Living",
                 _pat(r"^Brookdale\b", r"\bBrookdale\s+(at|of|Senior)\b"),
                 ("SNF",)),
    ChainPattern("genesis_healthcare", "Genesis Healthcare",
                 _pat(r"^Genesis\s+Health", r"\bGenesis\s+Health[Cc]are\b"),
                 ("SNF", "HHA", "HOSPICE")),
    ChainPattern("life_care_centers", "Life Care Centers of America",
                 _pat(r"\bLife\s+Care\s+Center"), ("SNF",)),
    ChainPattern("consulate_health_care", "Consulate Health Care",
                 _pat(r"\bConsulate\s+Health\s*[Cc]are\b"), ("SNF",)),
    ChainPattern("trilogy_health_services", "Trilogy Health Services",
                 _pat(r"\bTrilogy\s+Health\b"), ("SNF",)),
    ChainPattern("ensign_group", "The Ensign Group",
                 _pat(r"\bEnsign\s+Group\b", r"^Ensign\s+"), ("SNF",)),
    ChainPattern("promedica_manorcare", "ProMedica / ManorCare",
                 _pat(r"\bManor\s*[Cc]are\b", r"\bManorCare\b",
                      r"\bHeartland\s+(Health\s*Care|Hospice)\b"),
                 ("SNF", "HHA", "HOSPICE")),
    ChainPattern("pruitt_health", "PruittHealth",
                 _pat(r"\bPruittHealth\b", r"\bPruitt\s+Health\b",
                      r"^PRUITT\s+"), ("SNF", "HHA", "HOSPICE")),
    ChainPattern("sava_senior_care", "SavaSeniorCare",
                 _pat(r"\bSavaSeniorCare\b", r"\bSava\s+Senior\b"), ("SNF",)),
    ChainPattern("diversicare", "Diversicare",
                 _pat(r"\bDiversicare\b"), ("SNF",)),
    ChainPattern("signature_healthcare", "Signature HealthCARE",
                 _pat(r"\bSignature\s+HealthCare\b", r"\bSignature\s+Health[Cc]are\b"),
                 ("SNF",)),
    ChainPattern("communicare", "CommuniCare Health Services",
                 _pat(r"\bCommuniCare\b"), ("SNF",)),
    ChainPattern("five_star_senior_living", "Five Star Senior Living",
                 _pat(r"\bFive\s+Star\s+Senior\b"), ("SNF",)),
    ChainPattern("atria_senior_living", "Atria Senior Living",
                 _pat(r"^Atria\b", r"\bAtria\s+(at|of)\b"), ("SNF",)),
    ChainPattern("sunrise_senior_living", "Sunrise Senior Living",
                 _pat(r"^Sunrise\s+of\b", r"^Sunrise\s+Senior\b"), ("SNF",)),
    ChainPattern("good_samaritan_society", "Good Samaritan Society",
                 _pat(r"^Good\s+Samaritan\s+Society",
                      r"\bGood\s+Samaritan\s+Society\b"), ("SNF",)),

    # ─── HOSPICE ───────────────────────────────────────────────────────
    ChainPattern("vitas_healthcare", "VITAS Healthcare",
                 _pat(r"\bVITAS\b"), ("HOSPICE",)),
    ChainPattern("compassus", "Compassus",
                 _pat(r"\bCompassus\b"), ("HOSPICE", "HHA")),
    ChainPattern("elara_caring", "Elara Caring",
                 _pat(r"\bElara\s+Caring\b"), ("HOSPICE", "HHA")),
    ChainPattern("aseracare", "AseraCare",
                 _pat(r"\bAseraCare\b"), ("HOSPICE",)),
    ChainPattern("suncrest_hospice", "Suncrest Hospice",
                 _pat(r"\bSuncrest\s+Hospice\b"), ("HOSPICE",)),
    ChainPattern("crossroads_hospice", "Crossroads Hospice & Palliative Care",
                 _pat(r"\bCrossroads\s+Hospice\b"), ("HOSPICE",)),
    ChainPattern("hospice_of_the_valley", "Hospice of the Valley",
                 _pat(r"\bHospice\s+of\s+the\s+Valley\b"), ("HOSPICE",)),

    # ─── ASCs ──────────────────────────────────────────────────────────
    ChainPattern("uspi", "United Surgical Partners International (Tenet)",
                 _pat(r"\bUSPI\b", r"United\s+Surgical\s+Partners"), ("ASC",)),
    ChainPattern("surgery_partners", "Surgery Partners",
                 _pat(r"\bSurgery\s+Partners\b", r"\bNational\s+Surgical\s+Healthcare\b"),
                 ("ASC",)),
    ChainPattern("sca_health", "SCA Health (Optum)",
                 _pat(r"\bSCA\s+(Health|Surgical)\b", r"Surgical\s+Care\s+Affiliates"),
                 ("ASC",)),
    ChainPattern("amsurg_envision", "AmSurg / Envision",
                 _pat(r"\bAmSurg\b", r"\bEnvision\s+Surg"), ("ASC",)),

    # ─── Hospital-system extensions into non-hospital ───────────────────
    # (Use existing slugs so rollups merge across settings.)
    ChainPattern("kaiser_permanente", "Kaiser Permanente",
                 _pat(r"\bKaiser\s+Permanente\b",
                      r"\bKaiser\s+Foundation\b")),
    ChainPattern("sutter_health", "Sutter Health",
                 _pat(r"\bSutter\b\s+(Care|Health|Hospice)")),
    ChainPattern("hca", "HCA",
                 _pat(r"\bHCA\s+(Healthcare|Florida|Texas|Virginia|of)\b")),
    ChainPattern("cleveland_clinic", "Cleveland Clinic",
                 _pat(r"\bCleveland\s+Clinic\b")),
    ChainPattern("mass_general_brigham", "Mass General Brigham",
                 _pat(r"\bMass\s+General\s+Brigham\b",
                      r"\bMassachusetts\s+General\s+Hospital\b")),
    ChainPattern("northwell_health", "Northwell Health",
                 _pat(r"^Northwell\b", r"\bNorthwell\s+Health\b")),
    ChainPattern("providence", "Providence",
                 _pat(r"^Providence\s+(Home|Hospice|Health|Saint)\b")),
    ChainPattern("intermountain_health", "Intermountain Health",
                 _pat(r"\bIntermountain\s+(Health|Home|Hospice)\b")),
    ChainPattern("ascension", "Ascension",
                 _pat(r"\bAscension\s+(at\s+Home|Care|Hospice|Home)\b")),
    ChainPattern("trinity_health", "Trinity Health",
                 _pat(r"\bTrinity\s+Health\b", r"\bMercy\s+Home\s+Health\b")),
    ChainPattern("commonspirit", "CommonSpirit Health",
                 _pat(r"\bCommonSpirit\b", r"\bDignity\s+Health\b")),
    ChainPattern("baylor_scott_white", "Baylor Scott & White",
                 _pat(r"\bBaylor\s+Scott\b")),
    ChainPattern("upmc", "UPMC",
                 _pat(r"^UPMC\b", r"\bUPMC\s+(Home|Hospice|Senior|Skilled)\b")),
    ChainPattern("mayo_clinic", "Mayo Clinic",
                 _pat(r"\bMayo\s+Clinic\b")),
]


def assign_chain(name: str, facility_type: str) -> tuple[str, str] | None:
    """Return (slug, display_name) for a matching chain pattern, or None."""
    if not isinstance(name, str):
        return None
    for entry in CHAIN_CATALOG:
        if facility_type not in entry.applies_to:
            continue
        for pat in entry.patterns:
            if pat.search(name):
                return (entry.slug, entry.display)
    return None


def apply_chain_matching(facilities: pd.DataFrame) -> pd.DataFrame:
    """Update health_system_id + health_system in-place style.
    Returns new DataFrame. Only overrides rows currently flagged Independent."""
    df = facilities.copy()
    new_slug = []
    new_disp = []
    for name, ft, cur_slug in zip(df["name"], df["facility_type"], df["health_system_id"]):
        if cur_slug not in (None, "", "independent"):
            new_slug.append(cur_slug)
            new_disp.append(df.loc[df["health_system_id"] == cur_slug, "health_system"].iloc[0]
                            if len(df[df["health_system_id"] == cur_slug]) else "Independent / Unknown")
            continue
        result = assign_chain(name, ft)
        if result is None:
            new_slug.append("independent")
            new_disp.append("Independent / Unknown")
        else:
            new_slug.append(result[0])
            new_disp.append(result[1])
    df["health_system_id"] = new_slug
    df["health_system"] = new_disp
    return df


def main() -> None:
    """Apply chain matching to non_hospital_facilities.csv and report stats."""
    from pathlib import Path
    DATA = Path(__file__).parent / "data"
    src = DATA / "non_hospital_facilities.csv"
    print(f"Reading {src}")
    fac = pd.read_csv(src, dtype={"ccn": str})
    n_before = (fac["health_system_id"] != "independent").sum()

    fac = apply_chain_matching(fac)

    n_after = (fac["health_system_id"] != "independent").sum()
    print(f"  Chain-assigned: {n_before:,} → {n_after:,} (+{n_after - n_before:,})")
    print(f"  Independent: {(fac['health_system_id'] == 'independent').sum():,}")
    print()
    print("=== Top 25 chains across non-hospital universe ===")
    top = (
        fac[fac["health_system_id"] != "independent"]
        .groupby(["health_system_id", "health_system"])
        .agg(n=("ccn", "count"),
             by_type=("facility_type", lambda s: ", ".join(
                 [f"{k}={v}" for k, v in s.value_counts().items()])))
        .reset_index()
        .sort_values("n", ascending=False)
        .head(25)
    )
    for _, r in top.iterrows():
        print(f"  {r['n']:>5,}  {r['health_system']:<40}  {r['by_type']}")

    fac.to_csv(src, index=False)
    print(f"\n✓ Updated {src}")

    # Also regenerate the priced parquet so the Streamlit tab picks up new ownership
    print("\nRegenerating non_hospital_priced.parquet…")
    from non_hospital_pricing import price_non_hospital
    priced = price_non_hospital(fac)
    out = DATA / "non_hospital_priced.parquet"
    priced.to_parquet(out, index=False)
    print(f"✓ Wrote {out}")


if __name__ == "__main__":
    main()
