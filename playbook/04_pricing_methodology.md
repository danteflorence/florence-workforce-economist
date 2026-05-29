# How our pricing works

> _The customer doesn't need to see this in this much depth. You do. If
> a CFO challenges a number on your proposal, you need to defend it in
> 30 seconds without flipping through anything._

## The principle

**Florence's pricing engine produces a locally-calibrated quote per
facility — and the engine ships in two distinct modes, one for each
care setting:**

| Care setting | Pricing model | Customer commercial structure |
|---|---|---|
| **Inpatient — hospitals** | `FLAT_PLACEMENT_FEE` at $50K/RN | One-time fee, amortized over 36 months ≈ $1,389/RN/mo |
| **Outpatient — ASC, HHA, SNF, hospice, dialysis** | `FICA_OFFSET_TARGET` at 40% | **Monthly credit-card subscription**, 1-month deposit at signing, 24-month term |

**Why two models?** Hospital CFOs are buying capacity displacement on a
multi-million-dollar nursing labor line — the placement fee is the way
that procurement department thinks. Outpatient operators (a 12-OR
surgery center, a 60-bed SNF) buy on an opex line item, and $50K
upfront is a board decision they don't want to make. The monthly
subscription on a credit card is the way THAT buyer thinks.

The engine is **not** a national average dressed up as a quote. Every
number on a proposal traces back to a specific data point at that
facility — its MSA, its cost report, its system-level overlay if one
exists.

---

## The five inputs per facility

1. **MSA prevailing wage (BLS OEWS)** — mean hourly RN wage for the
   facility's MSA. Updated annually when BLS publishes (May).

2. **Agency rate (HCRIS NMRC + Worksheet S-3 Part V)** — what the
   facility actually paid for contract labor in their most recent cost
   report. NMRC line 01700 (total CL cost) ÷ contract labor hours from
   S-3 Part V. If confidence is low, we fall back to a standard rate
   and flag the row for manual review.

3. **RN need (HCRIS S-3 Part I)** — worked hours for nursing service,
   facility-reported.

4. **System overlay (NASHP + manual research)** — for systems where the
   facility-level signal is unreliable (e.g. Kaiser's $622M AMN
   relationship), we apply an organization-level adjustment. Documented
   per system in `data/system_overlays.csv`.

5. **Florence cost basis** — our placement cost per nurse, internally
   maintained. Drives the floor.

---

## How those become a quote

**FLAT_PLACEMENT_FEE mode — INPATIENT default, customer-facing:**

```
Placement fee per RN  =  $50,000  (configurable per system)
Monthly amortization  =  $50,000 / 36 months ≈ $1,389 / RN / month
Annual fee per RN     =  $50,000 / 3 years ≈ $16,667 / RN / year
Annual savings per RN =  (agency_premium × hours_per_year)
                         − ($50,000 / 3)
```

This is what a hospital CFO sees on the proposal. The lead message is
**savings**, the structure is a placement fee amortized over 36 months.

**FICA_OFFSET_TARGET mode — OUTPATIENT default, customer-facing:**

```
Target offset         =  40% of FICA-exempt payroll savings funds the fee
Monthly fee per RN    =  monthly_FICA_savings / target_offset_pct
                         (clamped to $750-$2,000 / RN / month)

Month 1  at signing   =  deposit (1 month) + first month's subscription
Months 2-23           =  monthly subscription auto-charged to credit card
Month 24              =  $0 (deposit applied to final month)
24-month total        =  24 × monthly subscription
```

This is what an outpatient operator sees on the proposal. The lead
message is **monthly subscription on credit card**, the structure is a
24-month service term with a one-month deposit.

**Important — what the customer hears in BOTH cases:**

We do not say the word "FICA" to either buyer. Inpatient customers
hear "savings on agency." Outpatient customers hear "monthly subscription."
The FICA mechanic is how WE size the fee — never how we explain it to
the buyer.

---

## Why we're confident in the number

**Provenance is built in.** The internal app has a "Data provenance"
tab that traces every number on every proposal back to its source row
in the source file. If a CFO asks "where did this come from?" you can
show them.

**Manual-review flag for low-confidence rows.** Some HCRIS cost reports
are missing fields, mis-coded, or implausibly extreme. We flag those
and either fall back to a defensible standard or refuse to quote until
we re-research. This is why occasionally a recommended proposal is
gated.

**Snapshot history.** Every proposal generated is saved as a
point-in-time snapshot. Six months later, if the customer comes back
and says "your numbers changed" — yes, the underlying data changed.
The snapshot proves what we promised on what date.

**3-tier pricing bands.** The recommendation engine produces three
prices per facility:
- **Stretch** — what the math supports if the customer is sophisticated
  and the data confidence is high.
- **Target** — the price we recommend leading with.
- **Reference** — the floor we will not go below without internal
  approval.

---

## When the number is wrong

The pricing engine is calibrated, not psychic. Three situations require
human judgment:

1. **Manual-review flag is on.** The HCRIS data was unreliable. Don't
   quote until the account manager reviews.

2. **System overlay exists.** The facility-level number is right but
   the system has organization-level dynamics (a captive staffing
   subsidiary, a sole-source contract) that change the picture. The
   overlay is documented and applied automatically; just don't be
   surprised by the result.

3. **The customer pushes back hard.** They know something we don't.
   Listen. Then come back to the playbook objections chapter for the
   defensible response.

---

## What the engine does NOT do

- It does not include immigration or visa fees in the quote unless the
  $5K immigration transition add-on is toggled on.
- It does not include nurse housing assistance, sign-on bonuses, or
  retention payments. Those are operator-side costs.
- It does not assume the customer's HR system, payroll provider, or
  scheduling stack. We quote nursing capacity, not integration.
- It does not predict contract length. The economics work at 12 months
  and improve at 24 and 36.

---

## How to defend a number on the call

If a CFO challenges any specific dollar on the proposal:

1. **Open the Data provenance tab.** Find the facility. Show them the
   source row.
2. **Cite the source explicitly.** "That comes from your fiscal 2023
   HCRIS Worksheet S-3 Part V, line 01700."
3. **Acknowledge the lag.** "This is FY23 data. Cost reports lag by 12
   to 18 months. We can re-run if you have current internals you'd
   share — we'd actually love to."
4. **Offer the data-share path.** This is how the conversation upgrades
   to a partnership. They share internals; we run a custom proposal
   with their actuals.

The best objection response is an invitation to share their data.
