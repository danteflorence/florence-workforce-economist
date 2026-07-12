# White Paper Revisions — Florence Labor Economics Agent

These sections replace the corresponding sections of the original draft. The substantive change is that the model now treats FICA capture as a **conditional, cohort-weighted, time-bounded** input — not a universal feature of every Florence placement. This aligns the white paper with what is already implemented in `care-capacity-index/src/lib/ficaAdvantage.ts`, which is the right design.

---

## §1. Executive Summary (revised)

The U.S. nursing shortage is a supply, pricing, and labor-conversion problem. Hospitals buy nursing labor through fragmented channels — internal recruiting, full-time employment, per diem, travel, MSPs, direct hire, staffing agencies, and international recruitment — each with a different cost structure. Most workforce decisions still rely on static benchmarks: placement fee, hourly bill rate, vacancy count, wage scale, or annual agency spend.

The Florence Labor Economics Agent creates a new pricing and intelligence layer for this market. It continuously monitors local RN supply, wage rates, agency premiums, hospital economics, and Florence nurse availability, then converts that data into dynamic pricing for permanent nurse capacity.

The central pricing premise is:

> Florence should not charge every hospital the same fixed fee. Florence should price permanent nurse production against each hospital's local labor economics **and the visa/tax profile of the nurses Florence is actually placing into that hospital**.

The fee is built from two independent components:

```
Florence Fee per Nurse =
    Base Conversion Fee                              (always)
  + Eligible FICA Capture × eligibility_weight       (conditional)
```

The **Base Conversion Fee** is what Florence charges for producing, preparing, supporting, and guaranteeing a permanent full-time RN. It is priced against the hospital's loaded staff cost, the all-in agency rate, and a target net hourly premium δ — and is **bounded by an agency-savings guardrail** so the hospital's effective per-hour cost never exceeds all-in agency labor minus a savings buffer ζ.

The **Eligible FICA Capture** is the employer-side payroll-tax savings the hospital realizes when a nurse is FICA-exempt under IRC §3121(b)(19). This applies only to F-1, J-1, M-1, Q-1, or Q-2 nonresident aliens performing services consistent with their visa status, and only while the individual remains a nonresident alien for tax purposes (typically the first two calendar years of J-1 status, or roughly the first five years of F-1 status under the substantial-presence test).

**Florence's likely permanent-placement pipeline runs primarily on EB-3 immigrant visas and H-1B.** EB-3 nurses are lawful permanent residents from day one and pay full FICA. H-1B nurses pay full FICA. For both populations, the FICA capture component is zero.

The model handles both cases:

- For FICA-exempt cohorts (F-1 OPT/CPT, J-1 exchange visitors, etc.), Florence can quote a higher headline fee and the hospital still nets a savings because the hospital captures employer-side FICA savings during the exempt window.
- For non-exempt cohorts (EB-3, H-1B, TN, U.S. domestic), Florence quotes the Base Conversion Fee with no FICA discount layered in. The pricing is then driven entirely by the agency-cost spread.

Both cases are bounded by the same guardrail: the hospital's effective per-hour cost must remain below all-in agency labor by at least ζ.

The agent generates three outputs:

1. A dynamic Florence fee by hospital, role, geography, specialty, and visa cohort mix.
2. A CFO-ready evidence pack showing effective hourly cost versus agency labor, with the FICA component disclosed separately and an explicit caveat that FICA treatment requires hospital tax/payroll/legal review.
3. A national opportunity map ranking hospitals by agency premium, open RN demand, wage environment, Florence supply fit, and channel access.

The strategic point is unchanged: Florence is not selling recruiting hours. Florence is pricing the conversion of premium contract labor into permanent staff capacity. The agent makes that pricing market-sensitive instead of static.

---

## §5. Mathematical Model (revised)

### 5.1 Notation

For each pricing instance:

```
h = hospital
m = local labor market (MSA)
r = role / specialty
s = shift pattern
t = pricing date
```

Variables:

```
W(h,r,s,t)  = taxable hourly RN wage
B(h,r,s,t)  = non-FICA benefit and labor load per hour
T_emp(W,t)  = employer payroll tax per hour for a normally-taxed RN
              = (6.2% × min(annual_wages, SS_wage_base) + 1.45% × annual_wages) / annual_hours
C(h,r,s,t)  = ordinary all-in loaded staff cost per hour
              = W + B + T_emp
A(h,r,s,t)  = all-in agency cost per hour (includes MSP/VMS fee allocation)
H_c         = commitment hours (e.g., 5,616 for 3 years × 1,872 hrs/yr)
H_exempt    = FICA-exempt hours within commitment, per nurse
              (typically 1,872 to 3,744 — i.e., 1–2 years — for eligible F-1/J-1)
η(h)        = FICA-eligible share of Florence's placed cohort at h
              (0.0 to 1.0; equals 0 for pure EB-3/H-1B/TN/domestic pipelines)
δ           = target net hourly premium to hospital over loaded staff cost
ζ           = required hourly savings buffer versus all-in agency
F_base      = base conversion fee per nurse
F_fica      = expected FICA capture per nurse (cohort-weighted)
F           = Florence total fee per nurse
```

### 5.2 The base conversion fee

The base fee is the hourly premium δ amortized over the commitment:

```
F_base = H_c × δ
```

This is what Florence charges for producing a permanent RN regardless of visa status. It is the only component that applies to **every** placement.

### 5.3 The FICA capture component

For each FICA-eligible placement during the eligible window:

```
T_emp_per_hour(h) = (0.062 × min(W × H_yr, SS_base) + 0.0145 × W × H_yr) / H_yr
```

For W ≤ SS_base / H_yr (the common case in U.S. RN wages), this simplifies to a flat 7.65% × W. At California ICU wages and above, the SS wage-base cap reduces the effective rate.

The expected FICA capture per nurse, cohort-weighted, is:

```
F_fica = η(h) × T_emp_per_hour × H_exempt
```

Three things matter here:

1. **η(h)** is the fraction of the cohort Florence will actually place at hospital h that qualifies for the exemption. For an account where Florence's pipeline is 100% EB-3, η = 0. For a hospital partnering with a U.S. university (Touro, Webster) that produces F-1/J-1 nurses, η can approach 1.0 for that subset of placements.
2. **H_exempt < H_c.** The exemption ends when the individual becomes a resident alien for tax purposes. Modeling the full commitment as exempt overstates the capture by 30–60%.
3. **Florence does not directly receive the FICA savings.** The hospital receives them as payroll-tax reduction. Florence captures them only via a higher headline fee that the hospital accepts because it nets out against those savings.

### 5.4 Total fee and hospital effective cost

```
F = F_base + F_fica
  = H_c × δ + η × T_emp × H_exempt
```

The hospital's effective labor cost per nurse over the commitment:

```
Effective hospital cost = C × H_c                      (what it would pay for a normal staff RN)
                       + F                              (what it pays Florence)
                       - η × T_emp × H_exempt           (FICA it doesn't pay because nurse is exempt)
                       = C × H_c + H_c × δ
                       = (C + δ) × H_c
```

The FICA terms cancel exactly when η, T_emp, and H_exempt match between Florence's fee and the hospital's actual tax savings. **This is the clean result, but it depends on the FICA assumptions being accurate.** If the hospital's actual FICA savings come in lower than F_fica priced (because, say, the nurse becomes a resident alien earlier than expected), the hospital experiences a per-hour premium higher than δ.

For this reason, the model presents the fee in two visa scenarios:

**Scenario A — FICA-exempt placement (η = 1, H_exempt = 2 × 1,872 = 3,744):**

```
F   = H_c × δ + T_emp × H_exempt
    = 5,616 × δ + T_emp × 3,744
Effective per-hour premium to hospital = δ  (if FICA captured as projected)
                                       = δ + risk-adjusted shortfall otherwise
```

**Scenario B — Non-exempt placement (η = 0):**

```
F   = H_c × δ
Effective per-hour premium to hospital = (F / H_c) = δ
```

In Scenario B, the entire fee is the spread δ. There is no FICA story. The CFO comparison is purely Florence's effective per-hour rate against agency labor.

### 5.5 Guardrails

Define agency premium:

```
M = A - C
```

Maximum hospital-allowed spread:

```
δ_allowed = M - ζ = (A - C) - ζ
```

Florence's price ladder by spread target:

```
δ = clamp(δ_target, δ_floor, min(δ_cap, δ_allowed))
```

If δ_allowed < δ_floor (meaning the agency premium minus required savings buffer is less than Florence's minimum viable spread), the account does not qualify for direct Florence enterprise pricing. The agent routes to one of:

- AMN wholesale (Florence prices at $35,000 wholesale; AMN absorbs the spread risk)
- Reduced-scope package (university referral, screening only, no relocation)
- Strategic pilot pricing (subsidized; tracked separately)
- No quote

The agent must also check Florence's production-cost floor:

```
F ≥ F_floor(r, m, h)
```

where `F_floor` reflects Florence's cost to source, screen, prepare (Academy), license, support visa workflow, relocate, and reserve replacement capacity for the given role, market, and hospital complexity. F_floor is a calibration parameter, not a market input; it should be set from internal cost accounting and updated quarterly.

### 5.6 Calibration constants — current proposed values

These are starting points, not derived from data. They are explicitly labeled as calibration parameters to be tuned against pilot results in Phase 5 (closed-loop learning).

```
δ_target  = $2.50 / hour     (CFO-acceptable hourly premium over loaded staff)
δ_cap     = $4.00 / hour     (maximum spread regardless of market)
δ_floor   = $1.00 / hour     (minimum spread to cover production cost in low-cost markets)
ζ         = $3.00 / hour     (required hospital savings buffer vs. agency)
F_floor   = market-specific  (see §10 production-cost model)
H_yr      = 1,872            (36 hrs/wk × 52 wks — RN three-twelves schedule)
H_c       = 5,616            (3-year commitment standard)
H_exempt  = 3,744            (2 years assumed exempt window for F-1/J-1 cohort;
                              tune per university partner profile)
SS_base   = current IRS Rev. Proc. value (2025: $176,100; 2026: $184,500)
```

The annual-hours convention is **1,872 hours/year throughout** — i.e., the nursing 36-hour schedule. The original draft was inconsistent (mixing 2,080 and 1,872); this convention should be applied uniformly, and BLS-reported annual figures should be divided by 2,080 to recover hourly wage, then re-multiplied by 1,872 only when computing FICA on actual hours worked.

---

## §6. Worked Example — Three Visa Scenarios (revised)

This worked example uses the same hospital profile across three different cohort assumptions to show how visa status changes the pricing result. The hospital is roughly modeled on a Northern California Dignity/CommonSpirit facility from the demo dataset (e.g., Mercy General Sacramento, where staff rate ≈ $90/hr and agency rate ≈ $154/hr).

**Hospital inputs (all three scenarios):**

```
W       = $90.00 / hour taxable RN wage
B       = $22.00 / hour benefit and labor load (excl. employer FICA)
T_emp   = $6.89 / hour       (7.65% × $90; both wages and SS base satisfied)
C       = $118.89 / hour     loaded staff cost
A       = $135.00 / hour     all-in agency cost (incl. MSP allocation)
H_c     = 5,616 hours        (3-year commitment)
H_exempt= 3,744 hours        (2-year exempt window)
δ_target= $2.50 / hour
ζ       = $3.00 / hour
M       = $16.11 / hour      agency premium
δ_allowed = $13.11 / hour    M − ζ
δ       = $2.50              clamp(target, floor, min(cap, allowed))
```

### Scenario A — 100% F-1/J-1 cohort (η = 1.0)

This is the upper bound of the model. Applies only when Florence's placements at this hospital come exclusively from a U.S.-based F-1/J-1 university pipeline within their nonresident-alien window.

```
F_base   = 5,616 × $2.50 = $14,040
F_fica   = 1.0 × $6.89 × 3,744 = $25,796
F        = $39,836 per nurse
```

Hospital effective cost over 3 years per nurse:

```
Normal staff:     $118.89 × 5,616 = $667,668
With Florence:    $667,668 + $39,836 (fee) − $25,796 (FICA saved) = $681,708
Net premium:      $681,708 − $667,668 = $14,040 = δ × H_c  ✓
Vs. agency:       $135 × 5,616 = $758,160
Savings vs agency:$758,160 − $681,708 = $76,452 = ($13.61/hr × 5,616)  ✓
```

The CFO sees: $2.50/hr premium over staff, $13.61/hr below agency, Florence captures $39,836.

### Scenario B — Mixed cohort (η = 0.3)

This is more realistic for Florence's likely operating mix — a hospital receiving a blend of university-pipeline F-1/J-1 (30%) and EB-3/H-1B (70%).

```
F_base   = 5,616 × $2.50 = $14,040
F_fica   = 0.3 × $6.89 × 3,744 = $7,739
F        = $21,779 per nurse
```

Hospital effective cost over 3 years per nurse:

```
Normal staff:     $667,668
With Florence:    $667,668 + $21,779 − $7,739 = $681,708
Net premium:      $14,040 = δ × H_c  ✓  (same as Scenario A — the math is invariant if FICA is captured as projected)
Savings vs agency:$76,452 (same per-hour)
```

Note: the hospital's experience is the same δ × H_c premium in Scenario B as in Scenario A — that's by design. The difference is **Florence's revenue**: $21,779 vs. $39,836. Florence earns less in mixed cohorts because there's less FICA to capture.

### Scenario C — 100% EB-3 / H-1B / TN / domestic (η = 0)

This is Florence's likely **majority pricing case** for permanent placements where the candidate already holds permanent or H-1B status.

```
F_base   = 5,616 × $2.50 = $14,040
F_fica   = 0
F        = $14,040 per nurse
```

Hospital effective cost over 3 years per nurse:

```
Normal staff:     $667,668
With Florence:    $667,668 + $14,040 = $681,708
Net premium:      $14,040
Savings vs agency: $76,452
```

The hospital's experience is unchanged. Florence's revenue is the base spread only. This is the floor of the model. **At δ = $2.50, F = $14,040 per nurse is well below the $50,000 Tenet reference and the $35,000 AMN wholesale reference.** That tells us either:

1. The Tenet $50,000 reference price implicitly includes a FICA component (it is priced for university-pipeline nurses, η ≈ 1) — in which case the model should reproduce that fee for that cohort and explicitly disclose the assumption.
2. Or the Tenet $50,000 reflects a larger δ — e.g., δ ≈ $8.90/hr — meaning Tenet has effectively been overpaying relative to the agency-savings model, or the Northern California agency premium is large enough to support it (A ≈ $145/hr against C ≈ $130/hr loaded gives a $15/hr agency premium and δ = $8.90 still leaves a $6.10/hr buffer, just inside ζ).
3. Or Florence's production cost in 2025 is high enough that the F_floor lifts the per-nurse fee above the spread-only result, and the model should make that visible.

The white paper should not paper over this — **the Tenet $50,000 anchor and the EB-3-only spread model are not consistent under δ = $2.50, and the model needs to surface that gap rather than hide it.**

### Reading the three scenarios together

| Scenario | η   | F_base   | F_fica  | F        | Hospital premium/hr | Hospital savings vs agency |
|----------|-----|----------|---------|----------|---------------------|----------------------------|
| A        | 1.0 | $14,040  | $25,796 | $39,836  | $2.50               | $13.61                     |
| B        | 0.3 | $14,040  | $7,739  | $21,779  | $2.50               | $13.61                     |
| C        | 0.0 | $14,040  | $0      | $14,040  | $2.50               | $13.61                     |

The hospital experience is identical across all three. **Florence's revenue varies by a factor of 2.8x depending on cohort composition.** This is the single most important fact the white paper must communicate: the FICA-driven price elevation is a function of *who Florence is placing*, not of Florence's pricing power or the hospital's willingness to pay.

---

## §15. Governance and Compliance (revised — additions)

The original §15 covers data governance and audit. Two additions are needed.

### 15.1 Visa and tax disclosure in every quote

Every CFO evidence pack must include a "Tax assumption" section with the following structure:

```
TAX ASSUMPTION

This quote assumes [X]% of placements will be FICA-exempt under IRC §3121(b)(19)
for an average exempt window of [Y] hours per nurse. Eligible cohorts: F-1, J-1,
M-1, Q-1, Q-2 nonresident aliens performing services consistent with visa status
during their nonresident-alien tax period.

If the actual cohort delivered to [Hospital] consists primarily of EB-3 immigrant
visa holders, H-1B holders, TN holders, or U.S. permanent residents/citizens, the
employer-side FICA savings will be lower than projected and the hospital's effective
per-hour premium over loaded staff cost may rise from $[δ_target]/hr to up to
$[δ_target + risk]/hr.

Florence does not provide tax, payroll, immigration, or legal advice. The hospital's
tax, payroll, immigration, and legal teams must independently confirm visa status,
work authorization, tax residency, payroll treatment, and applicability of the
exemption to each individual nurse before relying on the projected FICA component
of this pricing.

References: IRC §3121(b)(19); IRS Publication 519; IRS Publication 15 (Circular E).
```

This is not an optional footnote. It must be **on the same page** as the headline fee, and the FICA-dependent and FICA-independent fees must both be shown.

### 15.2 Pipeline composition reporting

The agent's quote-generation logic must call the nurse-supply data layer (Florence's matching/placement system) to determine the actual visa-cohort composition of nurses currently available, in-progress, or projected to be placed at the target hospital. The cohort weight η used in the quote must trace to the actual data, not to a sales target.

A quote that assumes η = 1.0 ("all F-1 students") when Florence's pipeline for that hospital's specialty/market is 90% EB-3 is, in effect, a misrepresentation. The agent should refuse to generate a high-η quote when the supply data does not support it, and should log the override if a human pricing approver chooses to issue one anyway.

### 15.3 Calibration audit trail

The four calibration constants (δ_target, δ_cap, δ_floor, ζ) and the production-cost floor F_floor materially determine Florence's revenue per placement. Changes to these values must be:

- Versioned (each pricing run records the version of constants used)
- Approved by a pricing committee (not changed unilaterally by sales)
- Tracked against realized outcomes (offer acceptance rate, replacement events, hospital churn)

This protects the agent from "tuning to win the next deal" — a failure mode that would erode the model's economic discipline over time.

---

## Summary of what changed vs. the original draft

| Issue from review | Resolution |
|---|---|
| FICA model assumed full 3-year exemption for all placements | Introduced `η` (cohort eligibility share) and `H_exempt` (exempt window in hours), separating commitment from exemption |
| Worked example showed only the favorable visa case | §6 now shows three scenarios (η = 1.0, 0.3, 0.0) with the same hospital inputs |
| EB-3/H-1B case (likely majority) was undisclosed | §6 Scenario C makes this explicit; revenue drops to $14,040 at δ = $2.50 |
| Inconsistent annual hours (1,872 vs 2,080) | §5.6 establishes 1,872 as the canonical convention with explicit BLS conversion |
| Calibration constants asserted without justification | §5.6 labels them as calibration parameters; §15.3 adds approval / audit process |
| Tax disclaimer buried in §15 | §15.1 requires it on the quote page itself, with cohort-specific numerics |
| Sales could quote favorable η without supply backing | §15.2 ties η to actual pipeline data; refusal logic for unsupported overrides |
| Gap between Tenet $50K anchor and EB-3 spread-only model not addressed | §6 Scenario C surfaces this gap rather than hiding it; three candidate explanations offered for resolution |
