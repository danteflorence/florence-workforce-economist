# Live Data Roadmap — Real, Continuous, Dynamic Pricing

The goal: every wage and agency-rate number in the pricing engine comes from a live, dated, source-tracked observation — not a static placeholder.

> **Status (2026-07-12):** most of the original roadmap has shipped. The full original document (phase details, schemas, effort estimates) is archived verbatim at [`docs/archive/2026-07/`](docs/archive/2026-07/) — this file now tracks only what remains.

## Shipped ✅ (verified against code)

- **A1 HCRIS NMRC ingest** — `hcris_nmrc_parser.py` → `data/hcris_agency_rates.csv` (3,105 hospitals)
- **A2 BLS API** — `surveillance/bls_fetch.py` (generic BLS v2 client) + CES RN series
- **A3 ZIP → CBSA crosswalk** — `build_zip_cbsa_crosswalk.py`
- **B3 JOLTS/CES pressure indicators** — `surveillance/jolts_healthcare.py`, `surveillance/ces_rn.py`
- **B1 (public-signal portion)** — `surveillance/job_postings.py`
- **C1 `market_rate_observations`** — `market_observations.py` + `data/market_rate_observations.csv`
- **C2 snapshots** — `snapshots.py` (daily parquet, point-in-time reproducibility)
- **E2 pricing change alerts** — `pricing_alerts.py`
- **Provenance/vintage governance** — `provenance.py` (data vintages + freshness ladder on every buyer-facing number)
- **D3-adjacent outcome loop** — close-out capture, pricing calibration, invoice re-price (git `2f6c08a`)

## Still open (original wording preserved)

### B1 — Travel nurse posting feeds (licensed portion)
Vendor-licensed feeds (NSI, SIA, NATHO — paid) or VMS partners' API (Aya, AMN — requires partnership). Convert `estimated_bill_rate = weekly_pay × bill_rate_factor / weekly_hours` (factor ≈ 1.5-1.8×). Refresh: daily.

### B2 — Hospital career-page scrape
Compliant scraping: licensed-feed first (Indeed for Employers feeds, Glassdoor partner data), then publicly-listed hospital career pages. **Legal review required for ToS compliance** before any scraping. Refresh: weekly.

### C3 — NASHP/HCRIS "audited baseline" separation
Per v2 §3 — NASHP baseline values are NEVER overwritten by current-market overlay. Need: `nashp_hospital_year` immutable audited baseline (annual, version-tagged) vs `hospital_market_snapshot` scenario overlay. `provenance.py` tracks vintages; the baseline-immutability separation itself still needs verification/completion.

### A4/E1 — Scheduled refresh pipeline
Cron/GitHub Actions nightly re-run of ingest + `pricing_batch.py` with cache invalidation. (Local surveillance cadences + daily backups exist; a CI-scheduled full pipeline does not.)

### E3 — Auto-refresh proposal bundles
For accounts in active sales: nightly regeneration of Excel + exec summary, versioned ("v2026-05-28 quote vs v2026-05-27 quote").

### Phase D — Customer-specific data (ongoing, per account)
Customer payroll disclosure (confidence 1.0, overrides all sources) · customer MSP/VMS feeds · contract-labor invoice ingest. Each new account adds observations.
