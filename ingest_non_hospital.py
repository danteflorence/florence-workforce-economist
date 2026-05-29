"""
Ingest CMS provider data for non-hospital care settings:
  - Ambulatory Surgery Centers (ASCs)
  - Home Health Agencies (HHAs)
  - Skilled Nursing Facilities (SNFs)
  - Hospices
  - Dialysis Facilities (bonus — labor-constrained, FICA-savings story strong)

For each, produces a unified `data/non_hospital_facilities.csv` with the same
join schema as `hospital_universe.csv` plus:
  - facility_type  ∈ {ASC, HHA, SNF, HOSPICE, DIALYSIS}
  - rn_estimate    (RN headcount from setting-specific rule)
  - rn_wage_hourly (BLS state-level RN wage; MSA refinement later)
  - capacity_revenue_per_rn_annual (incremental gross revenue per added RN)

Joined into the main universe via `assemble_full_universe.py` (next step).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
RAW = DATA / "raw_cms_non_hospital"


# --- Setting-specific RN-headcount + capacity-revenue rules ----------------
# Each row: (facility_type, default_rn_estimate, annual_revenue_per_rn,
#           rn_per_bed if bed-driven, comment)
SETTING_RULES = {
    "ASC": {
        # ASCs typically run 2-4 ORs, ~5 RNs (1 circulator + 2 PACU + 1-2 pre-op)
        "rn_default": 5,
        "rn_per_or": 2,  # if we ever get OR count, override
        "revenue_per_rn_annual": 400_000,
        "comment": "1 circulator/OR + PACU + pre-op; per ASC industry surveys",
    },
    "HHA": {
        # HHA RN count varies wildly with census; median ~10 RNs/agency
        "rn_default": 10,
        "revenue_per_rn_annual": 300_000,
        "comment": "Median HHA carries ~50 census/RN; gross episode revenue ~$3.2K",
    },
    "SNF": {
        # SNF: ~0.3 RN per 10 certified beds is the operational reality
        # (regulatory minimum is 8h/day RN coverage = 0.08 FTE per facility minimum)
        "rn_default": 5,
        "rn_per_bed": 0.03,    # 100 beds → ~3 RN FTE + relief
        "revenue_per_rn_annual": 200_000,
        "comment": "CMS minimum staffing + relief; reimbursement-capped",
    },
    "HOSPICE": {
        "rn_default": 5,
        "revenue_per_rn_annual": 250_000,
        "comment": "Hospice case manager model, ADC-driven",
    },
    "DIALYSIS": {
        "rn_default": 6,
        "revenue_per_rn_annual": 280_000,
        "comment": "Typical 12-chair center, 4 RN per shift × 1.5 relief",
    },
}


def _read_normalized(path: Path, ccn_col: str, name_col: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, dtype={ccn_col: str})
    df[ccn_col] = df[ccn_col].astype(str).str.strip()
    # Most CMS CCNs are 6 chars; ASCs use 6-char IDs too
    df["ccn"] = df[ccn_col].str.zfill(6)
    return df


def load_asc() -> pd.DataFrame:
    df = _read_normalized(RAW / "ASC_Facility.csv", "Facility ID", "Facility Name")
    df = df.rename(columns={
        "Facility Name": "name",
        "City/Town": "city",
        "State": "state",
        "ZIP Code": "zip",
    })
    # ASC file has one row per facility per measure; dedupe to facility
    df = df.drop_duplicates("ccn", keep="first").copy()
    df["facility_type"] = "ASC"
    df["ownership_type"] = ""
    # ASC files don't include beds; use defaults
    df["rn_estimate"] = SETTING_RULES["ASC"]["rn_default"]
    return df[["ccn", "name", "city", "state", "zip", "facility_type",
               "ownership_type", "rn_estimate"]]


def load_hha() -> pd.DataFrame:
    df = _read_normalized(RAW / "HH_Provider.csv", "CMS Certification Number (CCN)", "Provider Name")
    df = df.rename(columns={
        "Provider Name": "name",
        "City/Town": "city",
        "State": "state",
        "ZIP Code": "zip",
        "Type of Ownership": "ownership_type",
    })
    df = df.drop_duplicates("ccn", keep="first").copy()
    df["facility_type"] = "HHA"
    df["rn_estimate"] = SETTING_RULES["HHA"]["rn_default"]
    return df[["ccn", "name", "city", "state", "zip", "facility_type",
               "ownership_type", "rn_estimate"]]


def load_snf() -> pd.DataFrame:
    df = _read_normalized(RAW / "NH_Provider.csv", "CMS Certification Number (CCN)", "Provider Name")
    df = df.rename(columns={
        "Provider Name": "name",
        "City/Town": "city",
        "State": "state",
        "ZIP Code": "zip",
        "Ownership Type": "ownership_type",
    })
    # SNFs have certified bed count → use bed-driven rule
    beds_col = "Number of Certified Beds"
    df["beds"] = pd.to_numeric(df.get(beds_col), errors="coerce").fillna(100)
    rn_per_bed = SETTING_RULES["SNF"]["rn_per_bed"]
    rn_default = SETTING_RULES["SNF"]["rn_default"]
    df["rn_estimate"] = (df["beds"] * rn_per_bed).clip(lower=rn_default).round().astype(int)
    df = df.drop_duplicates("ccn", keep="first").copy()
    df["facility_type"] = "SNF"
    return df[["ccn", "name", "city", "state", "zip", "facility_type",
               "ownership_type", "rn_estimate"]]


def load_hospice() -> pd.DataFrame:
    df = _read_normalized(RAW / "Hospice_General.csv", "CMS Certification Number (CCN)", "Facility Name")
    df = df.rename(columns={
        "Facility Name": "name",
        "City/Town": "city",
        "State": "state",
        "ZIP Code": "zip",
        "Ownership Type": "ownership_type",
    })
    df = df.drop_duplicates("ccn", keep="first").copy()
    df["facility_type"] = "HOSPICE"
    df["rn_estimate"] = SETTING_RULES["HOSPICE"]["rn_default"]
    return df[["ccn", "name", "city", "state", "zip", "facility_type",
               "ownership_type", "rn_estimate"]]


def load_dialysis() -> pd.DataFrame:
    df = _read_normalized(RAW / "Dialysis_Facility.csv", "CMS Certification Number (CCN)", "Facility Name")
    df = df.rename(columns={
        "Facility Name": "name",
        "City/Town": "city",
        "State": "state",
        "ZIP Code": "zip",
        "Profit or Non-Profit": "ownership_type",
    })
    if "ownership_type" not in df.columns:
        df["ownership_type"] = ""
    df = df.drop_duplicates("ccn", keep="first").copy()
    df["facility_type"] = "DIALYSIS"
    df["rn_estimate"] = SETTING_RULES["DIALYSIS"]["rn_default"]
    return df[["ccn", "name", "city", "state", "zip", "facility_type",
               "ownership_type", "rn_estimate"]]


def attach_wage(df: pd.DataFrame) -> pd.DataFrame:
    """Join state-level BLS RN wage. (MSA-level refinement would be nicer
    but requires ZIP→CBSA lookup; doing state for now.)"""
    states = pd.read_csv(DATA / "state_benchmarks.csv")
    states = states[["state", "rn_wage"]].rename(columns={"rn_wage": "rn_wage_hourly"})
    return df.merge(states, on="state", how="left")


def attach_revenue_per_rn(df: pd.DataFrame) -> pd.DataFrame:
    """Add capacity_revenue_per_rn_annual based on facility_type."""
    rev_map = {ft: r["revenue_per_rn_annual"] for ft, r in SETTING_RULES.items()}
    df["capacity_revenue_per_rn_annual"] = df["facility_type"].map(rev_map)
    return df


def main() -> None:
    print("Ingesting non-hospital facilities…")
    parts = []
    for loader, label in [
        (load_asc, "ASC"),
        (load_hha, "HHA"),
        (load_snf, "SNF"),
        (load_hospice, "HOSPICE"),
        (load_dialysis, "DIALYSIS"),
    ]:
        df = loader()
        print(f"  {label:<10} {len(df):>6,} facilities  "
              f"(median RN estimate: {df['rn_estimate'].median():.0f})")
        parts.append(df)

    all_nh = pd.concat(parts, ignore_index=True)
    all_nh["zip"] = all_nh["zip"].astype(str).str.zfill(5).str[:5]
    all_nh = attach_wage(all_nh)
    all_nh = attach_revenue_per_rn(all_nh)

    # Default health_system = Independent (we don't have ownership chains yet
    # for non-hospital; the System Ownership tab + bulk CSV import lets reps
    # patch in known chains like USPI/Encompass/Genesis/DaVita/Fresenius)
    all_nh["health_system_id"] = "independent"
    all_nh["health_system"] = "Independent / Unknown"

    out = DATA / "non_hospital_facilities.csv"
    all_nh.to_csv(out, index=False)
    print(f"\n✓ Wrote {out}")
    print(f"  Total non-hospital facilities: {len(all_nh):,}")
    print(f"  By type:")
    for ft, n in all_nh["facility_type"].value_counts().items():
        median_wage = all_nh.loc[all_nh["facility_type"] == ft, "rn_wage_hourly"].median()
        rev = SETTING_RULES[ft]["revenue_per_rn_annual"]
        print(f"    {ft:<10} {n:>6,}  median wage ${median_wage:>5.2f}/hr  "
              f"${rev/1000:.0f}K rev/RN/yr")
    print(f"\n  Aggregate addressable RN capacity: {all_nh['rn_estimate'].sum():,.0f}")


if __name__ == "__main__":
    main()
