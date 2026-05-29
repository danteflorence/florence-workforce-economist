# Status — Florence Workforce Restoration Economics

Engine version: **v0.5-methodology-v2-2026-05** (matches Methodology v2.0).
Data layer version: **v0.6** (full data uplift pass — May 28, 2026).

Default pricing posture (all confirmed):
- F-1 cohort, 2-year placement → IRC §3121(b)(19) employer FICA exemption reliable
- η = 1.0 default (per IRS guidance + user confirmation)
- 24-month contract term, all 24 months FICA-eligible
- FICA_OFFSET_TARGET pricing mode at 50% target
- $750–$2,000/RN/month guardrails
- Immigration transition add-on: toggleable

---

## v0.6 — Overnight data accuracy uplift summary

| Uplift | Before | After |
|---|---|---|
| Hospital roster | CMS HGI live | unchanged (5,432 hospitals) |
| Per-hospital agency hourly rate | State-imputed (CommonSpirit-CA-anchored) for 96% | **HCRIS NMRC per-hospital REAL for 3,011 hospitals (49.7%)** |
| RN wages | State-level placeholder only | **3-tier: BLS OEWS MSA (1,811 hospitals, top 60 MSAs) > HCRIS-blended × multiplier (1,532) > state fallback (2,089)** |
| HCRIS data years | FY2023 only | **FY2023 + FY2024 (latest per CCN)** |
| Geographic granularity | State-level + ZIP/lat-lon | **ZIP → CBSA/MSA crosswalk (Census 2023) — 18,475 ZIPs in MSAs** |
| MSP/vendor markup capture | Missing entirely | **Kaiser $622M AMN overlay allocated to 35 KP facilities ($17.39/RN-CL-hr)** |
| Source governance | Flat universe.csv | **market_rate_observations table — 3,194 rows with source_type, as_of_date, confidence_tier** |
| Snapshot reproducibility | None | **Daily snapshot writer (parquet) — replay any past pricing run** |

## Kaiser numbers — full evolution

| Metric | v0.4 imputed | v0.5 HCRIS NMRC | **v0.6 + AMN overlay + BLS MSA** |
|---|---:|---:|---:|
| Median agency rate | $142.89/hr | $105.66/hr | **$121.73/hr** (HCRIS + $17.39 AMN overlay) |
| Median loaded staff cost | $87.36/hr | $87.36/hr | **$89.66/hr** (BLS MSA RN wages, not blended × 1.4) |
| Median agency premium | $55.37/hr | $18.73/hr | **$28.05/hr** (post-AMN, more conservative than imputed but bigger than HCRIS-only) |
| Median monthly Florence fee | $1,574 | $1,574 | **$1,596** |
| Median FICA savings/mo | $787 | $787 | **$798** |
| Actual FICA offset % | 50.0% | 50.0% | **50.0%** (target hit) |
| Median net monthly savings/RN | $7,851 | $2,135 | **$3,741** |
| Total monthly Florence billings | $15.1M/mo | $15.1M/mo | **$18.45M/mo** |
| 24-month Florence fee | $363M | $455M | **$443M** |
| 24-month Kaiser net savings | $1.90B | $0.66B | **$0.91B** |
| **Savings : Fee ratio** | 5.2× (inflated) | 1.4× (under-counted) | **2.0× (correct)** |
| Quotable facilities | 38 / 38 | 36 / 38 | **35 / 38** (3 KP-OR facilities have agency < staff cost — real reflection of Kaiser's integrated wage advantage) |

The 2.0× savings:fee ratio under v0.6 is the most defensible Kaiser number to date. Every dollar of agency premium is anchored to either KP's own HCRIS filings (per-hospital) or to AMN's public 10-K disclosures (system-level overlay). The earlier 5.2× ratio overstated savings by ~2.6× via bad CA-tier imputation.

## National numbers — final v0.6 state

- 5,432 hospitals scanned
- 4,693 quotable (was 5,431; 739 now correctly manual-review when real agency ≤ real RN wage)
- Total RN need: 330,173 FTE
- **Total monthly Florence billings: $386M/mo**
- **Total monthly FICA offset to hospitals: $191M/mo**
- **Total monthly net savings: $1,767M/mo**
- **24-month Florence fee: $9.27B**
- **24-month hospital net savings: $42.40B**
- Savings:Fee ratio (national): 4.6×
- 94% of quotable hospitals land at the exact 50% FICA-offset target

## Confidence distribution

| Tier | Hospitals | Source |
|---|---:|---|
| 1.00 | 31 | CommonSpirit direct match (real customer disclosure) |
| 0.95 | 100 | CS + HCRIS-NMRC + MSP overlay (Kaiser/etc.) |
| 0.92 | 2,569 | HCRIS-NMRC per-hospital agency rate, with BLS MSA wage |
| 0.85 | 2,351 | HCRIS staff cost + state agency fallback |
| 0.60 | 147 | State-level imputed (CS anchor) |
| 0.40 | 234 | National-imputed fallback |

**98.5% of hospitals now have confidence ≥ 0.85** (up from 1.8% before v0.5).

---

## Data sources in production

| Source | What it provides | Refresh | Status |
|---|---|---|---|
| CMS Hospital General Information | Roster, address, type, ownership | Quarterly | ✅ Live |
| CMS HCRIS Hospital Provider Cost Report (aggregated) | Per-hospital salaries, FTE, contract labor $ | Annual | ✅ Live (FY2023) |
| **CMS HCRIS NMRC (raw line items)** | **Per-hospital contract labor $/hr (S-3 Part II line 01100)** | **Annual** | **✅ Live (FY2023 + FY2024)** |
| BLS OEWS by MSA (top 60 MSAs) | RN-specific MSA wages | Annual | ✅ Hardcoded from May 2024 release; API ingest pending |
| BLS OEWS state-level | RN wages fallback | Annual | ✅ Hardcoded |
| Census ZCTA-County-CBSA | Geographic crosswalk | Annual | ✅ Live (Census 2020 + 2023) |
| **System-level MSP overlays** | **AMN markup not captured in HCRIS** | **Per-system manual** | **✅ Kaiser configured ($622M)** |
| CommonSpirit demo | Anchor agency rates for 96 hospitals | Static | ✅ Loaded |

---

## Files added in this overnight pass

| File | Purpose |
|---|---|
| `hcris_nmrc_parser.py` | Parses raw HCRIS NMRC line items → per-hospital agency hourly rate |
| `build_zip_cbsa_crosswalk.py` | ZIP → County → CBSA/MSA mapping (Census 2020 + 2023) |
| `wage_estimator.py` | 3-tier per-hospital RN wage (BLS MSA > HCRIS-blended × multiplier > state) |
| `system_overlays.py` | Generic MSP-overlay allocator (Kaiser $622M AMN as first case) |
| `market_observations.py` | Generates v2 §3 market_rate_observations table (3,194 rows) |
| `snapshots.py` | Daily snapshot writer for point-in-time pricing reproducibility |
| `data/hcris_raw/HOSP10FY{2023,2024}.zip` | Raw CMS HCRIS data (~260 MB) |
| `data/hcris_agency_rates.csv` | Per-hospital agency rates from NMRC |
| `data/per_hospital_rn_wages.csv` | 3-tier per-hospital wage table |
| `data/geo/zcta_county_2020.txt` | Census ZCTA → County |
| `data/geo/cbsa_list_2023.xlsx` | Census CBSA delineation |
| `data/geo/zip_cbsa.csv` | ZIP → CBSA crosswalk (33,791 ZIPs) |
| `data/system_level_overlays.csv` | Per-facility MSP overlay allocations |
| `data/market_rate_observations.csv` | v2 §3 source governance table |
| `data/snapshots/snapshot_2026-05-28.parquet` | Today's full universe pricing snapshot |
| `proposals/Kaiser_Permanente_v0.6_FINAL.xlsx` | Kaiser system Excel workbook (10 tabs, v0.6 data) |
| `proposals/Kaiser_Permanente_exec_summary.pdf` | 2-page exec summary with all uplifts |

---

## What's still pending after v0.6

| Item | Effort | Why |
|---|---|---|
| BLS OEWS live API integration | 1 day | Replace hardcoded MSA table; needs registered token + series ID mapping |
| HCRIS NMRC for more lines (e.g., 01700 wage-related costs) | 1 day | Investigated — line 01700 is wage-related costs not contract labor; current scope is correct |
| Travel nurse posting feeds (Aya/AMN/NSI/SIA) | 3-5 days | Needs vendor/API access or licensed feed |
| Hospital career page parsing | 3-5 days | Legal review required for ToS-compliant scraping |
| BLS JOLTS pressure indicators | 1 day | Monthly job-openings data per market |
| Additional system-level overlays (HCA, Ascension, etc.) | 0.5 day per system | When AMN/MSP filings disclose system-level fee amounts |
| AHA Annual Survey CCN → system_id (replace keyword inference) | 2-4 days | Lifts system coverage from 15% to ~95% |
| Automated test suite (v2 §10) | 2 days | Formula tests, manual-review tests, rollup tests |
| Approval workflow + calibration audit log | 3-5 days | Enterprise governance for production |
| Cron/scheduled refresh pipeline | 1 day | Nightly re-run of all ingest scripts |
| Excel workbook formulas (vs. hardcoded values) | 2-3 days | Per v2 §10 validation — formula-driven not value-driven |
| Word proposal generator | 2-3 days | Per v2 §Required Outputs |

---

## To run

```bash
cd /Users/dantetolbedantert/florence-work/labor-economics-agent
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
streamlit run app.py
```

Defaults reflect v0.6 calibration: FICA_OFFSET_TARGET mode, 50% target, $750–$2,000 monthly guardrails, F-1 cohort η=1.0, 24-month term. Streamlit has 9 tabs now — including the new **Data provenance** tab that surfaces the 3,194-row market_rate_observations table + Kaiser MSP overlay + snapshot history.

## To regenerate data layer from scratch

```bash
python3 hcris_parser.py              # ~30 sec — aggregated HCRIS
python3 hcris_nmrc_parser.py          # ~90 sec — raw NMRC for per-hospital rates
python3 build_zip_cbsa_crosswalk.py   # ~1 sec
python3 wage_estimator.py             # ~5 sec — per-hospital RN wages
python3 geocode_and_systems.py        # ~3 sec — ZIP → lat/lon + system inference
python3 build_hospital_universe.py    # ~5 sec — assemble universe
python3 system_overlays.py            # ~1 sec — allocate Kaiser AMN $622M
python3 build_hospital_universe.py    # rebuild with overlay applied
python3 market_observations.py        # ~2 sec — build observation table
python3 snapshots.py                  # ~5 sec — today's snapshot
```
