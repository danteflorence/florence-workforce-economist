# Florence Labor Economics Agent — v0.6

National pricing engine for permanent RN placement. For every Medicare-registered U.S. hospital (5,432 facilities), produces a Florence fee per [Florence Workforce Restoration Economics Methodology v2.0](Florence_Market_Pricing_Product_Plan.md).

**Default mode**: FICA-offset target pricing on an F-1 cohort, 24-month term, $750–$2,000/RN/month guardrails. Per-hospital agency rates from raw HCRIS Hospital 2552-10 line items (2,699 hospitals with real per-hospital data). System-level MSP overlays for Kaiser (+$17.39/RN-CL-hr per AMN $622M disclosure).

**For every hospital, the engine produces the five v2 primary buyer-facing numbers:**
1. Florence Monthly Fee per RN
2. Employer FICA Savings per RN per Month
3. FICA-Adjusted Effective Cost per RN per Month
4. Actual FICA Offset %
5. Net Monthly Savings per RN

Not a sales-targeting tool — the engine prices whatever account is in front of Florence.

---

## Quick start

```bash
cd /Users/dantetolbedantert/florence-work/labor-economics-agent
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
streamlit run app.py
```

App opens at http://localhost:8501. First load ~5s for the 5,432-hospital batch.

Pre-generated proposal bundles for the top 10 systems (Kaiser, Sutter, HCA, VA, Beth Israel Lahey, Stanford, UChicago, RWJBarnabas, Banner, Ascension) live in [`proposals/systems/`](proposals/systems/). Top 50 individual hospitals in [`proposals/hospitals/`](proposals/hospitals/). Each comes with Excel (10 tabs) + 2-page exec summary PDF + HTML.

---

## Current state (v0.6, May 28 2026)

| Layer | Status |
|---|---|
| Pricing engine | v0.5 — v2 methodology, FICA_OFFSET_TARGET default, 18 unit tests passing |
| Hospital roster | 5,432 (CMS HGI, live) |
| Per-hospital agency hourly rate | **3,105 hospitals (57%) from raw HCRIS NMRC 2021-2024** |
| Per-hospital RN wage | 3-tier: BLS OEWS MSA top-60 → HCRIS-blended × multiplier → state fallback |
| ZIP → CBSA crosswalk | Census 2020 ZCTA + 2023 CBSA (18,475 ZIPs in MSAs) |
| System-level MSP overlays | Kaiser ($622M / 35.76M hours = $17.39/hr) |
| Source governance | `market_rate_observations` table — 3,288 observations |
| Snapshot persistence | Daily parquet snapshots for point-in-time reproducibility |
| Pricing change alerts | Snapshot diff → markdown alerts |
| Outputs | Excel (10 tabs), 2-page PDF, HTML, Markdown |
| Pre-generated bundles | Top 10 systems + Top 50 hospitals |

## Headline numbers under v0.6

| | National | Kaiser |
|---|---:|---:|
| Quotable hospitals | 4,693 / 5,432 | 35 / 38 |
| Total monthly Florence billings | **$386M / mo** | **$18.5M / mo** |
| Total monthly FICA offset | $191M / mo | $9.2M / mo |
| Total monthly hospital net savings | $1.77B / mo | $37.8M / mo |
| **24-month Florence fee** | **$9.27B** | **$443M** |
| **24-month hospital net savings** | **$42.4B** | **$0.91B** |
| Savings : Fee ratio | 4.6× | 2.0× |
| % at exact 50% FICA target | 94% | 100% (of quotable) |

---

## Files

### Pricing engine + batch
| File | Purpose |
|---|---|
| `pricing_engine.py` | Canonical v2 pricing math, PricingMode enum, 5 buyer-facing numbers, immigration add-on, manual-review logic, IRS compliance sentence |
| `pricing_batch.py` | `price_batch()` over the universe, `calibration_sweep()`, `market_aggregate()` |
| `test_pricing_engine.py` | 18 unit tests for formula, manual-review, guardrails, FICA, partner split, rollups |

### Data ingest + universe build
| File | Purpose |
|---|---|
| `build_hospital_universe.py` | Stitches all sources into `data/hospital_universe.csv` |
| `hcris_parser.py` | CMS aggregated Hospital Provider Cost Report parser |
| `hcris_nmrc_parser.py` | **Raw HCRIS NMRC parser — per-hospital agency $/hr** (S-3 Part II line 01100) |
| `wage_estimator.py` | 3-tier per-hospital RN wage (BLS MSA > HCRIS blended > state) |
| `build_zip_cbsa_crosswalk.py` | ZIP → County → CBSA/MSA mapping |
| `geocode_and_systems.py` | ZCTA centroids + curated health-system inference |
| `system_overlays.py` | System-level MSP overlay allocator (Kaiser $622M as first case) |
| `market_observations.py` | Builds v2 §3 `market_rate_observations` table |
| `snapshots.py` | Point-in-time pricing snapshot writer/reader |
| `pricing_alerts.py` | Snapshot diff → pricing change alerts |

### Output generators
| File | Purpose |
|---|---|
| `excel_writer.py` | 10-tab Excel workbook per v2 §8 (per hospital or per system) |
| `exec_summary.py` | 2-page executive summary (HTML + PDF via reportlab) |
| `cross_system_report.py` | Top-12 systems side-by-side (HTML + PDF, landscape) |
| `manual_review_report.py` | Categorized explanation of 739 manual-review hospitals |
| `proposal_data.py`, `proposal_html.py` | Earlier-iteration HTML deck renderers (paused) |

### App
| File | Purpose |
|---|---|
| `app.py` | Streamlit app — 9 tabs (Map, Systems, Single hospital, Table, Market view, Pricing elasticity, Calibration sweep, Data quality, **📊 Data provenance**) |

### Data
| File | What's in it |
|---|---|
| `data/cms_hospitals.csv` | CMS Hospital General Information (5,432, live) |
| `data/cost_report_2023.csv` | Aggregated CMS HCRIS 2023 |
| `data/hcris_hospital_metrics.csv` | Parsed HCRIS aggregated (5,867 hospitals) |
| `data/hcris_raw/HOSP10FY{2021,2022,2023,2024}.zip` | Raw HCRIS for 4 years (~540 MB) |
| `data/hcris_agency_rates.csv` | **Per-hospital agency rates from NMRC (3,105 hospitals)** |
| `data/per_hospital_rn_wages.csv` | 3-tier per-hospital wage table |
| `data/geo/{zcta_county_2020.txt,cbsa_list_2023.xlsx,zip_cbsa.csv}` | Geographic crosswalks |
| `data/system_level_overlays.csv` | Per-facility MSP overlay $/hr (Kaiser only) |
| `data/market_rate_observations.csv` | **v2 §3 source-governance table (3,288 observations)** |
| `data/snapshots/snapshot_*.parquet` | Daily pricing snapshots |
| `data/alerts/alert_*.md` | Pricing change alert reports |
| `data/hospital_universe.csv` | The unified universe — what the app reads |
| `data/state_benchmarks.csv` | State-level wage + agency benchmarks (fallback) |
| `data/manual_review_report.md`, `manual_review_hospitals.csv` | 739 manual-review hospital categorization |
| `data/top_systems_for_proposals.csv` | Top 15 systems by Florence revenue |

### Documentation
| File | Purpose |
|---|---|
| `CHANGE_LOG.md` | **What changed in the last autonomous overnight run** — START HERE |
| `PRODUCT_PLAN_STATUS.md` | v2 methodology section-by-section status |
| `LIVE_DATA_ROADMAP.md` | Path from v0.6 to fully live continuous data |
| `WHITE_PAPER_REVISIONS.md` | Revised white-paper sections (FICA/visa fix) |
| `MULTI_MARKET_EXAMPLES.md` | 5 worked examples |
| `BUILD_PLAN.md` | Path to FlorenceOS integration |
| `HCRIS_NMRC_NEXT.md` | Original scope doc for raw HCRIS ingest (now DONE) |

### Pre-generated proposals
| Path | What's there |
|---|---|
| `proposals/systems/{system}/*.xlsx`, `*.pdf`, `*.html`, `*_bundle.zip` | Top 10 systems |
| `proposals/systems/MANIFEST.json` | System-bundle manifest |
| `proposals/hospitals/{ccn}_*/*.xlsx`, `*.pdf`, `*.html`, `*_bundle.zip` | Top 50 individual hospitals |
| `proposals/hospitals/MANIFEST.json` | Hospital-bundle manifest |
| `proposals/Cross_System_Comparison_v0.6.pdf` | Top-12 systems side-by-side (landscape PDF) |

---

## To regenerate everything

```bash
# Data layer (~3 min total)
python3 hcris_parser.py
python3 hcris_nmrc_parser.py            # 90s — scans 4 years of NMRC data
python3 build_zip_cbsa_crosswalk.py
python3 wage_estimator.py
python3 geocode_and_systems.py
python3 build_hospital_universe.py      # pass 1
python3 system_overlays.py              # allocate Kaiser $622M
python3 build_hospital_universe.py      # pass 2 with overlays
python3 market_observations.py
python3 snapshots.py

# Tests
python3 test_pricing_engine.py          # 18 tests, ~1s

# Proposals (~3 min to regenerate top 10 + top 50)
python3 cross_system_report.py
python3 manual_review_report.py
# Top 10 system bundles + Top 50 hospital bundles regenerate from app.py code
```

---

## To add a new system-level MSP overlay

Edit `system_overlays.py`. Add to `SYSTEM_OVERLAYS` dict:

```python
"hca": SystemOverlay(
    health_system_id="hca",
    health_system_name="HCA",
    additional_agency_fee_annual=XXX_000_000.0,
    source="...AMN 10-K / system disclosure...",
    as_of_year=2024,
),
```

Then run `python3 system_overlays.py && python3 build_hospital_universe.py`.

---

## What you do NOT use this tool for yet (v0.6 limits)

1. **Binding quotes for hospitals at confidence < 0.85** (~7% of universe). Get customer disclosure first.
2. **Pricing for systems with documented MSP markup but no overlay configured** (HCA, Ascension, etc. — Kaiser is the only one in). The HCRIS-only number under-counts their true agency spend.
3. **MSA-level wages outside the top-60 MSAs** — currently state-fallback for 2,089 hospitals.
4. **Live wage / agency data** — current data is annual refresh (HCRIS, BLS OEWS). The path to daily/weekly live data is in [LIVE_DATA_ROADMAP.md](LIVE_DATA_ROADMAP.md).
