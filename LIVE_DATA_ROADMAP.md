# Live Data Roadmap — Real, Continuous, Dynamic Pricing

The goal: every wage and agency-rate number in the pricing engine comes from a live, dated, source-tracked observation — not a static placeholder. Pricing then refreshes on a cadence and Florence stays competitive in every market at all times.

This document scopes the work to go from where we are today (95% imputed agency rates, 99% imputed wages) to "all rates real" with continuous refresh.

---

## Current state (v0.5)

| Data point | Source today | Refresh | Coverage |
|---|---|---|---|
| Hospital roster | CMS Hospital General Information (live download) | Quarterly | 100% (5,432 hospitals) |
| Per-hospital total salaries, FTE, contract labor $ | HCRIS Hospital Provider Cost Report 2023 | Annual | ~91% (5,028 hospitals) |
| Per-hospital RN-specific wage | BLS state-level placeholder table | Static (hardcoded) | 100% but state-level only |
| Per-hospital agency hourly rate | CommonSpirit anchor (96 hospitals) or state median (rest) | Static | ~2% direct, ~38% state-anchored, ~60% national |
| Operating margin, NPR | HCRIS | Annual | ~90% |
| Contract labor intensity (CL share) | HCRIS | Annual | ~50% (only hospitals that report contract labor) |
| Health system membership | Curated name pattern → ID slug | Static | ~15% of hospitals matched to top-50 systems |
| Geocoding | Census 2024 ZCTA gazetteer (ZIP → lat/lon) | Static (annual) | 100% |

**The two biggest gaps for accuracy:**
1. Per-hospital agency hourly rate — currently 60% nationally imputed
2. MSA-level RN wage — currently state-level placeholder

---

## Roadmap

### Phase A — Foundation (highest accuracy lift, 5-7 days total)

#### A1. Raw HCRIS NMRC ingest (2-3 days)

**Unlocks**: per-hospital agency hourly rate from real contract-labor cost ÷ hours.

Already scoped in `HCRIS_NMRC_NEXT.md`. Summary:
- Download CMS HCRIS Hospital 2552-2010 NMRC files (~3-5 GB per year)
- Parse Worksheet S-3 Part V line items (cost + hours per occupation)
- Join to RPT file on `rpt_rec_num` → CCN
- Compute `adjusted_agency_rate = contract_labor_$ / contract_labor_hours` per hospital
- Schema is already provisioned in `florenceos/db/migrations/011_cms.sql`

Confidence shift: ~50% of US hospitals move from state-imputed (0.40-0.60 confidence) to HCRIS-derived (0.85-0.92).

#### A2. BLS OEWS API ingest (1-2 days)

**Unlocks**: MSA-level RN wages refreshed annually, replacing the state-level hardcoded placeholder.

- Register for BLS public API token (free, 500 requests/day)
- Endpoint: `https://api.bls.gov/publicAPI/v2/timeseries/data/`
- Query series for occupation **29-1141** (Registered Nurses) × all MSAs (~390 MSAs)
- Fields: mean hourly wage, median, P25, P75, P90 by MSA
- Store in `data/bls_oews_msa.csv` with `as_of_year` column
- Annual refresh (BLS publishes May data the following March)

Confidence shift: state-level wage placeholder (0.40) → MSA-level real BLS (0.85).

#### A3. ZIP → CBSA/MSA crosswalk (0.5 day)

**Unlocks**: MSA-level rollups and the BLS join.

- Use HUD-USPS ZIP-CBSA crosswalk file (free quarterly download)
- Or Census Bureau ZIP-to-MSA file
- Join hospitals' ZIP to CBSA code for MSA rollups

#### A4. Live Data Pipeline scheduling (1 day)

**Unlocks**: continuous refresh.

- Cron job / GitHub Actions workflow that runs nightly
- Re-downloads CMS Hospital General Information weekly
- Re-downloads BLS OEWS check-for-new-release monthly
- Re-runs `hcris_parser.py` + `build_hospital_universe.py` on data change
- Triggers Streamlit cache invalidation

---

### Phase B — Market-Pressure & Demand Signals (5-7 days)

#### B1. Travel nurse posting feeds (2-3 days)

**Unlocks**: real-time agency bill-rate signals to validate HCRIS-derived rates.

- Source options (in order of legal cleanliness):
  - Vendor-licensed feeds (NSI, SIA, NATHO — paid)
  - VMS partners' API (Aya, AMN — requires partnership)
  - Public job-board scraping (legal review required for ToS compliance)
- Parse: weekly pay, hours, specialty, MSA, posting date
- Convert: `estimated_bill_rate = weekly_pay × bill_rate_factor / weekly_hours`
- Industry standard `bill_rate_factor` ≈ 1.5-1.8× the take-home pay
- Store in `data/travel_postings.csv` with `as_of_date`, `source`, `confidence_tier`

**Refresh: daily.**

#### B2. Hospital career-page scrape (2-3 days)

**Unlocks**: live staff RN wage signals (replaces / augments BLS).

- Compliant scraping: licensed-feed first (Indeed for Employers feeds, Glassdoor partner data), then publicly-listed hospital career pages
- Parse: posted RN salary range, shift, specialty, MSA
- Convert to hourly using shift-specific hours
- Store in `data/staff_postings.csv` with `as_of_date`, `source`, `confidence_tier`

**Refresh: weekly.**

#### B3. BLS JOLTS/CES pressure indicators (1 day)

**Unlocks**: leading signal for wage pressure (hospitals tightening or loosening).

- BLS JOLTS = Job Openings and Labor Turnover Survey
- Healthcare-specific series (NAICS 622 = hospitals)
- Monthly release, easy API
- Surface in Streamlit as "wage pressure" badge per market

---

### Phase C — Source Governance & Audit (3-5 days)

#### C1. `market_rate_observations` table (2 days)

**Unlocks**: per-source tracking with `as_of_date`, `confidence_tier`, and proper weighted aggregation (v2 §3 source overlay rule).

Schema (matches v2 §Data Model):
```
observation_id (UUID)
as_of_date
source_type    (customer_payroll, msp_invoice, bls_oews, travel_posting, staff_posting, nashp_proxy)
source_name
source_url_or_file
geography      (ccn or msa or state)
specialty
shift
employment_type
hourly_pay     (canonical hourly)
weekly_pay
scheduled_weekly_hours
estimated_bill_rate_factor
posting_count
confidence_tier  (High / Medium / Directional / Low)
```

Each pricing run pulls the median weighted by `confidence × recency`.

#### C2. `hospital_market_snapshot` table (1 day)

Per-hospital, per-snapshot-date roll-up of the chosen rates. Lets us:
- Run "what was the price last month vs. now?" comparisons
- Show pricing trend lines per hospital
- Reproduce historical quotes if disputed

#### C3. NASHP/HCRIS "audited baseline" separation (1 day)

Per v2 §3 — NASHP baseline values are NEVER overwritten by current-market overlay. Today HCRIS is used for both baseline AND for the agency-rate input. Need to separate:
- `nashp_hospital_year` table = immutable audited baseline (refresh annually, version-tagged)
- `hospital_market_snapshot` = scenario overlay computed from live observations

---

### Phase D — Customer-Specific Data (variable; per account)

When Florence onboards an account, that account's own disclosure beats everything else.

#### D1. Customer payroll disclosure → wage source

- Accept CSV or API push: per-RN wages, benefits, shifts
- Confidence tier: **High (1.0)** — overrides all other sources for that customer
- Stored as `source_type = customer_payroll` in `market_rate_observations`

#### D2. Customer MSP/VMS feed → agency rate

- Aya, AMN, Cross Country, Medical Solutions — most healthcare systems have MSP arrangements
- Customer-disclosed agency bill rates and hours per facility
- Confidence tier: **High (1.0)**
- Stored as `source_type = msp_invoice`

#### D3. Customer contract-labor invoice ingest

- Monthly invoice OCR / CSV → contract labor $ and hours per facility
- Validates HCRIS-derived numbers
- Stored as `source_type = customer_invoice`

---

### Phase E — Dynamic Pricing Automation (3-5 days, after A-C complete)

Once observations are flowing continuously, pricing becomes a live computation:

#### E1. Nightly pricing batch

- Cron job re-runs `pricing_batch.py` on the universe with latest observations
- Writes `hospital_pricing_output` snapshot per CCN per snapshot_date
- Streamlit reads latest snapshot

#### E2. Pricing change alerts

- Email/Slack notification when a hospital's recommended fee moves > ±5%
- Surfaces market shifts (e.g., agency rate dropped → suggested fee dropped → competitive pressure)

#### E3. Auto-refresh proposal bundles

- For accounts in active sales: nightly re-generation of Excel + 2-page exec summary with the latest data
- Versioned so we can show "v2026-05-28 quote vs. v2026-05-27 quote"

---

## Refresh cadence summary (v2 §3 aligned)

| Data layer | Refresh | Mechanism |
|---|---|---|
| Customer payroll / MSP / invoices | Monthly (or on customer push) | API or upload |
| Hospital career page postings | Weekly | Licensed feed or scrape |
| Travel nurse postings | Daily | Licensed feed |
| BLS JOLTS/CES | Monthly | BLS API |
| BLS OEWS by MSA | Annual | BLS API |
| HCRIS Hospital Cost Report | Annual | data.cms.gov |
| HCRIS NMRC line items | Annual | CMS quarterly release |
| CMS Hospital General Information | Quarterly | data.cms.gov |
| ZIP → CBSA crosswalk | Quarterly | HUD-USPS |
| BEA Regional Price Parities | Annual | BEA download |

---

## Estimated effort to "all rates real"

| Phase | Days | What's unlocked |
|---|---|---|
| A — Foundation | 5-7 | Per-hospital agency rates (HCRIS NMRC), MSA wages (BLS), CBSA join, scheduling |
| B — Market signals | 5-7 | Travel posting feed, staff posting feed, JOLTS pressure |
| C — Source governance | 3-5 | `market_rate_observations` table, snapshots, NASHP separation |
| D — Customer data ingest | Variable per account | High-confidence wage and agency rates |
| E — Dynamic pricing automation | 3-5 | Nightly refresh, change alerts, auto bundle regeneration |
| **Total foundation (A-C, E)** | **~16-24 days** | Full dynamic-pricing platform across the US universe |

Phase D is ongoing — each new customer adds their disclosure as observations.

---

## Recommended starting point

**Day 1-3: Raw HCRIS NMRC ingest (Phase A1).** Biggest single accuracy unlock — moves ~50% of hospitals' agency rate from imputed to real. Schema and scaffold already in place. This is the highest-leverage first step.

After A1, decide between:
- A2 (BLS OEWS API) — if wage accuracy is the next priority
- C1 (`market_rate_observations`) — if source governance / audit trail is the next priority
- B1 (travel posting feeds) — if real-time market signals are the next priority

Tell me which lane to start.
