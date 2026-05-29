# The State of the U.S. Nursing Workforce — 2026


*A Florence Workforce Intelligence Report — published 2026-05-29*



## Executive summary — 2026

The United States nursing workforce remains the structural constraint on
U.S. healthcare capacity. Across **52,545 Medicare-certified
facilities** spanning hospitals, ambulatory surgery centers, home health
agencies, skilled nursing facilities, hospices, and dialysis centers, total
addressable RN demand is approximately **641,576 full-time equivalents**.

**Healthcare labor market is TIGHT.** As of March 2026, healthcare has 700K job openings against 463K quits (ratio: 1.51). Operators are competing for talent — Florence positioning is strongest in tight markets.

12-month projection: openings/quits ratio 1.51 → 1.54. Florence pricing power expanding over the next year.

Florence's analysis identifies a **$21.6B 24-month placement opportunity**
against a corresponding **$43.6B in hospital cost-displacement savings**
from converting contingent agency labor to permanent international RN supply.

The labor market is tightening across every signal we monitor: job openings
exceed quits at a sustained 1.5:1 ratio in healthcare, wage growth is
accelerating in high-cost states, and operator margins remain pressured by
agency-labor premiums that recur every fiscal cycle.

This report compiles the evidence from publicly-sourced government datasets —
U.S. Bureau of Labor Statistics, the Centers for Medicare & Medicaid Services,
and the National Academy for State Health Policy — refreshed continuously in
the Florence Workforce Intelligence platform.



## Market structure

| Segment | Facilities | Florence-priceable |
|---|---:|---:|
| Hospitals (CMS Form 2552-10) | 5,432 | 4,741 |
| Ambulatory Surgery Centers | 5,612 | 5,612 |
| Home Health Agencies | 12,392 | 12,392 |
| Skilled Nursing Facilities | 14,700 | 14,700 |
| Hospices | 6,852 | 6,852 |
| Dialysis Centers | 7,557 | 7,557 |
| **Total** | **52,545** | **51,854** |

The non-hospital segment alone — surgery centers, home health, skilled nursing,
hospice, and dialysis — represents 9× the facility count of the acute-care
hospital segment. Home health agencies are the most fragmented (12,392 agencies
with no dominant operator); skilled nursing is the most consolidated (top 3
operators run 600+ facilities combined).



## Labor market signals (BLS JOLTS — Healthcare & Social Assistance, NAICS 62)

As of March 2026:

- **Job openings:** 700K — the unmet demand for healthcare workers
- **Voluntary separations (quits):** 463K — workers exercising mobility
- **Openings:quits ratio:** 1.51

A ratio above 1.3 indicates a tight labor market with sustained upward
pressure on wages and agency-labor costs. The current healthcare ratio of
1.51 reflects a structurally constrained labor pool — every quit must
be backfilled, and the unfilled openings represent revenue that operators
cannot capture without expanding their workforce.

The 12-month BLS forecast (based on SARIMA model fit to historical JOLTS data)
projects continued tightening through 2027, with the
openings:quits ratio expanding modestly as the long-cycle demographic demand
(aging baby boomers entering peak healthcare-consumption years) continues to
outpace the supply of domestically-trained RNs.



## Wage geography (BLS OEWS, May 2024 release)

Prevailing RN wages vary 1.9× across U.S. states.

**Highest-wage states:**
| state | rn_wage |
| --- | --- |
| CA | $65.95 |
| HI | $60.45 |
| AK | $55.10 |
| OR | $53.85 |
| MA | $53.20 |

**Lowest-wage states:**
| state | rn_wage |
| --- | --- |
| SD | $34.70 |
| MS | $35.45 |
| TN | $35.80 |
| KS | $36.40 |
| AL | $36.80 |

The variation reflects three structural factors: cost of living (California,
Hawaii, Oregon, Washington); state-level nursing-staffing ratio regulation
(California, Massachusetts); and union density (Northeast and West Coast).
Lower-wage states (Alabama, Mississippi, Arkansas, South Dakota) reflect
rural labor markets with limited union penetration and lower cost-of-living
adjustments.

For employers, this variation means a single national hiring strategy will
fail. Local-market understanding — which Florence's platform delivers via
HCRIS-derived per-facility data, BLS state-level wage data, and CMS Care
Compare quality signals — is essential to competitive workforce planning.



## Florence's role in the workforce

Florence operates the only end-to-end international RN production pipeline
in the United States:

1. **Exam preparation** — international RN candidates pass NCLEX-RN
2. **Higher education** — F-1 program preparing for U.S. clinical practice
3. **Bedside practice** — onboarding into U.S. healthcare operators
4. **Permanent placement** — full-time employment, not contingent supply

Florence's flat $50,000 per-RN placement fee, amortized over a 36-month
minimum contract term, converts an operator's contingent agency-labor line
item into permanent capacity. The fee is payable on successful employment
start with replacement protection for early attrition.

Florence Workforce Intelligence — the platform behind this report — refreshes
all underlying data monthly from public BLS and CMS sources, ensuring
operators, investors, and policymakers can rely on the most current view of
the U.S. nursing labor market.



## Methodology & sources

### Data sources
- **U.S. Bureau of Labor Statistics, JOLTS** — monthly job openings, hires,
  separations for Healthcare & Social Assistance (NAICS 62)
- **U.S. Bureau of Labor Statistics, CES** — monthly employment in hospitals,
  ambulatory care, nursing & residential care
- **U.S. Bureau of Labor Statistics, OEWS** — annual May release, Registered
  Nurses (SOC 29-1141), state and MSA levels
- **CMS Hospital Cost Report Information System (HCRIS)** — Worksheet S-3
  Part II line 01100 (direct patient care contract labor hourly rate),
  Worksheet S-3 Part V (RN staffing)
- **CMS Provider of Services and Provider Enrollment, Chain and Ownership
  System (PECOS)** — facility-level ownership and chain affiliation
- **CMS Provider Data Catalog** — Care Compare quality measures, staffing
  hours, star ratings (quarterly)
- **National Academy for State Health Policy (NASHP), Hospital Cost Tool** —
  2011-2024 hospital financial data including system affiliation

### Refresh cadence
- Monthly: JOLTS, CES, briefing, ownership/pricing snapshots
- Quarterly: CMS Care Compare, CMS HCRIS rolling
- Annually: BLS OEWS (May), NASHP HCT (December)

### Forecasting methodology
Twelve-month SARIMA models (1,1,1)(1,1,0,12) fit on JOLTS healthcare series
with 80% confidence intervals. Forecasts refreshed monthly with new JOLTS
release.

### Reproducibility
All numbers in this report are reproducible from public datasets via the
Florence Workforce Intelligence open codebase. Data refresh + report
generation runs on a monthly cron schedule.

---

**Disclaimer.** This report is informational and based on public data sources.
Florence does not warrant specific outcomes for any employer, nurse, or
investment decision. Engage your own legal, tax, and operational counsel before
contracting any workforce program.

*Florence Workforce Intelligence — 2026 edition. Generated
2026-05-29.*
