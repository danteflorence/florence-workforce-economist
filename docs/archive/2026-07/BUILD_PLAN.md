# Build Plan — Florence Labor Economics Agent

Mapping the agent onto the existing FlorenceOS + Care Capacity Index codebases. Goal: build minimum-viable agent in roughly 4–6 weeks by extending what's already there, rather than building parallel infrastructure.

## What we already have (strong foundations)

| Component | Where it lives | What it does | Reusability |
|---|---|---|---|
| FICA capture math | `care-capacity-index/src/lib/ficaAdvantage.ts` | Employer FICA savings calc with IRS-cited constants, eligibility factor, exempt-year window | **Direct reuse** — the math is correct; just needs to be called from the new pricing engine instead of from the system-level EBIT model |
| System-level economics | `care-capacity-index/src/lib/calculations.ts` | Weighted means, growth modeling, 3-year EBIT/EPS/EV, FICA system roll-up | **Partial reuse** — keep `weightedMean`, `resolveStaffRate`; the 3-year EBIT roll-up belongs in a system-view product, not in per-hospital pricing |
| Hospital data model | `care-capacity-index/src/types/hospital.ts`, `florenceos/src/types/hospitalData.ts` | `HospitalData` interface with CCN, staff rate, agency rate, RN need, ED metrics, peer-comparison fields | **Extend** — add visa-cohort assumptions, MSP fee allocation, role/specialty breakdown |
| CommonSpirit demo dataset | `florenceos/supabase/functions/demo-ingest-data-v2/data.ts` | 100+ real facilities with contracted spend, agency rate, staff rate, RN need FTE, per-RN savings | **Direct reuse** as the seed dataset for the agent |
| CMS HCRIS ingest | `florenceos/services/cms-ingest/`, `db/migrations/011_cms.sql` | Federal cost report ingestion (`raw_cms.hcris_lines`, `raw_cms.pbj_hours`, `dm.hospital_costs_yearly`, `dm.agency_trend_10y`) | **Direct reuse** for hospital-economics inputs |
| Job-board ingest | `florenceos/services/connectors/greenhouse/`, `lever/` | ATS API → `ats.ats_job` with location/shift/employment-type parsing | **Direct reuse**; the pricing engine consumes ATS job records to estimate market demand and wage ranges |
| VMS aggregator | `florenceos/src/services/vms.ts`, `supabase/functions/fulfillment-orchestrator/`, `supabase/migrations/vms_bookings.sql` | Aya, AMN integration with cost-tracking | **Reuse for agency-rate observation** — `vms_bookings` is the cleanest existing source of all-in agency rates |
| Pipeline stage tracking | `care-capacity-index/supabase/functions/data-match/` | Recruiting → NCLEX → Visa → Cleared → Arrived stages with conversion probability | **Direct reuse** — this is exactly the nurse-supply data the pricing engine needs |
| Peer matching | `florenceos/supabase/functions/suggest-hospital-matches/` | Confidence-scored peer identification, `hospital_matches` table | **Partial reuse** — extend for opportunity-score ranking |
| Reliability scoring | `florenceos/supabase/migrations/clinician_reliability.sql`, `LABOR_FULFILLMENT_SCORING.md` | Per-clinician reliability formula (acceptance/completion/on-time/cancellation) | **Adapt** — feeds the conversion-probability adjustment in the agent |

## What needs to be built

1. **Single-hospital pricing engine** (TypeScript port of `pricing_engine.py`)
2. **Visa-cohort composition resolver** — given a hospital + role + market, what is η for the actual placeable pipeline?
3. **Agency-rate observation pipeline** — combine VMS bookings + MSP invoices + travel postings into A_hat(h, r, m) with confidence
4. **Wage observation pipeline** — BLS OEWS + ATS job postings + hospital career pages into W_hat(h, r, m) with confidence
5. **Opportunity score + ranker** — formalize the §11 score on top of the existing peer-matching infra
6. **Evidence-pack generator** — Edge function that emits the CFO one-pager from a pricing run
7. **Weekly market surveillance job** — cron that re-runs the scoring + ranking and writes the weekly target list
8. **Calibration audit log** — versioned constants + change approvals (Postgres table + UI)

---

## Build sequence

### Phase 1 — Pricing engine in the repo (week 1)

**Files to add:**

- `care-capacity-index/src/lib/pricingEngine.ts` — TypeScript port of `pricing_engine.py`. Signature:
  ```ts
  export interface PricingInput {
    hospital: HospitalProfile;
    cohort: CohortMix;
    calibration?: Partial<Calibration>;
  }
  export function price(input: PricingInput): PricingResult;
  ```
- `care-capacity-index/src/lib/pricingEngine.test.ts` — Vitest unit tests that reproduce the five examples in `MULTI_MARKET_EXAMPLES.md`. **The tests should fail loudly if the math drifts** — the multi-market table is the regression baseline.
- `care-capacity-index/src/types/hospital.ts` — extend `Assumptions` with `delta_target`, `delta_cap`, `delta_floor`, `zeta`, `cohort_eta` (defaulted but overridable). Keep all existing FICA fields.

**Wiring:** call `pricingEngine.price()` from `calculations.ts` instead of `computeFicaAdvantage()` directly when computing per-hospital fees. The system-level EBIT/EPS roll-up calls `price()` per hospital and aggregates.

**Decision to make in week 1:** does δ_target scale with market wage (e.g., δ = α × W with α tuned), or stay market-independent at $2.50? See §3 commentary in `MULTI_MARKET_EXAMPLES.md`. Strong recommendation: keep market-independent for v1, revisit when pilot data is in.

### Phase 2 — Data layer: agency-rate observation (weeks 1–2)

**Files to add:**

- `florenceos/db/migrations/0XX_agency_rate_observations.sql` — table:
  ```sql
  CREATE TABLE agency_rate_observations (
    id bigserial primary key,
    hospital_id text references hospitals(id),
    msa_code text,
    role text,
    specialty text,
    observed_at timestamptz,
    source text,         -- 'vms_booking' | 'msp_invoice' | 'travel_posting' | 'customer_disclosure'
    bill_rate_per_hr numeric,
    includes_msp_fee boolean,
    msp_fee_share numeric,
    confidence numeric,  -- 0..1 derived from source × recency × precision
    raw_payload jsonb
  );
  ```
- `florenceos/services/agency-rate-aggregator/main.py` — consumes `vms_bookings` (existing), unstructured MSP invoices (manual upload via Supabase edge function), and travel-posting feeds; writes to `agency_rate_observations`. Runs nightly.
- `florenceos/src/services/agencyRateEstimator.ts` — exposes `estimateAgencyRate(hospital, role, market): { A_hat, confidence, sources }` using the source-weighted Bayesian aggregation from white paper §9.

**Reuse:** `vms_audit_log` and `vms_bookings` already capture real Aya/AMN bookings with cost. That's the most reliable input. MSP fee allocation logic from `VMS_AGGREGATOR.md` should be lifted into the estimator.

### Phase 3 — Data layer: wage observation (week 2)

**Files to add:**

- `florenceos/services/bls-oews-ingest/main.py` — Python job that pulls BLS OEWS RN wages by MSA annually. Writes to `bls.oews_wages`.
- `florenceos/db/migrations/0XX_bls_oews.sql` — table for OEWS observations.
- `florenceos/services/wage-estimator/` — combines BLS OEWS, ATS job postings (already in `ats.ats_job`), and hospital career-page scrapes into `W_hat(h, r, m)`.
- `florenceos/src/services/wageEstimator.ts` — `estimateWage(hospital, role, market): { W_hat, confidence, sources }`.

**Reuse:** the Greenhouse + Lever connectors already populate `ats.ats_job`. The wage estimator just adds a parser pass to extract salary ranges from job descriptions (LLM-driven extraction is appropriate here; this is the genuine AI piece of the agent).

**Note on hospital career-page scraping:** check the legal review before turning on automated scraping. Public job postings are usually fine; some hospital sites have ToS prohibitions. Default to documented opt-in / public-API sources first.

### Phase 4 — Visa-cohort composition resolver (week 3)

**Files to add or extend:**

- `care-capacity-index/supabase/functions/data-match/index.ts` already has pipeline stages. **Extend** to expose visa class per candidate:
  ```ts
  type VisaClass = 'F1' | 'J1' | 'M1' | 'Q1' | 'Q2' | 'H1B' | 'EB3' | 'TN' | 'GC' | 'USC' | 'OTHER';
  type CandidateRecord = {
    /* ...existing fields... */
    visaClass: VisaClass;
    visaStatusValidFrom?: string;
    nonresAlienExitDate?: string;  // estimated date taxpayer becomes resident alien
    targetHospitalIds: string[];
  };
  ```
- `florenceos/src/services/cohortResolver.ts` — given a hospital + role + market + commitment-start date, return the projected cohort visa mix:
  ```ts
  export function resolveCohort(
    hospitalId: string,
    role: string,
    market: string,
    placementHorizonMonths: number = 18
  ): {
    eta: number;                    // FICA-exempt share
    expectedExemptHours: number;    // average per-nurse, accounting for exit dates
    cohortSize: number;
    cohortBreakdown: Record<VisaClass, number>;
    confidence: number;
  };
  ```

**Hard rule for §15.2 enforcement:** the pricing engine refuses to use η > resolveCohort().eta + 0.1 without an explicit override flag and an approver user ID logged.

### Phase 5 — Opportunity score and ranker (week 3–4)

**Files to add:**

- `florenceos/supabase/functions/opportunity-score/index.ts` — implements white paper §11:
  ```
  OpportunityScore(h, r, m, t) =
      0.20 × AgencyPremiumScore
    + 0.20 × OpeningsScore
    + 0.15 × PostingAgeScore
    + 0.15 × ContractedRNFTEOpportunityScore
    + 0.10 × FlorenceSupplyFitScore
    + 0.10 × HospitalFinancialCapacityScore
    + 0.05 × ChannelAccessScore
    + 0.05 × DataConfidenceScore
    - 0.10 × ComplexityPenalty
  ```
- `florenceos/db/migrations/0XX_opportunity_scores.sql` — snapshot table for weekly scores.
- **Reuse:** `suggest-hospital-matches/` for peer-cohort fields; `dm.hospital_costs_yearly` for financial capacity; `data-match` for Florence supply fit.

### Phase 6 — Evidence pack generator (week 4)

**Files to add:**

- `care-capacity-index/supabase/functions/generate-evidence-pack/index.ts` — input: `{ hospitalId, role, cohortOverride? }`. Output: rendered PDF + JSON of `PricingResult` plus market context. Use the existing `render_evidence_pack()` logic from `pricing_engine.py` as the template.
- `care-capacity-index/src/components/EvidencePackView.tsx` — React view to render the same content interactively. Reuses `PeerComparePanel` styling.

**Hard requirement:** every evidence pack must include the tax-assumption block from §15.1 and must show the η = 0 fallback fee even when proposing an η > 0 quote.

### Phase 7 — Weekly market surveillance (week 5)

**Files to add:**

- `florenceos/services/weekly-surveillance/main.py` — cron job that runs every Monday. Re-estimates wage/agency rates, runs `price()` for the top 200 target hospitals across the three cohort scenarios, computes opportunity scores, and produces:
  1. `weekly_opportunity_list` table snapshot
  2. Markdown report committed to a `surveillance-reports/` directory (or sent via the existing notification rail)
  3. Slack/email digest with the top 50

- Schedule: GitHub Actions cron (`.github/workflows/weekly-surveillance.yml`) or Supabase scheduled function.

### Phase 8 — Calibration audit + governance (week 5–6)

**Files to add:**

- `florenceos/db/migrations/0XX_pricing_calibration_history.sql`:
  ```sql
  CREATE TABLE pricing_calibration_history (
    version text primary key,        -- e.g., 'v0.1-2026-05'
    effective_from timestamptz,
    effective_to timestamptz,
    delta_target numeric,
    delta_cap numeric,
    delta_floor numeric,
    zeta numeric,
    f_floor_by_market jsonb,
    approved_by text,
    approved_at timestamptz,
    change_rationale text
  );
  CREATE TABLE pricing_quotes (
    id bigserial primary key,
    quoted_at timestamptz,
    hospital_id text,
    role text,
    cohort_eta numeric,
    calibration_version text references pricing_calibration_history(version),
    f_base numeric,
    f_fica numeric,
    f_total numeric,
    delta_chosen numeric,
    feasible boolean,
    channel text,
    overridden boolean,
    overridden_by text,
    realized_outcome jsonb           -- backfilled with accept/decline/start/retention
  );
  ```
- `care-capacity-index/src/components/CalibrationAdmin.tsx` — admin UI to propose/approve calibration changes. Two-person rule for production changes.

This is what feeds Phase 5 of the original white paper roadmap (closed-loop learning). Realized outcomes against quoted prices is the only data that lets us tune δ_target empirically.

---

## What we deliberately do NOT build in v1

- **Bias/fairness review on visa-class data.** Defer until counsel review of the entire visa-cohort feature. Use of `visaClass` to set price needs explicit legal sign-off, especially in jurisdictions with broad national-origin discrimination protection. We can implement the technical infrastructure but should not turn on visa-conditional pricing in production quotes until that review completes.
- **NCLEX predictor.** The white paper §13 leaves room for this but it's a separate product. The pricing engine doesn't need it.
- **Real-time wage scraping at quote time.** The agent runs weekly. Quote-time data freshness is a v2 optimization.
- **Multi-currency / international pricing.** All numbers are USD. International placement support stays in the recruitment side.
- **LLM-driven recommendations to sales.** The agent outputs structured data + evidence packs. Conversational interfaces are not on the path to credibility — the math being right is.

---

## File-system layout proposal

```
florenceos/
  services/
    agency-rate-aggregator/     [new]
    bls-oews-ingest/            [new]
    wage-estimator/             [new]
    weekly-surveillance/        [new]
  src/services/
    agencyRateEstimator.ts      [new]
    wageEstimator.ts            [new]
    cohortResolver.ts           [new]
  supabase/functions/
    opportunity-score/          [new]
    generate-evidence-pack/     [new — could live in either repo]
  db/migrations/
    0XX_agency_rate_observations.sql      [new]
    0XX_bls_oews.sql                       [new]
    0XX_opportunity_scores.sql             [new]
    0XX_pricing_calibration_history.sql    [new]

care-capacity-index/
  src/lib/
    pricingEngine.ts            [new — TS port of pricing_engine.py]
    pricingEngine.test.ts       [new]
    ficaAdvantage.ts            [existing — keep]
    calculations.ts             [extend to call pricingEngine]
  src/components/
    EvidencePackView.tsx        [new]
    CalibrationAdmin.tsx        [new]
  src/types/
    hospital.ts                 [extend Assumptions]
  supabase/functions/
    data-match/                 [extend with visa class]
```

The Python `pricing_engine.py` in this folder stays as the **canonical reference implementation**. The TypeScript port must produce identical numbers for the five test cases in `MULTI_MARKET_EXAMPLES.md`. Cross-language drift is the failure mode to watch for; the test suite enforces parity.

---

## Estimated effort

| Phase | Effort | Critical path? |
|---|---|---|
| 1 — Pricing engine in repo | 3–5 days | Yes — everything downstream depends on it |
| 2 — Agency-rate observation | 5–7 days | Yes — without A_hat the model can't price |
| 3 — Wage observation | 5–7 days | Parallel to phase 2 |
| 4 — Cohort resolver | 4–6 days | Yes — without η the FICA component is unconstrained |
| 5 — Opportunity score | 3–5 days | No |
| 6 — Evidence pack | 3–4 days | Yes — this is the CFO deliverable |
| 7 — Weekly surveillance | 2–3 days | No (manual runs work for early pilots) |
| 8 — Calibration governance | 4–6 days | Yes — needed before production quotes |

**Total: roughly 4–6 calendar weeks for one engineer, or 3 weeks with two engineers running phases 2/3 in parallel and phases 5/6/7 in parallel.**

The single highest-risk dependency is the visa-class data feature (phase 4) clearing legal review. Recommend kicking off that review in week 1 so it doesn't gate go-live.
