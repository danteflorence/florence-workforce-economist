"""
HCRIS NMRC parser — extracts per-hospital contract-labor hourly rate from the
raw Hospital 2552-10 cost report line items.

Source: data/hcris_raw/HOSP10FY{year}.zip from CMS at
    https://downloads.cms.gov/Files/hcris/HOSP10FY{year}.zip

Reverse-engineered worksheet/line/column mapping (verified against the CMS
aggregated Hospital Provider Cost Report):

  Worksheet S300002 (S-3 Part II: Hospital Wage Data)
    line 00100, col 00200 = Total salaries
    line 00100, col 00500 = Total paid hours
    line 00100, col 00600 = Total average hourly wage
    line 01100, col 00200 = Contract Labor: Direct Patient Care ($)
    line 01100, col 00500 = Contract Labor: Direct Patient Care (hours)
    line 01100, col 00600 = Contract Labor: Direct Patient Care AVG HOURLY RATE

  The aggregated CSV "Contract Labor: Direct Patient Care" = line 01100 col 00200
  (verified to exact dollar value).

Output: data/hcris_agency_rates.csv with:
    ccn, rpt_rec_num, fy_end,
    contract_labor_dollars,
    contract_labor_hours,
    contract_labor_hourly_rate,    ← THIS IS THE PER-HOSPITAL AGENCY RATE
    total_paid_hours,
    total_avg_hourly_wage,         ← all-workforce blended hourly wage
    source_confidence              (0.92 for HCRIS NMRC direct)

Notes:
  - The "Contract Labor: Direct Patient Care" line includes RN agency, allied
    health contracts, locums, etc. Not pure RN agency — but the closest signal
    we have until customer-disclosed agency rates arrive.
  - Some hospitals don't report line 01100 (no contract labor used). Filter
    those out — they need a different agency-rate source.
  - Latest fiscal year per CCN is kept; older reports are deduplicated out.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
HCRIS_DIR = DATA_DIR / "hcris_raw"
OUTPUT_CSV = DATA_DIR / "hcris_agency_rates.csv"


# RPT (report metadata) field positions (0-indexed) per HCRIS spec
RPT_RPT_REC_NUM = 0
RPT_CCN = 2          # prvdr_num
RPT_FY_BGN = 5       # fy_bgn_dt
RPT_FY_END = 6       # fy_end_dt


def load_rpt_index(zip_path: Path) -> dict:
    """Load RPT file and return {rpt_rec_num: (ccn, fy_end)} mapping."""
    print(f"  Loading RPT index from {zip_path.name}...")
    rpt_csv_name = [n for n in zipfile.ZipFile(zip_path).namelist() if n.endswith("_rpt.csv")][0]
    index = {}
    with zipfile.ZipFile(zip_path) as z, z.open(rpt_csv_name) as f:
        reader = csv.reader(io.TextIOWrapper(f, "utf-8"))
        for row in reader:
            if len(row) <= RPT_FY_END:
                continue
            rpt = row[RPT_RPT_REC_NUM].strip()
            ccn = row[RPT_CCN].strip().zfill(6)
            fy_end = row[RPT_FY_END].strip()
            if rpt and ccn:
                index[rpt] = (ccn, fy_end)
    print(f"    {len(index):,} reports indexed.")
    return index


# Target line items we care about (S-3 Part II, line 01100 = Contract Labor DPC)
TARGET_WKSHT = "S300002"
WANTED_LINES = {"00100", "01100"}
WANTED_COLS = {"00200", "00400", "00500", "00600"}


def stream_extract_s3_part_ii(zip_path: Path) -> pd.DataFrame:
    """Stream the NMRC file and extract only S-3 Part II target rows."""
    print(f"  Streaming NMRC from {zip_path.name}...")
    nmrc_csv_name = [n for n in zipfile.ZipFile(zip_path).namelist() if n.endswith("_nmrc.csv")][0]
    records = []
    n_total = 0
    with zipfile.ZipFile(zip_path) as z, z.open(nmrc_csv_name) as f:
        reader = csv.reader(io.TextIOWrapper(f, "utf-8"))
        for row in reader:
            n_total += 1
            if n_total % 5_000_000 == 0:
                print(f"    ... scanned {n_total:,} rows, kept {len(records):,}")
            if len(row) < 5:
                continue
            if row[1] != TARGET_WKSHT:
                continue
            if row[2] not in WANTED_LINES:
                continue
            if row[3] not in WANTED_COLS:
                continue
            try:
                records.append({
                    "rpt_rec_num": row[0].strip(),
                    "line_num": row[2],
                    "clmn_num": row[3],
                    "value": float(row[4]) if row[4] else 0.0,
                })
            except ValueError:
                continue
    print(f"    Scanned {n_total:,} total rows, kept {len(records):,} S-3 Part II target rows.")
    return pd.DataFrame(records)


def build_agency_rates(zip_paths: list[Path]) -> pd.DataFrame:
    """Build per-hospital agency rate table from one or more HCRIS year ZIPs."""
    all_rows = []
    for zp in zip_paths:
        print(f"\nProcessing {zp.name} ...")
        rpt_index = load_rpt_index(zp)
        nmrc = stream_extract_s3_part_ii(zp)
        # Map rpt_rec_num to (ccn, fy_end)
        nmrc["ccn"] = nmrc["rpt_rec_num"].map(lambda r: rpt_index.get(r, (None, None))[0])
        nmrc["fy_end"] = nmrc["rpt_rec_num"].map(lambda r: rpt_index.get(r, (None, None))[1])
        nmrc = nmrc.dropna(subset=["ccn"])
        all_rows.append(nmrc)

    df = pd.concat(all_rows, ignore_index=True)
    print(f"\nCombined: {len(df):,} target rows across {df['ccn'].nunique():,} CCNs.")

    # Pivot to one row per (ccn, rpt_rec_num) with columns for each (line, col)
    pivot = df.pivot_table(
        index=["ccn", "rpt_rec_num", "fy_end"],
        columns=["line_num", "clmn_num"],
        values="value",
        aggfunc="first",
    ).reset_index()
    # Flatten column index
    pivot.columns = [
        f"L{a}_C{b}" if a and b else (a or b)
        for a, b in pivot.columns
    ]
    # Rename to human-readable
    rename_map = {
        "L00100_C00200": "total_salaries",
        "L00100_C00400": "total_salaries_adj",
        "L00100_C00500": "total_paid_hours",
        "L00100_C00600": "total_avg_hourly_wage",
        "L01100_C00200": "contract_labor_dollars",
        "L01100_C00400": "contract_labor_dollars_adj",
        "L01100_C00500": "contract_labor_hours",
        "L01100_C00600": "contract_labor_hourly_rate",
    }
    pivot = pivot.rename(columns=rename_map)

    # Compute hourly rate where we have both $ and hours but no published rate
    if "contract_labor_hourly_rate" in pivot.columns:
        recompute_mask = (
            pivot["contract_labor_hourly_rate"].isna()
            & pivot.get("contract_labor_dollars", pd.Series(dtype=float)).notna()
            & pivot.get("contract_labor_hours", pd.Series(dtype=float)).notna()
            & (pivot.get("contract_labor_hours", 0) > 0)
        )
        pivot.loc[recompute_mask, "contract_labor_hourly_rate"] = (
            pivot.loc[recompute_mask, "contract_labor_dollars"]
            / pivot.loc[recompute_mask, "contract_labor_hours"]
        )

    # Latest fy_end per CCN
    pivot["fy_end_dt"] = pd.to_datetime(pivot["fy_end"], errors="coerce")
    pivot = pivot.sort_values("fy_end_dt").drop_duplicates("ccn", keep="last")

    # Sanity-filter: reasonable hourly rate range
    keep = (
        pivot["contract_labor_hourly_rate"].notna()
        & (pivot["contract_labor_hourly_rate"] > 25)
        & (pivot["contract_labor_hourly_rate"] < 500)
    )
    n_dropped = (~keep).sum()
    print(f"Filtered out {n_dropped:,} CCNs with implausible or missing rates.")
    pivot = pivot[keep].copy()

    pivot["source_confidence"] = 0.92  # HCRIS NMRC direct
    return pivot


def main() -> None:
    print("=" * 78)
    print("HCRIS NMRC parser — per-hospital contract-labor hourly rate")
    print("=" * 78)

    zip_paths = sorted(HCRIS_DIR.glob("HOSP10FY*.zip"))
    if not zip_paths:
        print(f"No HOSP10FY*.zip files found in {HCRIS_DIR}")
        return

    out = build_agency_rates(zip_paths)
    print(f"\nFinal: {len(out):,} hospitals with HCRIS-derived agency rates.\n")

    print("Rate distribution:")
    desc = out["contract_labor_hourly_rate"].describe(percentiles=[0.10, 0.25, 0.50, 0.75, 0.90, 0.99])
    for k, v in desc.items():
        print(f"  {k:>10}  ${v:>8.2f}")

    print(f"\nWriting {OUTPUT_CSV}...")
    keep_cols = [
        "ccn", "rpt_rec_num", "fy_end",
        "total_salaries", "total_paid_hours", "total_avg_hourly_wage",
        "contract_labor_dollars", "contract_labor_hours", "contract_labor_hourly_rate",
        "source_confidence",
    ]
    out[[c for c in keep_cols if c in out.columns]].to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote {OUTPUT_CSV}")
    print(f"\nSample rows:")
    print(out[[c for c in keep_cols if c in out.columns]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
