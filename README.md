# Florence Labor Economics Agent

National pricing engine for permanent RN placement. For every Medicare-registered U.S. hospital (5,432 facilities), produces a Florence fee per the v2 methodology — see [`playbook/04_pricing_methodology.md`](playbook/04_pricing_methodology.md) ("How our pricing works").

Engine `v0.5-methodology-v2-2026-05` (see `pricing_engine.py` `version`) · data layer v0.6 — status in [PRODUCT_PLAN_STATUS.md](PRODUCT_PLAN_STATUS.md).

**Default mode**: FICA-offset target pricing on an F-1 cohort, 24-month term, $750–$2,000/RN/month guardrails. Per-hospital agency rates from raw HCRIS NMRC line items (`data/hcris_agency_rates.csv` — 3,105 hospitals). System-level MSP overlays for **12 systems** (Kaiser anchored by the AMN $622M disclosure; full list = `SYSTEM_OVERLAYS` in `system_overlays.py`).

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

App opens at http://localhost:8501. First load ~5s for the 5,432-hospital batch. Deployment (Render, Core SSO env, CI): [DEPLOY.md](DEPLOY.md).

Pre-generated proposal bundles for the top 10 systems live in [`proposals/systems/`](proposals/systems/); top 50 individual hospitals in [`proposals/hospitals/`](proposals/hospitals/) (Excel 10 tabs + 2-page exec PDF + HTML each).

---

## Shipped since the v0.6 data pass (verified against git log, Jun–Jul 2026)

- **Surveillance set** (`surveillance/`) — BLS API client, OEWS/CES RN series, JOLTS healthcare pressure, job-postings signal, CMS Care Compare quarterly refresh + delta detection, morning briefing generator.
- **Provenance + confidence** (`provenance.py`) — every buyer-facing number carries its data vintage (OEWS, HCRIS, NASHP/PECOS) with a soft/hard freshness ladder; Streamlit Data-provenance tab.
- **Outcome loop** — close-out capture, pricing calibration, invoice re-price, UTM attribution.
- **Core SSO** (`core_auth.py`, wired in `render.yaml`) + market-lookup pricing path (`market_lookup.py`, `pricing_api.py` `/lookup` + `/price-job`).
- **Client Deck** — data-driven HTML pitch-deck generator, in-app export, per-system wordmarks; whole tool aligned to the Florence deck design system (`florence_theme.py`).
- **Capacity Outreach Engine** (`capacity-outreach/`) — Lob health-system booklet + home-health postcard mailers, tracked QR/UTM.
- **Distribution flywheel** — inbound leads → pipeline, gated industry report.
- **Reliability/CI** — full test suite on every push, pinned native deps, error monitoring, daily backups.

History of how the data layer got here: [`docs/archive/2026-07/`](docs/archive/2026-07/) (overnight-run logs, executed build plans, white-paper revision sections).

## Data layer at the v0.6 pass (May 28 2026)

| Layer | Status |
|---|---|
| Pricing engine | v2 methodology, FICA_OFFSET_TARGET default, unit tests in `test_pricing_engine.py` |
| Hospital roster | 5,432 (CMS HGI, live) |
| Per-hospital agency hourly rate | **3,105 hospitals from raw HCRIS NMRC 2021-2024** (`data/hcris_agency_rates.csv`) |
| Per-hospital RN wage | 3-tier: BLS OEWS MSA top-60 → HCRIS-blended × multiplier → state fallback |
| ZIP → CBSA crosswalk | Census 2020 ZCTA + 2023 CBSA (18,475 ZIPs in MSAs) |
| System-level MSP overlays | 12 systems configured (`system_overlays.py`) |
| Source governance | `market_rate_observations` table |
| Snapshot persistence | Daily parquet snapshots for point-in-time reproducibility |
| Pricing change alerts | Snapshot diff → markdown alerts |
| Outputs | Excel (10 tabs), 2-page PDF, HTML, Markdown; Client Deck HTML |

Headline national/Kaiser dollar figures from the v0.6 snapshot are preserved in `docs/archive/2026-07/CHANGE_LOG.md` — **regenerate via `pricing_batch.py` for current numbers** rather than quoting the archive.

---

## Files

### Pricing engine + batch
| File | Purpose |
|---|---|
| `pricing_engine.py` | Canonical v2 pricing math, PricingMode enum, 5 buyer-facing numbers, immigration add-on, manual-review logic, IRS compliance sentence |
| `pricing_batch.py` | `price_batch()` over the universe, `calibration_sweep()`, `market_aggregate()` |
| `test_pricing_engine.py` | Unit tests for formula, manual-review, guardrails, FICA, partner split, rollups |

### Data ingest + universe build
| File | Purpose |
|---|---|
| `build_hospital_universe.py` | Stitches all sources into `data/hospital_universe.csv` |
| `hcris_parser.py` | CMS aggregated Hospital Provider Cost Report parser |
| `hcris_nmrc_parser.py` | **Raw HCRIS NMRC parser — per-hospital agency $/hr** (S-3 Part II line 01100) |
| `wage_estimator.py` | 3-tier per-hospital RN wage (BLS MSA > HCRIS blended > state) |
| `build_zip_cbsa_crosswalk.py` | ZIP → County → CBSA/MSA mapping |
| `geocode_and_systems.py` | ZCTA centroids + curated health-system inference |
| `system_overlays.py` | System-level MSP overlay allocator (12 systems) |
| `market_observations.py` | Builds v2 §3 `market_rate_observations` table |
| `snapshots.py` | Point-in-time pricing snapshot writer/reader |
| `pricing_alerts.py` | Snapshot diff → pricing change alerts |
| `provenance.py` | Data-vintage source of truth + freshness ladder |
| `surveillance/` | BLS/JOLTS/CES/postings/Care-Compare refresh + briefing |

### Output generators + app
| File | Purpose |
|---|---|
| `excel_writer.py` | 10-tab Excel workbook per v2 §8 (per hospital or per system) |
| `exec_summary.py` | 2-page executive summary (HTML + PDF via reportlab) |
| `cross_system_report.py` | Top-12 systems side-by-side (HTML + PDF, landscape) |
| `manual_review_report.py` | Categorized explanation of manual-review hospitals |
| `app.py` | Streamlit app (tab list in code is the source of truth) |
| `pricing_api.py` / `market_lookup.py` | HTTP pricing API (`/lookup`, `/price-job`) with optional Core M2M auth |
| `capacity-outreach/` | Lob outbound creatives + senders |

### Data
Source-of-truth files live in `data/` — the unified universe the app reads is `data/hospital_universe.csv`; per-file inventory is visible in the ingest scripts above and the Streamlit Data-provenance tab.

### Documentation
| File | Purpose |
|---|---|
| `PRODUCT_PLAN_STATUS.md` | Current engine/data status + verified open items |
| `LIVE_DATA_ROADMAP.md` | Remaining path to fully live continuous data (executed phases collapsed) |
| `DEPLOY.md` | Deployment, CI, Core SSO env |
| `ARCHITECTURE.md` | Surfaces overview (see banner for date scope) |
| `MULTI_MARKET_EXAMPLES.md` | 5 worked examples |
| `playbook/` | Sales playbook incl. `04_pricing_methodology.md` |
| `docs/archive/2026-07/` | History: overnight-run logs, executed plans, white-paper revisions |

---

## To regenerate the data layer

```bash
python3 hcris_parser.py
python3 hcris_nmrc_parser.py            # ~90s — scans 4 years of NMRC data
python3 build_zip_cbsa_crosswalk.py
python3 wage_estimator.py
python3 geocode_and_systems.py
python3 build_hospital_universe.py      # pass 1
python3 system_overlays.py              # allocate MSP overlays
python3 build_hospital_universe.py      # pass 2 with overlays
python3 market_observations.py
python3 snapshots.py
python3 test_pricing_engine.py
```

## To add a new system-level MSP overlay

Edit `system_overlays.py` — add a `SystemOverlay(...)` entry to `SYSTEM_OVERLAYS` (source it to a public disclosure, e.g. an AMN 10-K), then:

```bash
python3 system_overlays.py && python3 build_hospital_universe.py
```

---

## Known limits (verify before quoting)

1. **Binding quotes for hospitals at confidence < 0.85** — get customer disclosure first (confidence lives per-row in the universe; Data-provenance tab shows the distribution).
2. **Systems with documented MSP markup but no configured overlay** under-count true agency spend — check `SYSTEM_OVERLAYS` before quoting a large system.
3. **MSA-level wages outside the top-60 MSAs** fall back to state level.
4. **Refresh cadence is annual/quarterly for the core sources** — the path to daily/weekly live data is [LIVE_DATA_ROADMAP.md](LIVE_DATA_ROADMAP.md); surveillance signals supplement but do not yet replace the core sources.
