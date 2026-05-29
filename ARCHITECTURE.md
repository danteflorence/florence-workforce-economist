# Florence Workforce Intelligence — Architecture

A continuously-updating, multi-surface workforce intelligence platform for the
U.S. nursing labor market.

## Surfaces

```
┌─────────────────────────────────────────────────────────────────┐
│                  Florence Workforce Intelligence                 │
├──────────────────┬──────────────────┬───────────────────────────┤
│ Internal         │ Public           │ Nurse (login-gated)       │
│ (Florence team)  │ (Operators)      │ (Florence-placed RNs)     │
├──────────────────┼──────────────────┼───────────────────────────┤
│ app.py           │ customer_        │ nurse_portal.py           │
│                  │   calculator.py  │                           │
│ Port 8501        │ public_market_   │ Port 8504                 │
│                  │   intel.py       │                           │
│                  │                  │                           │
│                  │ Ports 8502, 8503 │                           │
└──────────────────┴──────────────────┴───────────────────────────┘
         │                  │                       │
         └──────────┬───────┴───────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │   Shared core        │
         ├──────────────────────┤
         │ pricing_engine.py    │  ← FLAT_PLACEMENT_FEE + FICA_OFFSET_TARGET
         │ recommendation_      │
         │   engine.py          │  ← 3-tier bands per facility
         │ non_hospital_        │
         │   pricing.py         │  ← Capacity-expansion model
         │ system_overlays.py   │  ← MSP markup (Kaiser AMN $622M etc.)
         │ system_overrides.py  │  ← M&A scenario overrides
         │ system_fee_          │
         │   overrides.py       │  ← Per-system flat-fee tuning
         └──────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  Live data sources   │
         ├──────────────────────┤
         │ surveillance/        │
         │   jolts_healthcare   │  ← BLS JOLTS monthly
         │   ces_rn             │  ← BLS CES monthly
         │   oews_state_rn      │  ← BLS OEWS annual
         │   cms_care_compare   │  ← CMS quality, quarterly
         │   news_feeds         │  ← AHA News / Becker's, daily
         │   ownership_changes  │  ← Diff vs prior snapshot
         │   pricing_alerts     │  ← Pricing drift detection
         │   forecast           │  ← SARIMA 12-month projection
         │   briefing           │  ← Unified summary
         └──────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  AI Q&A layer        │
         │  ai_qa/              │  ← Anthropic Claude API
         │  Falls back to       │     (graceful when no key)
         │  rule-based parser   │
         └──────────────────────┘
```

## Static data assets

```
data/
├── hospital_universe.csv              5,432 hospitals (CMS + NASHP joined)
├── non_hospital_facilities.csv        47,113 ASCs/HHAs/SNFs/Hospices/Dialysis
├── recommendations.parquet            Pre-computed 3-tier per-facility
├── non_hospital_priced.parquet        Pre-computed FICA-only pricing
├── state_benchmarks.csv               BLS OEWS state-level RN wages
│
├── system_overrides.json              M&A scenario reassignments
├── system_flat_fee_overrides.json     Per-system custom fees
├── customer_leads.csv                 Lead capture from /calculator
├── nurse_access_codes.csv             Nurse portal demo accounts
│
├── raw_cms_non_hospital/              CMS Provider Data Catalog dumps
├── raw_cms_pecos/                     PECOS authoritative ownership
│
└── surveillance/                      All time-series feeds
    ├── jolts_healthcare/
    ├── ces_rn/
    ├── oews_state_rn/
    ├── cms_care_compare/
    ├── news_feeds/
    ├── ownership_snapshots/
    ├── pricing_snapshots/
    ├── forecasts/
    └── briefings/
```

## Pricing model

Two modes, toggled in the internal app sidebar:

**FLAT_PLACEMENT_FEE** (default)
- $50,000 per RN, amortized over 36 months
- Per-system overrides supported (Kaiser $50K, HCA $40K, Sutter $60K, etc.)
- Mode-aware manual-review: pricing works even where agency premium math
  fails (gains 691 hospitals vs FICA-offset mode)

**FICA_OFFSET_TARGET**
- Florence fee = FICA savings ÷ target_offset_pct (40% default)
- Clamped between $750–$2,000/RN/month
- Captures more value where agency premium is large
- Internal-only — the FICA mechanism is never displayed publicly

**Partner channel model**: markup ATOP Florence's core rate
- Florence's net is protected at the core fee regardless of channel
- AMN (or other partner) margin is added on top
- Customer pays florence_fee × (1 + partner_markup_pct)
- Florence collects florence_fee always

## Surveillance feeds

Each feed writes snapshots to `data/surveillance/<feed>/YYYY-MM-DD.{csv,json}`
and appends to a long-history CSV. Briefings compare today vs prior to surface
deltas.

| Feed | Cadence | Auth | Source |
|---|---|---|---|
| JOLTS healthcare | Monthly | None | BLS Public Data API v2 |
| CES nursing employment | Monthly | None | BLS Public Data API v2 |
| OEWS state RN wages | Annual May | None | BLS Public Data API v2 |
| CMS Care Compare | Quarterly | None | data.cms.gov Provider Data Catalog |
| Healthcare news | Daily | None | AHA News + Becker's RSS feeds |
| Ownership changes | Daily | None | Self-diff vs prior universe snapshot |
| Pricing alerts | Daily | None | Self-diff vs prior recommendations |
| Forecasting | Monthly | None | SARIMA on JOLTS history (statsmodels) |

Anonymous BLS API allows 25 series/day. Register for a free key at
data.bls.gov/registrationEngine for 500 req/day. Set as `BLS_REGISTRATION_KEY`
in env.

## AI Q&A layer

Drops Anthropic Claude in front of the data with the workforce schema in the
system prompt. The model converts user questions to JSON plans which our
responder executes against pandas DataFrames.

Set `ANTHROPIC_API_KEY` in env to enable. Without a key, the system gracefully
falls back to the rule-based parser already in the Market Intelligence tab.

Architecture:
```
User query
    │
    ▼
ai_qa/router.py
    │
    ├──→ has_api_key()? → No  → fall back to rule-based parser
    │
    └──→ Yes
            │
            ▼
        ai_qa/llm_client.py  (Anthropic SDK + schema system prompt)
            │
            ▼
        ai_qa/responder.py   (Executes JSON plan against datasets)
            │
            ▼
        Result: {kind, data, narrative, source}
```

## Public-facing surfaces (compliance-critical)

All public surfaces (`customer_calculator.py`, `public_market_intel.py`,
`customer_pdf_report.py`, generated customer decks) are scrubbed of:
- FICA / payroll tax mechanism language
- IRC §3121(b)(19) / IRS Pub 519 citations
- F-1 visa specifics or "nonresident-alien" framing
- Tax counsel references

Customer-facing pitch leads with: **capacity expansion + revenue uplift + flat
$50K placement fee**. The FICA mechanism is Florence's internal pricing
intelligence, not a customer-marketing angle.

Internal surface (`app.py`) retains full methodology including FICA math, IRS
citations, and tax-counsel references — that's how Florence sales reps
internally understand the unit economics.

## Deployment

See `render.yaml` for full Render.com manifest (4 web services + 2 cron jobs)
and `.github/workflows/surveillance.yml` for GitHub Actions fallback cron.

Production checklist before going live:
- [ ] Register BLS API key at data.bls.gov/registrationEngine
- [ ] Create real Stripe Payment Links (replace placeholders in `customer_calculator.py`)
- [ ] Set `ANTHROPIC_API_KEY` in Render env (for AI Q&A)
- [ ] Set `STRIPE_SUBSCRIPTION_URL` and `STRIPE_PLACEMENT_URL` in Render env
- [ ] Replace nurse_access_codes.csv demo entries with real cohort codes
- [ ] Wire DNS: florence.com/calculator, florence.com/intel, nurses.florence.com
- [ ] Set up password manager / Auth0 / Clerk for nurse portal real auth
- [ ] Configure Render or GH Actions cron schedules
- [ ] Run security review: confirm no FICA/IRS leakage on any public surface

## Security & compliance

- **No PHI/PII** in this codebase — only public CMS + BLS data + lead emails
- **Lead emails** stored in `data/customer_leads.csv` (Florence-internal only)
- **Nurse passcodes** stored in `data/nurse_access_codes.csv`
- **Anthropic API key** read from env, never committed
- **Public surfaces** audited monthly for FICA/IRS leakage (see
  `customer_calculator.py` for current scrub state; verify before each deploy)

## Cron schedule

```
0 6 * * *      Daily 06:00 UTC    News feeds refresh
5 0 5 * *      5th of month       Full briefing refresh:
                                    - JOLTS, CES, OEWS, CMS Care Compare
                                    - Ownership diff + pricing alerts
                                    - 12-month forecast
                                    - Unified briefing markdown + JSON
```

## Surfaces × Ports (development)

| Surface | Port | File | Audience |
|---|---|---|---|
| Florence Workforce Economist | 8501 | `app.py` | Internal sales + ops |
| Customer Calculator | 8502 | `customer_calculator.py` | Public operators |
| Market Intelligence | 8503 | `public_market_intel.py` | Public, educational |
| Nurse Portal | 8504 | `nurse_portal.py` | Florence-placed RNs |

To run all four locally:
```bash
streamlit run app.py --server.port 8501 &
streamlit run customer_calculator.py --server.port 8502 &
streamlit run public_market_intel.py --server.port 8503 &
streamlit run nurse_portal.py --server.port 8504 &
```
