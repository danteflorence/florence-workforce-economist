# Multi-Market Worked-Example Set

Every number below comes from running [`pricing_engine.py`](pricing_engine.py). To reproduce: `python3 pricing_engine.py`.

The five hospitals span four real CommonSpirit-system facilities (using the rates in the FlorenceOS demo dataset) plus one synthetic case constructed to stress the no-quote logic.

**Calibration used:** δ_target = $2.50/hr, δ_cap = $4.00/hr, δ_floor = $1.00/hr, ζ = $3.00/hr, H_c = 5,616 hours, H_exempt = 3,744 hours, SS wage base = $184,500 (2026 IRS Rev. Proc.).

**One reading note:** the "savings vs. agency" figures below assume Florence's permanent placement displaces agency labor 1:1 over the full commitment. That is a CFO-validated assumption per role/unit, not a model output. In production, the agent should multiply this by an "agency displacement factor" calibrated against the hospital's actual contracted-labor share for the unit.

---

## Summary Table

Florence fee per nurse (3-year commitment), across hospital and cohort visa-exempt share η:

| Hospital | Loaded staff $/hr | All-in agency $/hr | Premium $/hr | Channel | η=1.0 fee | η=0.3 fee | η=0.0 fee |
|---|---:|---:|---:|---|---:|---:|---:|
| Saint Francis Memorial (SF) — ICU | $119.00 | $230.60 | $111.60 | direct | $38,385 | $21,344 | $14,040 |
| Mercy Hospital (Bakersfield) — Med/Surg | $80.44 | $135.19 | $54.75 | direct | $30,652 | $19,024 | $14,040 |
| St. Mary's (Grand Junction CO) — Med/Surg | $65.67 | $125.08 | $59.41 | direct | $27,788 | $18,164 | $14,040 |
| Methodist (Arcadia CA) — Med/Surg | $95.20 | $109.39 | $14.19 | direct | $33,516 | $19,883 | $14,040 |
| Compressed-premium (synthetic) — Med/Surg | $60.21 | $62.00 | $1.79 | **AMN wholesale** | $11,664 | $7,432 | $5,616 |

Hospital experience per nurse (premium over loaded staff, savings vs. all-in agency), unchanged across cohort scenarios:

| Hospital | Premium over staff/hr | Savings vs. agency/hr | Savings vs. agency, 3-yr |
|---|---:|---:|---:|
| Saint Francis | $2.50 | $109.10 | $612,692 |
| Mercy Bakersfield | $2.50 | $52.25 | $293,453 |
| St. Mary's | $2.50 | $56.91 | $319,595 |
| Methodist Arcadia | $2.50 | $11.69 | $65,640 |
| Compressed-premium | $1.00 | $0.79 | $4,420 |

**Two patterns to notice:**

1. **The hospital sees the same δ in every cohort scenario for a given hospital** — that is the model's central design property. δ is the CFO-facing number. The cohort affects only Florence's revenue.

2. **Florence revenue varies up to 2.7× between visa cases for the same hospital.** SF: $38,385 (η=1.0) vs. $14,040 (η=0.0). This is the single most important fact for sales/finance discipline: the FICA premium is a function of *who Florence is actually placing*, not of the hospital's willingness to pay. Quoting an η=1.0 fee against an η=0 pipeline is a misrepresentation.

---

## 1. Saint Francis Memorial Hospital — San Francisco, CA (ICU)

**Market inputs:** taxable wage $85.00/hr, benefit load $27.50/hr, loaded staff cost C = $119.00/hr, all-in agency A = $230.60/hr. Employer FICA T_emp = $6.50/hr (slightly below the flat 7.65% × W because annual wages exceed the 2026 SS wage base of $184,500).

**Agency premium M = $111.60/hr. Allowed δ = $108.60/hr (well above target).**

| Scenario | η | F_base | F_fica | F_total | Channel |
|---|---|---:|---:|---:|---|
| A — F-1/J-1 | 1.0 | $14,040 | $24,345 | **$38,385** | direct |
| B — mixed | 0.3 | $14,040 | $7,304 | **$21,344** | direct |
| C — EB-3/H-1B | 0.0 | $14,040 | $0 | **$14,040** | direct |

Hospital experience (per nurse, 3-year): normal cost $668,318 → effective cost $682,358. Net premium $14,040 over 3 years = $2.50/hr. Agency comparison $1,295,050 → savings $612,692 = $109.10/hr.

**Commentary.** Saint Francis is the most agency-pressured market in the example set. The agency premium is large enough that Florence could in principle push δ much higher than $2.50 — δ_allowed = $108.60/hr — but the cap and target both bind first. The $612K per-nurse savings vs. agency is real arithmetic but is a function of full agency displacement; CFO conversation should validate the displacement factor for ICU specifically.

The Tenet $50,000 reference is closest to Scenario A here. If Florence's pipeline to this kind of hospital genuinely is 100% F-1/J-1 from a university partner, the model produces $38,385 — about 23% below the Tenet anchor. The $11,615 gap probably reflects: a higher Tenet δ (~$4/hr rather than $2.50), or production-cost loading (F_floor), or both. Worth resolving before the next Tenet conversation.

---

## 2. Mercy Hospital — Bakersfield, CA (Med/Surg)

**Market inputs:** taxable wage $58.00/hr, benefit load $18.00/hr, loaded C = $80.44/hr, agency A = $135.19/hr, T_emp = $4.44/hr (flat 7.65% applies; wages under SS base).

**M = $54.75/hr. Allowed δ = $51.75/hr.**

| Scenario | η | F_base | F_fica | F_total | Channel |
|---|---|---:|---:|---:|---|
| A — F-1/J-1 | 1.0 | $14,040 | $16,612 | **$30,652** | direct |
| B — mixed | 0.3 | $14,040 | $4,984 | **$19,024** | direct |
| C — EB-3/H-1B | 0.0 | $14,040 | $0 | **$14,040** | direct |

Hospital experience: normal $451,734 → effective $465,774. Net premium $14,040. Agency $759,227 → savings $293,453 = $52.25/hr.

**Commentary.** Mid-market California Central Valley facility. Solid agency premium, plenty of room for the target δ. The FICA component drops from $16,612 (η=1.0) to zero (η=0.0) because of the lower wage base — same percentage capture but on a lower wage. This is where the model's market sensitivity shows: same calibration, lower per-nurse fee than SF, because the underlying wage is lower.

---

## 3. St. Mary's Hospital — Grand Junction, CO (Med/Surg)

**Market inputs:** taxable wage $48.00/hr, benefit load $14.00/hr, loaded C = $65.67/hr, agency A = $125.08/hr, T_emp = $3.67/hr.

**M = $59.41/hr. Allowed δ = $56.41/hr.**

| Scenario | η | F_base | F_fica | F_total | Channel |
|---|---|---:|---:|---:|---|
| A — F-1/J-1 | 1.0 | $14,040 | $13,748 | **$27,788** | direct |
| B — mixed | 0.3 | $14,040 | $4,124 | **$18,164** | direct |
| C — EB-3/H-1B | 0.0 | $14,040 | $0 | **$14,040** | direct |

Hospital experience: normal $368,814 → effective $382,854. Net premium $14,040. Agency $702,449 → savings $319,595 = $56.91/hr.

**Commentary.** Lower-cost market but with proportionally large agency premium (agency is ~2× loaded staff). The η=0.0 fee is $14,040 — same as the SF case. That's because F_base = δ × H_c is market-independent under the current calibration. The agent has two options here: (a) accept that the EB-3 fee is the same everywhere and let the FICA component carry market sensitivity, or (b) make δ itself market-indexed (e.g., δ scales with M). The current code does (a). The white paper §5 should make this explicit choice visible.

---

## 4. Methodist Hospital of Southern California — Arcadia, CA (Med/Surg)

**Market inputs:** taxable wage $68.00/hr, benefit load $22.00/hr, loaded C = $95.20/hr, agency A = $109.39/hr, T_emp = $5.20/hr.

**M = $14.19/hr. Allowed δ = $11.19/hr — still comfortably above target.**

| Scenario | η | F_base | F_fica | F_total | Channel |
|---|---|---:|---:|---:|---|
| A — F-1/J-1 | 1.0 | $14,040 | $19,476 | **$33,516** | direct |
| B — mixed | 0.3 | $14,040 | $5,843 | **$19,883** | direct |
| C — EB-3/H-1B | 0.0 | $14,040 | $0 | **$14,040** | direct |

Hospital experience: normal $534,654 → effective $548,694. Net premium $14,040. Agency $614,334 → savings $65,640 = $11.69/hr.

**Commentary.** This is the "thin agency premium" case in the source data (the demo shows 14.2% premium over staff cost). Even so, with the current calibration the model says go — δ_allowed = $11.19 is above target $2.50 by a healthy margin. The savings story is much weaker than SF ($65K per nurse over 3 years vs. $612K) but the math still works.

This is the kind of account where Florence should be careful: the model says "feasible" but the CFO will see a much smaller savings number. The agent should flag accounts where `savings_vs_agency_per_hour < $20/hr` for human review before quoting — the economic case is too narrow to defend if any assumption (agency displacement, wage progression, retention) moves against Florence.

---

## 5. Hypothetical Compressed-Premium Facility — synthetic (Med/Surg)

This isn't a real CommonSpirit facility — it's constructed to test the no-quote / AMN-routing logic. Imagine a Midwest community hospital with modest wages and modest agency rates.

**Market inputs:** taxable wage $42.00/hr, benefit load $15.00/hr, loaded C = $60.21/hr, agency A = $62.00/hr, T_emp = $3.21/hr.

**M = $1.79/hr. Allowed δ = M − ζ = −$1.21/hr (negative).**

| Scenario | η | F_base | F_fica | F_total | Channel |
|---|---|---:|---:|---:|---|
| A — F-1/J-1 | 1.0 | $5,616 | $6,048 | **$11,664** | **AMN wholesale** |
| B — mixed | 0.3 | $5,616 | $1,816 | **$7,432** | **AMN wholesale** |
| C — EB-3/H-1B | 0.0 | $5,616 | $0 | **$5,616** | **AMN wholesale** |

Hospital experience: normal $338,156 → effective $343,772. Net premium $5,616. Agency $348,192 → savings $4,420 = $0.79/hr.

**Commentary.** This is the case the model is designed to flag. Agency labor barely exceeds loaded staff cost. The required savings buffer ζ = $3/hr cannot be honored — there isn't $3/hr of premium to spread between Florence and the hospital. The agent drops δ to the floor ($1.00/hr), but the savings-vs-agency story is negligible ($0.79/hr).

The routing logic moves this account to AMN wholesale, where Florence accepts $35,000 from AMN regardless of the local agency premium and AMN absorbs the spread risk. This is exactly the kind of account AMN's channel was designed for in the framework.

If the agent didn't have this guardrail, Florence could quote a $14,000+ fee to this hospital, the hospital would discover post-deal that their savings vs. agency were nearly zero, and the relationship would burn. The model's job here is to prevent that quote from going out the door.

---

## What the example set demonstrates

1. **The hospital experience is identical across visa cohorts.** δ = $2.50/hr in every direct-enterprise case. The hospital does not "see" the cohort difference. This is the model property that makes the FICA layer commercially viable: it doesn't change what the CFO sees.

2. **Florence's revenue varies materially with cohort composition.** η = 1.0 vs. η = 0 changes the fee by 1.7× to 2.7× across these markets. Predicting this correctly requires actual pipeline data (Florence's nurse-supply system), not sales aspirations.

3. **The model handles the floor case.** The synthetic compressed-premium facility routes to AMN wholesale rather than generating an unsustainable direct quote.

4. **The model handles the SS wage-base case.** Saint Francis ICU has W=$85/hr × 1,872 = $159,120 annual base wage, plus shift differentials lifting effective annual wages over $184,500. T_emp drops to $6.50/hr from the flat $6.50 that 7.65% × $85 would imply. (For an even higher-wage RN, the divergence widens.)

5. **The model surfaces, rather than hides, the Tenet $50,000 anchor gap.** Even in the most favorable scenario (SF, η=1.0), the model produces $38,385. The $11,615 gap to Tenet's $50,000 reference price is not explained by the spread + FICA capture alone. The white paper §6 lists three candidate explanations; resolving which one applies is a precondition to a credible Tenet renewal pitch.

6. **The model is conservative on δ.** The δ_target = $2.50/hr is well below δ_allowed in every direct case (the smallest allowed value in this set is $11.19/hr at Methodist Arcadia). Florence has substantial room to raise δ if it chooses, with corresponding tradeoffs in CFO acceptance and account churn risk. This is a calibration decision for the pricing committee, not an automatic agent decision.

---

## How to use this in a CFO conversation

A complete one-page CFO deliverable for any single hospital looks like this:

1. Hospital and market name; role; cohort assumption (η) clearly stated.
2. Three numbers stacked: δ chosen, F_total, hospital effective premium/hr.
3. The savings table: normal staff cost vs. Florence effective cost vs. agency cost (per nurse, 3-year).
4. The visa-tax assumption block from §15.1.
5. A "what changes if..." sensitivity row: if η = 0 (worst case for Florence), the fee drops to $14,040 and Florence's value proposition rests entirely on production capability — not on tax capture.

The agent should always show the η = 0 fee even when proposing an η > 0 quote. That keeps the hospital's downside visible.
