# Status — Florence Workforce Restoration Economics

Last verified against code/git: **2026-07-12**. Point-in-time v0.6 analysis (Kaiser evolution tables, national headline dollars, overnight-uplift narrative) is archived verbatim in [`docs/archive/2026-07/`](docs/archive/2026-07/) — regenerate current numbers with `pricing_batch.py`; do not quote archived dollars.

Engine version: **`v0.5-methodology-v2-2026-05`** (source of truth: `pricing_engine.py` → `version`).
Data layer: **v0.6** (per-hospital NMRC agency rates: `data/hcris_agency_rates.csv`, 3,105 hospitals).

## Default pricing posture (confirmed decisions — load-bearing)

- F-1 cohort, 2-year placement → IRC §3121(b)(19) employer FICA exemption reliable
- η = 1.0 default (per IRS guidance + user confirmation)
- 24-month contract term, all 24 months FICA-eligible
- FICA_OFFSET_TARGET pricing mode at 50% target
- $750–$2,000/RN/month guardrails
- Immigration transition add-on: toggleable

## Data sources in production

| Source | What it provides | Refresh | Status |
|---|---|---|---|
| CMS Hospital General Information | Roster, address, type, ownership | Quarterly | Live |
| CMS HCRIS (aggregated) | Per-hospital salaries, FTE, contract labor $ | Annual | Live |
| CMS HCRIS NMRC (raw line items) | Per-hospital contract labor $/hr | Annual | Live (FY2021-2024) |
| BLS OEWS (MSA top-60 + state) | RN wages | Annual | Live; API client in `surveillance/bls_fetch.py` |
| BLS JOLTS / CES | Market-pressure signals | Monthly | Live (`surveillance/`) |
| Census ZCTA-County-CBSA | Geographic crosswalk | Annual | Live |
| System-level MSP overlays | Markup not captured in HCRIS | Per-system manual | **12 systems configured** (`system_overlays.py`) |
| Data vintages / freshness | Per-number provenance | Continuous | `provenance.py` + Streamlit provenance tab |

## Shipped since v0.6 (git-verified)

Surveillance set · provenance/confidence vintages · outcome loop (close-out capture, pricing calibration, invoice re-price, UTM attribution) · Core SSO + pricing API (`/lookup`, `/price-job`) · Client Deck + design-system alignment · Capacity Outreach Engine (Lob) · distribution flywheel (inbound leads, gated industry report) · CI full suite + pinned deps + monitoring + backups. Details: `git log` + [README](README.md).

## Still open (verified 2026-07-12)

| Item | Notes |
|---|---|
| Hospital career-page wage scraping | Compliance-gated — legal/ToS review before any scraping (same gate as the ATS demand connectors) |
| Licensed travel-posting feeds (NSI/SIA/vendor) | `surveillance/job_postings.py` covers public signals; licensed feeds need vendor access |
| Excel workbooks formula-driven (vs hardcoded values) | v2 §10 validation requirement |
| Word proposal generator | v2 §Required Outputs — no docx path in repo |
| AHA Annual Survey CCN → system mapping | System inference is still curated-keyword (`geocode_and_systems.py`); AHA lifts coverage |
| NASHP audited-baseline immutability | `provenance.py` tracks vintages; verify the baseline-vs-overlay separation before claiming v2 §3 compliance |
| Additional MSP overlays | Add per public disclosure as encountered (12 configured today) |

## To run

```bash
cd /Users/dantetolbedantert/florence-work/labor-economics-agent
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
streamlit run app.py       # tabs incl. Data provenance; deploy details in DEPLOY.md
```

Data-layer regeneration steps: [README → "To regenerate the data layer"](README.md).
