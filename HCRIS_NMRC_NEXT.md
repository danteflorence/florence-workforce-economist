# Next milestone: raw HCRIS NMRC ingest for per-hospital agency hourly rates

## Goal

Replace the state-imputed agency hourly rate with a per-hospital agency hourly rate derived directly from each hospital's HCRIS cost report. This is the single most impactful confidence improvement remaining.

Today, every hospital outside the 96 CommonSpirit direct matches uses a state-level median agency rate. After this milestone, every hospital that reports contract labor in HCRIS will have its own hourly rate.

## What changes

| Field | Today | After this milestone |
|---|---|---|
| Loaded staff cost | HCRIS-derived (per-hospital benefit load, state-level RN wage) | Same — HCRIS doesn't have RN-specific wages either |
| All-in agency rate | State-level median (CommonSpirit) | **Per-hospital from cost / hours** |
| Agency premium per hour | Hospital wage vs. state agency median | **Hospital wage vs. hospital agency rate** |
| Agency hours per hospital | Unknown | **Known per hospital** |
| Pricing confidence (the 0.85 bucket) | 0.85 | **~0.92** for HCRIS-reporting hospitals |

The "missing" piece in our current data — contract labor HOURS — is what raw HCRIS provides. Cost ÷ Hours = hourly bill rate.

## Where the data lives

CMS publishes HCRIS as a set of CSV files per fiscal year. The relevant files:

| File | What it contains |
|---|---|
| `HOSP10_YYYY_RPT.CSV` | One row per cost report. Columns: `rpt_rec_num` (join key), `prvdr_ctrl_type_cd`, **`prvdr_num` (= CCN)**, `npi`, `rpt_stus_cd`, `fy_bgn_dt`, `fy_end_dt`, `proc_dt`. ~10,000 rows. |
| `HOSP10_YYYY_NMRC.CSV` | One row per (report × worksheet × line × column) numeric value. ~30 million rows for a year. Columns: `rpt_rec_num`, `wksht_cd`, `line_num`, `clmn_num`, `itm_val_num`. |
| `HOSP10_YYYY_ALPHA.CSV` | Same shape as NMRC but for text values. Smaller. |
| `HOSP10_YYYY_ROLLUP.CSV` | Pre-aggregated by line — less granular. |

**Crucial join detail:** `rpt_rec_num` in the NMRC file is the report record number, NOT the CCN. You must join NMRC → RPT on `rpt_rec_num` to get the CCN. The existing florenceos `services/cms_ingest/main.py` got this wrong (used `rpt_rec_num` as CCN directly).

## Download

CMS publishes a quarterly ZIP at:
```
https://www.cms.gov/files/zip/hospital-2010-form-cost-reports-(...).zip
```
The exact URL changes; query via `https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports` or the data.cms.gov catalog. Files are 200-800 MB per year; expect ~30 minutes to download.

Alternative: HCRIS provides a "Public Use File" download via the older site:
```
https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports/Hospital-2010-form
```

## What to extract

For agency hourly rates, the relevant lines on Worksheet S-3 Part V (Contract Labor):

| Worksheet code | Line | Column | What it represents |
|---|---|---|---|
| `S300005` (S-3 Pt V) | `00100` | `00100` | Direct patient care — Contract labor cost ($) |
| `S300005` (S-3 Pt V) | `00100` | `00200` | Direct patient care — Contract labor hours |
| `S300005` (S-3 Pt V) | `00200` | `00100` | Therapy services — Contract labor cost |
| `S300005` (S-3 Pt V) | `00200` | `00200` | Therapy services — Contract labor hours |
| `S300005` (S-3 Pt V) | `00300` | `00100` | Other contracted services — Contract labor cost |
| `S300005` (S-3 Pt V) | `00300` | `00200` | Other contracted services — Contract labor hours |
| `S300005` (S-3 Pt V) | `00400` | `00100` | Top management — Contract labor cost |
| `S300005` (S-3 Pt V) | `00400` | `00200` | Top management — Contract labor hours |

Worksheet codes in the actual files may be formatted as `S-3` with a part suffix; the exact format is `S300005` or similar fixed-width code. **Verify against the actual file** — the structure has changed across HCRIS version revisions.

For RN-specific wages (Worksheet S-3 Part II — Hospital wage data):

| Worksheet code | Line | Column | What it represents |
|---|---|---|---|
| `S300002` (S-3 Pt II) | `00100` | `00100` | Total — paid hours |
| `S300002` (S-3 Pt II) | `00100` | `00200` | Total — average hourly wage |
| `S300002` (S-3 Pt II) | `00100` | `00300` | Total — paid hourly amount |
| `S300002` (S-3 Pt II) | `00400` | `00100` | RN — paid hours (verify line number; varies by year) |
| `S300002` (S-3 Pt II) | `00400` | `00200` | RN — average hourly wage |

**Important:** the 2552-2010 form does NOT break out RN-specific wages on S-3 Part II at the lines I listed above. That granularity exists in CMS PBJ (Payroll-Based Journal) for skilled nursing — but PBJ is a separate dataset focused on long-term care facilities. For hospital RN wages, you may need to combine BLS OEWS + the hospital's general wage index instead.

## Parser sketch

```python
import pandas as pd

# Load report metadata
rpt = pd.read_csv("HOSP10_2023_RPT.CSV", low_memory=False)
rpt = rpt[["rpt_rec_num", "prvdr_num", "fy_bgn_dt", "fy_end_dt"]]
rpt = rpt.rename(columns={"prvdr_num": "ccn"})
rpt["ccn"] = rpt["ccn"].astype(str).str.zfill(6)

# Load numeric line items (this is the big file)
nmrc = pd.read_csv(
    "HOSP10_2023_NMRC.CSV",
    low_memory=False,
    dtype={
        "rpt_rec_num": str,
        "wksht_cd": str,
        "line_num": str,
        "clmn_num": str,
        "itm_val_num": float,
    },
)

# Filter to Worksheet S-3 Part V (contract labor)
s3v = nmrc[nmrc["wksht_cd"] == "S300005"]

# Pivot to one row per (report, line) with cost + hours columns
pivot = s3v.pivot_table(
    index=["rpt_rec_num", "line_num"],
    columns="clmn_num",
    values="itm_val_num",
).reset_index()
pivot.columns.name = None
pivot = pivot.rename(columns={"00100": "cost", "00200": "hours"})

# Direct patient care = line 00100
dpc = pivot[pivot["line_num"] == "00100"].copy()
dpc["agency_rate_per_hour"] = dpc["cost"] / dpc["hours"]
dpc = dpc.merge(rpt[["rpt_rec_num", "ccn"]], on="rpt_rec_num")

# Take latest report per CCN
dpc = dpc.sort_values("fy_end_dt").drop_duplicates(subset=["ccn"], keep="last")

# Sanity-filter
dpc = dpc[
    (dpc["agency_rate_per_hour"] > 30)      # implausibly low
    & (dpc["agency_rate_per_hour"] < 400)   # implausibly high
]

dpc[["ccn", "cost", "hours", "agency_rate_per_hour"]].to_csv(
    "data/hcris_agency_rates.csv", index=False
)
```

## What's hard about this

1. **File size.** NMRC is ~3-5 GB uncompressed per year. Need to either stream it, chunk-read with pandas, or push it into Postgres directly. The `florenceos/db/migrations/011_cms.sql` schema is already designed for this — use it.

2. **Schema drift.** HCRIS form versions changed in 2010 and again with minor revisions. The worksheet codes and line numbers shift slightly across years. Verify against the actual file before relying on hardcoded codes.

3. **Coverage.** Not every hospital reports every line. Contract-labor lines have ~50% completion in the aggregated file; expect similar in raw. Hospitals with zero contract labor will have null hours.

4. **CCN padding.** CMS sometimes drops leading zeros on CCN. Always pad to 6 chars on both sides of any join.

5. **Multiple reports per year.** Some hospitals submit two reports per calendar year for different fiscal periods. The `hcris_parser.py` already handles this with `deduplicate_by_latest_fy()`; preserve that logic.

6. **Critical access hospitals.** These use a different form (2552-96 in some cases, or 2552-10 with different sections). Filter or handle separately.

## Validation plan

When the parser runs:

1. **Count check:** Expect ~3,000-3,500 hospitals with parseable contract-labor hourly rates (consistent with the 50% reporting rate seen in the aggregated file).
2. **Distribution check:** Median agency rate should be in $80-$160/hr range nationally. Outliers below $40/hr or above $300/hr are likely line-coding errors — investigate before using.
3. **CommonSpirit cross-check:** Use the 96 CommonSpirit matches as anchors. The HCRIS-derived rate per hospital should be within ±$15/hr of the CommonSpirit demo rate. Larger discrepancies indicate either line-coding issues or that the CommonSpirit `agency_rate` is from a different methodology (e.g., excludes certain MSP fees).
4. **State median check:** The HCRIS-derived state median should align with our current CommonSpirit-derived state median (within ±20%). Larger drift means we need to update the imputation logic for non-HCRIS hospitals.

## Integration into the existing tool

Once `data/hcris_agency_rates.csv` exists:

1. In `build_hospital_universe.py`, load it alongside the existing `hcris_hospital_metrics.csv`.
2. In `assemble_universe()`, when a hospital has a real `agency_rate_per_hour` from HCRIS, use it instead of the state median.
3. Bump that hospital's confidence to ~0.92 (from 0.85).
4. The Streamlit app will pick it up automatically — no UI changes needed.

The hardest part is #2 — and that work is 90% done now. The bottleneck is just the file ingest, not the modeling.
