# Glossary

> _Every term used in the internal tool, in the proposal, or by the
> customer. Alphabetical. Plain English first; technical detail second._

---

**Agency premium**
The gap between what a hospital pays a staffing agency for an RN hour
and what a permanent RN at that hospital costs per hour, fully loaded.
This is the savings Florence sells. Computed from HCRIS cost reports
(contract-labor cost ÷ hours) minus BLS OEWS prevailing wage for the
MSA.

**Agency rate**
The all-in hourly rate a hospital pays an agency. Includes the nurse's
wage, the agency's margin, and any add-ons. Often quoted as $150–$200/hr.

**Amortization (placement fee)**
The placement fee is paid over 36 months rather than upfront, smoothing
the operator's cash impact. $50K ÷ 36 ≈ $1,389/month per nurse.

**BLS — Bureau of Labor Statistics**
The federal agency that publishes JOLTS, CES, OEWS, and other labor
data. Florence's pricing engine consumes the public API.

**CES — Current Employment Statistics**
BLS monthly employment + earnings data by industry. We use the
healthcare sub-series.

**Census region**
Northeast / Midwest / South / West. Used in territory definitions and
lookalike scoring.

**Contract labor (CL)**
Anything that isn't a permanent FTE — agency, traveler, locum, per-diem.
CL intensity = CL hours ÷ total nursing hours. Higher = more pain =
better Florence fit.

**Cohort**
A group of Florence-placed RNs who were credentialed and arrive
together. Cohorts are the unit of community and the unit of operational
delivery.

**CCN — CMS Certification Number**
The 6-digit ID CMS uses for every certified provider. Our facility key.

**CMS Care Compare**
Public CMS data on hospital quality, ratings, and outcomes. Used in
surveillance for news and reputation signals.

**CMS Worksheet S-3 Part V**
The cost-report section where hospitals report contract-labor cost and
hours by line. The most important per-facility data we use.

**CRNA**
Certified Registered Nurse Anesthetist. The top of the RN salary curve.

**Deal score / Florence-fit score**
0–100 composite of facility size, agency premium, CL intensity, deal
score, and data confidence. Internal prioritization signal. Don't show
this to the customer.

**F-1 visa**
Student visa. The pathway most Florence-placed RNs use during their
credentialing-to-employment transition. Holders are non-resident aliens
for tax purposes. **Do not discuss with customers; internal only.**

**FICA**
The 7.65% employer + 7.65% employee payroll tax on US wages. F-1
non-resident-alien wages are FICA-exempt for the first 5 years under
IRC §3121(b)(19). This exemption underlies our `FICA_OFFSET_TARGET`
pricing mode. **Do not discuss with customers; internal only.**

**FLAT_PLACEMENT_FEE**
The default pricing mode. Customer pays $50K per nurse, amortized over
36 months. Customer-facing.

**FICA_OFFSET_TARGET**
The internal-analysis pricing mode. Targets a 40% offset of the
FICA-exempt savings to fund the fee. Used internally for sensitivity
analysis; not customer-facing.

**HCRIS — Healthcare Cost Report Information System**
CMS's public cost-report data, published annually. The source of our
facility-level contract-labor and RN-hours data.

**HHA — Home Health Agency**
A category in our facility taxonomy. We place RNs into HHAs.

**JOLTS — Job Openings and Labor Turnover Survey**
BLS monthly data on openings, hires, quits, layoffs. We use the
healthcare sub-series for surveillance.

**Manual-review flag**
Engine-set flag on rows where the data confidence is too low to quote
without human review. Honor it — don't override without checking.

**MSA — Metropolitan Statistical Area**
The Census geography we use for wage and demand calibration. There are
~390 MSAs. Mapped from ZIP via the BLS/Census crosswalk.

**MSP — Managed Service Provider**
A vendor model where one company manages all the staffing vendors at a
hospital, taking a margin on each. Some health systems use an MSP that
adds to the agency premium. Reflected in our system overlays.

**NASHP — National Academy for State Health Policy**
Publisher of the Hospital Cost Tool, which gives us ownership and
financial data we merge into the universe.

**NCLEX-RN**
The US RN licensing exam. Every Florence-placed nurse has passed it
before placement.

**NMRC**
The HCRIS sub-table that contains line-item cost data. Line 01700 is
total contract labor cost; line 01100 is direct patient care.

**OEWS — Occupational Employment and Wage Statistics**
BLS annual data on wages by occupation and geography. Source of our
prevailing-wage benchmark.

**OPT — Optional Practical Training**
The post-graduation work authorization on F-1 visa. Common bridge
between credentialing and employer-sponsored visa.

**PECOS**
CMS's provider enrollment data. Used for ownership signals across
non-hospital facilities.

**Placement fee**
The lump sum a hospital pays Florence per nurse placed. Default $50K.
Amortized over 36 months.

**Prevailing wage**
The mean hourly wage for the occupation in the MSA, per BLS OEWS. The
floor for what we pay our nurses.

**RN need**
Worked hours of nursing service at a facility, from HCRIS S-3 Part I.
Converted to FTE-equivalents in the proposal.

**Recommendation engine**
The internal module that computes per-facility recommended pricing with
3-tier bands (stretch / target / reference).

**SARIMA**
The statistical model we use to forecast JOLTS healthcare openings 12
to 24 months forward. Seasonal Autoregressive Integrated Moving
Average. Don't mention to customers.

**Snapshot**
A point-in-time saved version of a facility's pricing. Used to defend
quotes when underlying data changes later.

**Stretch / Target / Reference**
The 3-tier pricing bands the recommendation engine produces. Always
lead with Target. Stretch only when data confidence is high and
customer is sophisticated. Reference is the floor (need leadership
approval to go below).

**System overlay**
A documented organization-level adjustment we apply to certain health
systems where the facility-level data understates the picture. Kaiser
+ AMN is the canonical example.

**TAM / SAM**
Total / Serviceable addressable market. The data room rolls these up.
