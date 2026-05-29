"""
HCRIS Hospital Cost Report parser.

Reads the CMS-aggregated Hospital Provider Cost Report file (one row per
hospital cost report, ~6,100 rows for 2023) and extracts per-hospital labor
economics fields.

Source dataset: "Hospital Provider Cost Report" on data.cms.gov.
Identifier: 44060663-47d8-4ced-a115-b53b4c270acb
Current download:
    https://data.cms.gov/sites/default/files/2026-01/
    3c39f483-c7e0-4025-8396-4df76942e10f/CostReport_2023_Final.csv

What this file provides per hospital:
    ✓ Total salaries from Worksheet A           (DOLLARS, ~99% coverage)
    ✓ Wage-related costs (core)                 (DOLLARS, ~59% coverage)
    ✓ FTE - Employees on Payroll                (HEADCOUNT, ~98% coverage)
    ✓ Contract Labor: Direct Patient Care       (DOLLARS, ~50% coverage)
    ✓ Beds, patient days, Net Patient Revenue, Total Costs
    ✗ Contract labor HOURS                      (NOT in this aggregated file)
    ✗ Contract labor by OCCUPATION              (NOT in this aggregated file)
    ✗ Wages by OCCUPATION (RN/LPN/etc.)         (NOT in this aggregated file)

Getting hours + occupation breakdown requires parsing raw HCRIS NMRC files:
    https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports/Hospital-2010-form
And joining HOSP10_YYYY_NMRC.CSV (line items) to HOSP10_YYYY_RPT.CSV (report-
to-CCN mapping) on rpt_rec_num. That's the v2 of this ingest.

Outputs per CCN:
    - taxable_wage_per_hour (from total salaries / FTE / 2080)
    - benefit_load_per_hour (from wage-related / FTE / 2080)
    - loaded_staff_cost_per_hour (W + B + 7.65% employer FICA)
    - contract_labor_dollars
    - contract_labor_share (contract labor / (total_salaries + contract_labor))
    - estimated_rn_need_fte (refined from FTE × nursing share)
    - operating_margin_pct
    - hcris_confidence (high if total salaries + FTE both populated)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
COST_REPORT_CSV = DATA_DIR / "cost_report_2023.csv"
OUTPUT_CSV = DATA_DIR / "hcris_hospital_metrics.csv"

# Productive hours per FTE per year. CMS uses 2,080 for FTE conversions.
# The pricing engine uses 1,872 hours (nursing 36×52 schedule) for commitment
# math, but BLS/CMS labor accounting is on the 2,080 standard. We convert
# wages to per-hour using 2,080 here, then the pricing engine reapplies 1,872
# when computing commitment fees.
HOURS_PER_FTE_PER_YEAR = 2_080

EMPLOYER_FICA = 0.0765


def load_cost_report(path: Path = COST_REPORT_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, dtype={"Provider CCN": str})
    df = df.rename(columns={
        "Provider CCN": "ccn",
        "Hospital Name": "name",
        "State Code": "state",
        "Number of Beds": "beds",
        "FTE - Employees on Payroll": "fte",
        "Total Salaries From Worksheet A": "total_salaries",
        "Wage-Related Costs (Core)": "wage_related_costs",
        "Total Salaries (adjusted)": "total_salaries_adj",
        "Contract Labor: Direct Patient Care": "contract_labor",
        "Total Bed Days Available": "bed_days_available",
        "Total Days (V + XVIII + XIX + Unknown)": "patient_days",
        "Net Patient Revenue": "npr",
        "Total Costs": "total_costs",
        "Fiscal Year End Date": "fy_end",
    })
    # Pad CCN to 6 chars (CMS sometimes drops leading zeros)
    df["ccn"] = df["ccn"].astype(str).str.zfill(6)
    return df


def deduplicate_by_latest_fy(df: pd.DataFrame) -> pd.DataFrame:
    """Some hospitals submit two cost reports per calendar year. Keep latest FY-end."""
    df["fy_end_dt"] = pd.to_datetime(df["fy_end"], errors="coerce")
    df = df.sort_values("fy_end_dt").drop_duplicates(subset=["ccn"], keep="last")
    return df


def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-hospital labor-economics fields."""

    # Productive-hours-per-year per FTE
    H = HOURS_PER_FTE_PER_YEAR

    # Taxable wage per hour — best estimate from total salaries / FTE / hours.
    # Total Salaries from Worksheet A excludes wage-related costs (benefits),
    # so this approximates a loaded-cash-comp-per-hour but EXCLUDES benefits.
    # We treat it as "wage + payroll-related cash" — close enough for our
    # purposes; the W vs B split below is approximate.
    df["salary_per_fte"] = df["total_salaries"] / df["fte"]
    df["wage_related_per_fte"] = df["wage_related_costs"] / df["fte"]

    # Per-hour conversions. Where wage-related is missing, fall back to a
    # default benefit load (30% of base wage).
    df["taxable_wage_per_hour"] = df["salary_per_fte"] / H
    df["benefit_load_per_hour"] = np.where(
        df["wage_related_per_fte"].notna() & (df["wage_related_per_fte"] > 0),
        df["wage_related_per_fte"] / H,
        df["taxable_wage_per_hour"] * 0.30,  # 30% benefit load fallback
    )

    # Loaded staff cost = wage + benefits + employer FICA
    df["loaded_staff_cost_per_hour"] = (
        df["taxable_wage_per_hour"]
        + df["benefit_load_per_hour"]
        + df["taxable_wage_per_hour"] * EMPLOYER_FICA
    )

    # Contract labor intensity — share of comp going to agency.
    df["contract_labor_intensity"] = np.where(
        (df["total_salaries"].notna() & (df["total_salaries"] > 0)
         & df["contract_labor"].notna() & (df["contract_labor"] > 0)),
        df["contract_labor"] / (df["total_salaries"] + df["contract_labor"]),
        np.nan,
    )

    # Operating margin — for financial-capacity component of opportunity score
    df["operating_margin"] = np.where(
        df["npr"].notna() & (df["npr"] > 0) & df["total_costs"].notna(),
        (df["npr"] - df["total_costs"]) / df["npr"],
        np.nan,
    )

    # RN-need FTE estimate. The 'FTE - Employees on Payroll' figure is total
    # hospital FTE including non-nursing. CMS PBJ data would let us isolate
    # RN hours; without it we use a rough share by hospital type.
    # National benchmark: RNs are ~25-30% of acute care hospital FTE.
    df["estimated_rn_need_fte"] = df["fte"] * 0.27

    return df


def filter_acute_care(df: pd.DataFrame) -> pd.DataFrame:
    """Drop reports that are clearly out of scope (e.g., negative or zero FTE)."""
    keep = (
        df["taxable_wage_per_hour"].notna()
        & (df["taxable_wage_per_hour"] > 5)        # implausibly low
        & (df["taxable_wage_per_hour"] < 200)      # implausibly high
        & df["fte"].notna()
        & (df["fte"] > 0)
    )
    print(f"  Filtered: {keep.sum():,} valid / {len(df):,} total reports")
    return df[keep].copy()


def confidence_score(row: pd.Series) -> float:
    """How much do we trust these HCRIS-derived numbers for this hospital?"""
    c = 0.85  # base: total salaries + FTE both present
    if pd.notna(row.get("wage_related_costs")) and row.get("wage_related_costs", 0) > 0:
        c = 0.90  # bumped: wage-related-costs also populated
    if pd.notna(row.get("contract_labor")) and row.get("contract_labor", 0) > 0:
        c = 0.92  # bumped: contract labor reported
    return c


def main() -> None:
    print("Parsing HCRIS Hospital Provider Cost Report 2023...")
    raw = load_cost_report()
    print(f"  Loaded {len(raw):,} report rows ({raw['ccn'].nunique():,} unique CCNs)")

    raw = deduplicate_by_latest_fy(raw)
    print(f"  After dedup to latest FY: {len(raw):,}")

    out = compute_metrics(raw)
    out = filter_acute_care(out)
    out["hcris_confidence"] = out.apply(confidence_score, axis=1)

    print("\n  Per-hour wage distribution (loaded staff cost):")
    desc = out["loaded_staff_cost_per_hour"].describe()
    print(f"    median: ${desc['50%']:.2f}/hr")
    print(f"    p25:    ${desc['25%']:.2f}/hr")
    print(f"    p75:    ${desc['75%']:.2f}/hr")
    print(f"    p90:    ${out['loaded_staff_cost_per_hour'].quantile(0.90):.2f}/hr")
    print(f"    p99:    ${out['loaded_staff_cost_per_hour'].quantile(0.99):.2f}/hr")

    print("\n  Contract labor intensity distribution:")
    cli = out["contract_labor_intensity"].dropna()
    print(f"    hospitals reporting both: {len(cli):,} / {len(out):,}")
    if len(cli) > 0:
        print(f"    median: {cli.median()*100:.1f}%")
        print(f"    p75:    {cli.quantile(0.75)*100:.1f}%")
        print(f"    p90:    {cli.quantile(0.90)*100:.1f}%")
        print(f"    p95:    {cli.quantile(0.95)*100:.1f}%")
        print(f"    p99:    {cli.quantile(0.99)*100:.1f}%")
        print(f"    hospitals with >15% contract labor: {(cli > 0.15).sum():,}")
        print(f"    hospitals with >30% contract labor: {(cli > 0.30).sum():,}")

    print("\n  Top 10 hospitals by contract labor intensity:")
    top = out[out["contract_labor_intensity"].notna()].nlargest(
        10, "contract_labor_intensity"
    )
    cols = ["ccn", "name", "state", "contract_labor", "total_salaries",
            "contract_labor_intensity", "loaded_staff_cost_per_hour"]
    for _, r in top[cols].iterrows():
        print(f"    {r['name'][:48]:48} {r['state']}  "
              f"CL=${r['contract_labor']/1e6:6.1f}M  "
              f"share={r['contract_labor_intensity']*100:5.1f}%  "
              f"loaded=${r['loaded_staff_cost_per_hour']:6.2f}/hr")

    # Write output
    keep_cols = [
        "ccn", "name", "state", "beds", "fte",
        "taxable_wage_per_hour", "benefit_load_per_hour",
        "loaded_staff_cost_per_hour",
        "contract_labor", "contract_labor_intensity",
        "operating_margin", "estimated_rn_need_fte", "npr", "total_costs",
        "hcris_confidence", "fy_end",
    ]
    out[keep_cols].to_csv(OUTPUT_CSV, index=False)
    print(f"\n  Wrote {OUTPUT_CSV}")
    print(f"  Total hospitals with HCRIS metrics: {len(out):,}")


if __name__ == "__main__":
    main()
