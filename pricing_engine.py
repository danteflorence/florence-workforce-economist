"""
Florence Labor Economics Agent — reference pricing engine.

Implements the dynamic pricing model described in WHITE_PAPER_REVISIONS.md §5.
This is the canonical Python implementation; the TypeScript port lives in
care-capacity-index/src/lib/ficaAdvantage.ts (employer-side FICA component only).

Inputs:
  - HospitalProfile: loaded staff cost, all-in agency cost, market, role
  - CohortMix: visa composition (eta) and exempt-window assumption
  - Calibration: spread targets, savings buffer, production-cost floor, IRS values

Outputs:
  - PricingResult: F_base, F_fica, F, hospital effective premium,
    savings vs. agency, feasibility flag, channel routing, and a structured
    audit trail of every constant and intermediate used.

Conventions:
  - All hourly costs are in USD/hour
  - Commitment hours default to 5,616 (3 years × 1,872 hrs/yr nursing schedule)
  - All FICA assumptions are benchmark modeling; the hospital's tax/payroll/
    immigration teams must validate per-placement before billing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# IRS constants — calendar-year values. Update annually from IRS Rev. Proc.
# ---------------------------------------------------------------------------

EMPLOYER_SS_RATE = 0.062
EMPLOYER_MEDICARE_RATE = 0.0145
FICA_RATE_FLAT = EMPLOYER_SS_RATE + EMPLOYER_MEDICARE_RATE  # 7.65%

# Social Security wage base — IRS Rev. Proc. publishes annually.
SS_WAGE_BASE_2025 = 176_100
SS_WAGE_BASE_2026 = 184_500


# ---------------------------------------------------------------------------
# Calibration constants — tune against pilot data, version with audit trail.
# ---------------------------------------------------------------------------

class PricingMode(Enum):
    """v2 methodology pricing modes (Methodology §6).

    Production mode is FICA_OFFSET_TARGET (market-based); the rest are
    sensitivity / fallback / legacy modes.
    """
    FICA_OFFSET_TARGET = "fica_offset_target"   # Florence fee = FICA savings / target_offset_pct
    STANDARD_FEE = "standard_fee"               # Flat $1,750/RN/month
    BOUNDED_TARGET = "bounded_target"           # Target offset with custom floor/ceiling
    MANUAL_EXCEPTION = "manual_exception"       # Leadership-approved override
    LEGACY_V1 = "legacy_v1"                     # Product plan v1.0 (7.5% capture rate)


@dataclass(frozen=True)
class Calibration:
    """Calibration per Florence Workforce Restoration Economics v2 (May 2026).

    Default pricing mode is FICA_OFFSET_TARGET, where:
        SuggestedFee = EmployerFICASavingsPerRNPerMonth / target_offset_pct
        FinalFee = clamp(SuggestedFee, price_floor_monthly, price_ceiling_monthly)

    Florence is presumed to place F-1 nonresident-alien RNs during their
    nonresident-alien tax period, making the employer FICA exemption under
    IRC §3121(b)(19) reliable for the 24-month term. The hospital captures
    the FICA savings; Florence's fee is the visible invoice line; the
    FICA-adjusted effective cost is what the CFO sees as the true Florence
    cost net of the payroll-tax offset.
    """

    # Pricing mode (v2 §6)
    pricing_mode: PricingMode = PricingMode.FICA_OFFSET_TARGET

    # Monthly-anchored guardrails (v2 §6.2-6.3) — canonical buyer unit
    standard_monthly_fee: float = 1_750.00      # low-confidence fallback fee
    target_offset_pct: float = 0.40             # FICA covers 40% of fee (Florence protects more of the core rate)
    price_floor_monthly: float = 750.00         # $/RN/month — lowered to include 99% of US universe
    price_ceiling_monthly: float = 2_000.00     # $/RN/month
    manual_fee_override_monthly: Optional[float] = None  # for MANUAL_EXCEPTION mode

    # Low-confidence fallback (v2 §3 source hierarchy + §10 manual review)
    # When agency rate confidence is below this threshold, fall back to STANDARD_FEE
    # mode rather than blocking the quote — with a caveat that the price is based on
    # regional benchmarks pending customer disclosure.
    low_confidence_threshold: float = 0.50
    use_standard_fee_for_low_confidence: bool = True

    # Placeholder MSP markup pct (v2 §5.2) — applied at pricing time to systems
    # in the placeholder list (HCA, Ascension, Providence, UPMC, AdventHealth,
    # CHRISTUS, Ochsner, Sutter, Banner, Beth Israel Lahey, RWJBarnabas).
    # Kaiser uses its real-disclosed $622M overlay and is NOT affected by this.
    # Slider in Streamlit (0-50%) controls this value at runtime.
    placeholder_msp_markup_pct: float = 0.25

    # Term and hours (v2 §4)
    term_months: int = 24                       # default contract term
    annual_hours_rn: int = 1_872                # one Covered RN unit per year
    monthly_hours_rn: int = 156                 # 1,872 / 12

    # RN Need formula (v2 §5.3)
    rn_share_of_contracted_labor: float = 0.80
    coverage_fill_factor: float = 0.90          # plan calls this "DisplacementTarget"
    agency_displacement_factor: float = 1.0     # fraction of Florence hours that displace agency

    # Immigration add-on (v2 §6.5)
    immigration_addon_enabled: bool = False
    immigration_addon_total: float = 5_000.00   # 24-month coordination fee

    # FICA — IRS values (v2 §5.6)
    ss_wage_base: int = SS_WAGE_BASE_2026
    fica_eligible_months_default: int = 24      # F-1 cohort: full 24-month term eligible

    # Partner markup by channel — Florence net = core fee (protected);
    # partner margin is ADDED ON TOP of Florence's core rate.
    # Customer pays florence_fee × (1 + partner_markup).
    # Florence collects florence_fee regardless of channel.
    direct_partner_markup_pct: float = 0.00
    amn_partner_markup_pct: float = 0.20

    @property
    def direct_partner_share(self) -> float:
        """Backward-compat alias. Semantically: markup atop core rate."""
        return self.direct_partner_markup_pct

    @property
    def amn_partner_share(self) -> float:
        """Backward-compat alias. Semantically: markup atop core rate."""
        return self.amn_partner_markup_pct

    # --- Legacy v1.0 parameters kept for LEGACY_V1 mode comparison ---
    premium_capture_rate: float = 0.075
    premium_floor: float = 0.50
    premium_cap: float = 3.00

    version: str = "v0.5-methodology-v2-2026-05"

    # ---- Convenience properties -------------------------------------------
    @property
    def commitment_hours(self) -> int:
        """Total RN hours over the contract term (covered hours)."""
        return self.monthly_hours_rn * self.term_months

    @property
    def immigration_addon_monthly(self) -> float:
        """v2 §6.5: $5,000 / 24 months = $208.33/RN/month when enabled."""
        if not self.immigration_addon_enabled:
            return 0.0
        return self.immigration_addon_total / self.term_months if self.term_months > 0 else 0.0

    def partner_markup_for(self, channel: "Channel") -> float:
        """Partner markup atop Florence's core rate by channel routing.
        Florence's net is protected at the core fee regardless of channel."""
        return {
            Channel.DIRECT_ENTERPRISE: self.direct_partner_markup_pct,
            Channel.AMN_WHOLESALE: self.amn_partner_markup_pct,
            Channel.REDUCED_SCOPE: 0.0,
            Channel.STRATEGIC_PILOT: 0.0,
            Channel.NO_QUOTE: 0.0,
        }.get(channel, 0.0)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class Channel(Enum):
    DIRECT_ENTERPRISE = "direct_enterprise"   # e.g., Tenet
    AMN_WHOLESALE = "amn_wholesale"           # spread-risk routed to AMN
    REDUCED_SCOPE = "reduced_scope"           # screening + referral only
    STRATEGIC_PILOT = "strategic_pilot"       # subsidized
    NO_QUOTE = "no_quote"                     # economics do not work


@dataclass
class HospitalProfile:
    """A single pricing target. All hourly values are loaded (incl. benefits, employer FICA)."""
    name: str
    city: str
    state: str
    role: str = "RN — Med/Surg"
    taxable_wage_per_hour: float = 0.0   # W
    benefit_load_per_hour: float = 0.0   # B (non-FICA)
    all_in_agency_per_hour: float = 0.0  # A (incl. MSP allocation)
    notes: str = ""

    # Data provenance — drives manual-review logic
    agency_rate_confidence: float = 0.85       # 1.0 = customer-disclosed; <0.5 = low
    agency_rate_source: str = "unspecified"    # e.g., commonspirit_demo, state_imputed
    contracted_labor_fte: Optional[float] = None  # from HCRIS (when reported)
    contracted_labor_dollars: Optional[float] = None  # from HCRIS

    def loaded_staff_cost(self, cal: Calibration) -> float:
        """C = W + B + T_emp. We compute T_emp from W and the SS wage base."""
        t_emp = self.employer_fica_per_hour(cal)
        return self.taxable_wage_per_hour + self.benefit_load_per_hour + t_emp

    def employer_fica_per_hour(self, cal: Calibration) -> float:
        """Employer FICA $/hr for a normally-taxed RN.

        For F-1 nonresident-alien cohort (Florence's default), this is the
        SAVINGS the hospital realizes (the hospital does NOT pay this for the
        FICA-exempt placement). For non-exempt cohorts, savings = 0.
        """
        annual_w = self.taxable_wage_per_hour * cal.annual_hours_rn
        ss_taxable = min(annual_w, cal.ss_wage_base)
        annual_fica = ss_taxable * EMPLOYER_SS_RATE + annual_w * EMPLOYER_MEDICARE_RATE
        return annual_fica / cal.annual_hours_rn

    def annual_eligible_wages(self, cal: Calibration) -> float:
        """v2 §5.6 hourly wage basis: EligibleAnnualWages = wage × annual_hours."""
        return self.taxable_wage_per_hour * cal.annual_hours_rn

    def monthly_fica_savings(self, cal: Calibration, eta: float = 1.0,
                             eligible_months: Optional[int] = None) -> float:
        """v2 §5.6: ContractAverageMonthlyFICASavings.

        Computes employer FICA savings $/RN/month, adjusted for the cohort's
        FICA-eligible fraction (η) and the eligible-months / term ratio.
        """
        wages = self.annual_eligible_wages(cal)
        ss_savings = EMPLOYER_SS_RATE * min(wages, cal.ss_wage_base)
        medicare_savings = EMPLOYER_MEDICARE_RATE * wages
        annual_savings = (ss_savings + medicare_savings) * eta
        run_rate_monthly = annual_savings / 12
        elig = eligible_months if eligible_months is not None else cal.fica_eligible_months_default
        if cal.term_months > 0:
            contract_avg = run_rate_monthly * min(elig, cal.term_months) / cal.term_months
        else:
            contract_avg = run_rate_monthly
        return contract_avg


@dataclass
class CohortMix:
    """Visa composition of the Florence cohort placed at this hospital.

    Default η=1.0: Florence's confirmed pipeline is F-1 students on a 2-year
    placement during their nonresident-alien tax period. IRC §3121(b)(19)
    employer FICA exemption applies for the full term.
    """
    eta: float = 1.0                        # FICA-eligible share [0, 1]
    eligible_months: Optional[int] = None   # override cal.fica_eligible_months_default

    def __post_init__(self):
        if not 0.0 <= self.eta <= 1.0:
            raise ValueError(f"eta must be in [0, 1]; got {self.eta}")


@dataclass
class PricingResult:
    """v2 methodology pricing result. The five primary buyer-facing numbers
    are highlighted with comments — these are the headline metrics per v2 §1.
    """
    hospital: str
    cohort_eta: float
    pricing_mode: str

    # ---- Market inputs --------------------------------------------------
    loaded_staff_cost_per_hr: float
    agency_premium_per_hr: float            # MAX(A − C, 0)
    employer_fica_per_hr: float             # T_emp/hr (for ref)
    monthly_hours_rn: int                   # 156
    term_months: int                        # 24

    # ---- v2 PRIMARY BUYER-FACING NUMBERS (5) ---------------------------
    florence_monthly_fee_per_rn: float                # #1: Florence Monthly Fee per RN
    employer_fica_savings_per_rn_per_month: float     # #2: Employer FICA Savings/RN/Month
    fica_adjusted_effective_cost_per_rn_month: float  # #3: FICA-Adjusted Effective Cost
    actual_fica_offset_pct: float                     # #4: Actual FICA Offset %
    net_monthly_savings_per_rn: float                 # #5: Net Monthly Savings/RN

    # ---- Pricing decision detail ---------------------------------------
    suggested_fee_pre_guardrails: float     # FICA / target_offset_pct
    final_fee_constrained_by: str           # "floor" | "ceiling" | "target" | "standard" | "override"
    target_offset_pct: float                # default 0.50
    price_floor_monthly: float              # default $1,500
    price_ceiling_monthly: float            # default $2,000

    # ---- Immigration add-on (v2 §6.5) ----------------------------------
    immigration_addon_monthly: float        # $208.33 if enabled, else 0
    all_in_florence_fee_per_rn_month: float # final_fee + addon
    all_in_fica_adjusted_cost_per_rn_month: float

    # ---- Agency premium economics (per RN per month) -------------------
    monthly_agency_premium_avoided_per_rn: float

    # ---- 24-month / term totals (per RN) -------------------------------
    term_florence_fee_per_rn: float         # monthly × term
    term_employer_fica_offset_per_rn: float
    term_effective_cost_per_rn: float
    term_gross_agency_savings_per_rn: float
    term_net_savings_per_rn: float

    # ---- Partner markup atop Florence's core rate ----------------------
    # `partner_share` retained as field name for backward-compat; semantics is
    # now MARKUP atop Florence's core fee (not share of fee). Florence's net
    # always equals the core fee — protected regardless of channel.
    partner_share: float                    # alias for partner_markup_pct
    partner_revenue_monthly: float          # partner's added margin atop core fee
    florence_net_monthly: float             # Florence's core fee (protected)
    florence_net_term: float
    customer_total_monthly: float           # what customer pays = core + markup

    # ---- Routing / governance ------------------------------------------
    feasible: bool
    channel: Channel
    manual_review_flag: bool
    manual_review_reason: str
    rationale: list[str] = field(default_factory=list)

    # ---- Legacy / backward-compat aliases (so existing code keeps working) -
    # These map v2 fields to the field names used by pricing_batch and the
    # Streamlit app. Computed in price() after the v2 values are known.
    f_base: float = 0.0
    f_fica: float = 0.0
    f_total: float = 0.0                    # gross term fee (= term_florence_fee_per_rn)
    monthly_fee: float = 0.0                # = florence_monthly_fee_per_rn
    amortization_months: int = 24
    commitment_hours: int = 5_616
    exempt_hours: int = 3_744
    premium_capture_rate: float = 0.0
    premium_floor: float = 0.0
    premium_cap: float = 0.0
    delta_raw: float = 0.0
    delta_chosen: float = 0.0
    hospital_normal_3yr_cost: float = 0.0
    hospital_effective_3yr_cost: float = 0.0
    hospital_premium_per_hr: float = 0.0
    agency_3yr_cost: float = 0.0
    gross_agency_savings: float = 0.0
    net_savings: float = 0.0
    net_savings_per_hr: float = 0.0
    partner_revenue: float = 0.0
    florence_net_revenue: float = 0.0
    florence_net_monthly_alias: float = 0.0  # avoid name clash with primary

    # ---- Audit ----------------------------------------------------------
    calibration_version: str = ""


# ---------------------------------------------------------------------------
# Core pricing function
# ---------------------------------------------------------------------------

def price(
    hospital: HospitalProfile,
    cohort: CohortMix = CohortMix(),
    cal: Calibration = Calibration(),
    system_id: str = "independent",
) -> PricingResult:
    """
    Florence Workforce Restoration Economics v2 pricing.

    Computes the five primary buyer-facing numbers:
        1. Florence Monthly Fee per RN
        2. Employer FICA Savings per RN per Month
        3. FICA-Adjusted Effective Cost per RN per Month  (= 1 − 2)
        4. Actual FICA Offset %  (= 2 ÷ 1)
        5. Net Monthly Savings per RN  (= Agency Premium Avoided + FICA Savings − Fee)

    Pricing modes (selected via Calibration.pricing_mode):
        FICA_OFFSET_TARGET : Suggested = FICA / target_offset_pct, clamped [floor, ceiling]
        STANDARD_FEE       : Flat standard_monthly_fee
        BOUNDED_TARGET     : Target with custom floor/ceiling
        MANUAL_EXCEPTION   : Uses manual_fee_override_monthly
        LEGACY_V1          : Product plan v1.0 capture-rate formula

    Manual review fires when agency rate is missing, zero, or low-confidence.
    In that case the engine does NOT auto-price — the row is flagged for human
    review per v2 methodology §3 source hierarchy + §10 validation.
    """
    rationale: list[str] = []

    # ---- Inputs ----------------------------------------------------------
    C = hospital.loaded_staff_cost(cal)
    A = hospital.all_in_agency_per_hour
    T_emp = hospital.employer_fica_per_hour(cal)
    M_raw = A - C
    M = max(M_raw, 0)
    H_monthly = cal.monthly_hours_rn
    H_term = H_monthly * cal.term_months  # covered RN hours over contract

    # ---- Manual-review gate (v2 §10 validation) --------------------------
    # STANDARD_FEE doesn't need a positive agency premium —
    # the fee is set independent of agency math. Only FICA_OFFSET_TARGET /
    # BOUNDED_TARGET / LEGACY_V1 are blocked when agency premium is missing or
    # non-positive (because their fee logic uses the agency premium).
    manual_review = False
    manual_review_reason = ""
    low_confidence_fallback = False
    modes_needing_agency_premium = {
        PricingMode.FICA_OFFSET_TARGET,
        PricingMode.BOUNDED_TARGET,
        PricingMode.LEGACY_V1,
    }
    if cal.pricing_mode in modes_needing_agency_premium:
        if A <= 0:
            manual_review = True
            manual_review_reason = "Agency rate missing or zero; cannot compute premium."
        elif M_raw <= 0:
            manual_review = True
            manual_review_reason = (
                f"Agency premium non-positive (A=${A:.2f}, C=${C:.2f}, M=${M_raw:.2f}). "
                "Customer disclosure required before quoting."
            )
        elif (cal.use_standard_fee_for_low_confidence
              and hospital.agency_rate_confidence < cal.low_confidence_threshold):
            low_confidence_fallback = True
            rationale.append(
                f"Low agency-rate confidence ({hospital.agency_rate_confidence:.2f}, "
                f"source: {hospital.agency_rate_source}). Falling back to "
                f"STANDARD_FEE mode (${cal.standard_monthly_fee:,.0f}/RN/mo) — "
                "price based on regional benchmarks pending customer disclosure."
            )

    # ---- Employer FICA savings per RN per month (v2 §5.6) ---------------
    fica_savings_monthly = hospital.monthly_fica_savings(
        cal, eta=cohort.eta, eligible_months=cohort.eligible_months
    )
    rationale.append(
        f"Employer FICA savings: η={cohort.eta:.2f} × eligible months "
        f"{cohort.eligible_months or cal.fica_eligible_months_default}/{cal.term_months} "
        f"= ${fica_savings_monthly:,.0f}/RN/month."
    )

    # ---- Pricing decision (v2 §6) ----------------------------------------
    suggested_fee = 0.0
    final_fee = 0.0
    constrained_by = "n/a"

    if manual_review:
        final_fee = 0.0
        constrained_by = "manual_review"
        rationale.append(f"MANUAL REVIEW: {manual_review_reason}")
    elif low_confidence_fallback:
        # Forced STANDARD_FEE mode for low-confidence agency-rate rows
        final_fee = cal.standard_monthly_fee
        suggested_fee = final_fee
        constrained_by = "low_confidence_standard"
    elif cal.pricing_mode == PricingMode.MANUAL_EXCEPTION:
        final_fee = cal.manual_fee_override_monthly or cal.standard_monthly_fee
        suggested_fee = final_fee
        constrained_by = "override"
        rationale.append(f"MANUAL EXCEPTION override: ${final_fee:,.0f}/RN/month.")
    elif cal.pricing_mode == PricingMode.STANDARD_FEE:
        final_fee = cal.standard_monthly_fee
        suggested_fee = final_fee
        constrained_by = "standard"
        rationale.append(f"Standard fee mode: ${final_fee:,.0f}/RN/month flat.")
    elif cal.pricing_mode == PricingMode.LEGACY_V1:
        # Product plan v1.0 formula for comparison
        delta_raw = M * cal.premium_capture_rate
        delta = max(cal.premium_floor, min(cal.premium_cap, delta_raw))
        final_fee = delta * H_monthly
        suggested_fee = delta_raw * H_monthly
        constrained_by = "legacy_v1"
        rationale.append(
            f"LEGACY v1.0 mode: {cal.premium_capture_rate:.1%} capture × M=${M:.2f}/hr × "
            f"{H_monthly} hrs = ${final_fee:,.0f}/month."
        )
    else:
        # FICA_OFFSET_TARGET (v2 §6.2) or BOUNDED_TARGET
        if cal.target_offset_pct <= 0:
            suggested_fee = cal.standard_monthly_fee
            rationale.append("target_offset_pct = 0; falling back to standard fee.")
        else:
            suggested_fee = fica_savings_monthly / cal.target_offset_pct
            rationale.append(
                f"Suggested fee = FICA ${fica_savings_monthly:,.0f} ÷ "
                f"{cal.target_offset_pct:.0%} target = ${suggested_fee:,.0f}/RN/month."
            )
        # Apply guardrails
        floor = cal.price_floor_monthly
        ceiling = cal.price_ceiling_monthly
        if suggested_fee < floor:
            final_fee = floor
            constrained_by = "floor"
            rationale.append(
                f"Suggested fee ${suggested_fee:,.0f} below floor ${floor:,.0f}; "
                "floor applied (FICA offset will be < target_offset_pct)."
            )
        elif suggested_fee > ceiling:
            final_fee = ceiling
            constrained_by = "ceiling"
            rationale.append(
                f"Suggested fee ${suggested_fee:,.0f} above ceiling ${ceiling:,.0f}; "
                "ceiling applied (FICA offset will be > target_offset_pct)."
            )
        else:
            final_fee = suggested_fee
            constrained_by = "target"

    feasible = not manual_review

    # ---- The five primary buyer-facing numbers --------------------------
    monthly_fee = final_fee                                         # #1
    fica_monthly = fica_savings_monthly                             # #2
    fica_adjusted_cost = monthly_fee - fica_monthly                 # #3
    actual_offset_pct = (
        fica_monthly / monthly_fee if monthly_fee > 0 else 0.0
    )                                                               # #4

    # Monthly agency premium avoided per RN (v2 §5.4)
    monthly_agency_premium_avoided = (
        M * H_monthly * cal.agency_displacement_factor
    )
    net_monthly_savings = (
        monthly_agency_premium_avoided + fica_monthly - monthly_fee
    )                                                               # #5

    # ---- Immigration add-on (v2 §6.5) -----------------------------------
    addon_monthly = cal.immigration_addon_monthly
    all_in_fee = monthly_fee + addon_monthly
    all_in_fica_adjusted = all_in_fee - fica_monthly

    # ---- Term totals per RN ---------------------------------------------
    term_florence_fee = monthly_fee * cal.term_months
    term_fica_offset = fica_monthly * cal.term_months
    term_effective_cost = fica_adjusted_cost * cal.term_months
    term_gross_savings = monthly_agency_premium_avoided * cal.term_months
    term_net_savings = net_monthly_savings * cal.term_months

    # ---- Channel routing -------------------------------------------------
    if manual_review:
        channel = Channel.NO_QUOTE
    else:
        channel = Channel.DIRECT_ENTERPRISE

    # ---- Partner markup atop Florence's core rate (monthly + term) ------
    # Florence's net is the core fee. Partner margin is ADDED on top —
    # customer pays florence_fee × (1 + markup); Florence collects florence_fee
    # regardless of channel.
    partner_markup_pct = cal.partner_markup_for(channel)
    partner_monthly = monthly_fee * partner_markup_pct
    florence_net_monthly = monthly_fee                        # protected at core
    florence_net_term = florence_net_monthly * cal.term_months
    customer_total_monthly = monthly_fee + partner_monthly
    if partner_markup_pct > 0:
        rationale.append(
            f"Channel {channel.value}: partner markup {partner_markup_pct:.0%} atop "
            f"Florence's core rate. Customer pays ${customer_total_monthly:,.0f}/mo; "
            f"partner margin ${partner_monthly:,.0f}/mo; Florence net ${florence_net_monthly:,.0f}/mo "
            f"(core rate protected)."
        )

    # ---- Build result with v2 fields + legacy aliases -------------------
    result = PricingResult(
        hospital=f"{hospital.name} ({hospital.city}, {hospital.state})",
        cohort_eta=cohort.eta,
        pricing_mode=cal.pricing_mode.value,
        loaded_staff_cost_per_hr=C,
        agency_premium_per_hr=M,
        employer_fica_per_hr=T_emp,
        monthly_hours_rn=H_monthly,
        term_months=cal.term_months,

        # Primary 5 numbers
        florence_monthly_fee_per_rn=monthly_fee,
        employer_fica_savings_per_rn_per_month=fica_monthly,
        fica_adjusted_effective_cost_per_rn_month=fica_adjusted_cost,
        actual_fica_offset_pct=actual_offset_pct,
        net_monthly_savings_per_rn=net_monthly_savings,

        # Decision detail
        suggested_fee_pre_guardrails=suggested_fee,
        final_fee_constrained_by=constrained_by,
        target_offset_pct=cal.target_offset_pct,
        price_floor_monthly=cal.price_floor_monthly,
        price_ceiling_monthly=cal.price_ceiling_monthly,

        # Immigration add-on
        immigration_addon_monthly=addon_monthly,
        all_in_florence_fee_per_rn_month=all_in_fee,
        all_in_fica_adjusted_cost_per_rn_month=all_in_fica_adjusted,

        # Agency premium
        monthly_agency_premium_avoided_per_rn=monthly_agency_premium_avoided,

        # Term totals
        term_florence_fee_per_rn=term_florence_fee,
        term_employer_fica_offset_per_rn=term_fica_offset,
        term_effective_cost_per_rn=term_effective_cost,
        term_gross_agency_savings_per_rn=term_gross_savings,
        term_net_savings_per_rn=term_net_savings,

        # Partner markup atop Florence's core rate
        partner_share=partner_markup_pct,
        partner_revenue_monthly=partner_monthly,
        florence_net_monthly=florence_net_monthly,
        florence_net_term=florence_net_term,
        customer_total_monthly=customer_total_monthly,

        # Governance
        feasible=feasible,
        channel=channel,
        manual_review_flag=manual_review,
        manual_review_reason=manual_review_reason,
        rationale=rationale,

        # Legacy aliases (so older downstream code keeps working)
        f_base=monthly_fee * cal.term_months,        # term gross
        f_fica=0.0,                                   # FICA goes to hospital, not Florence's fee
        f_total=term_florence_fee,                    # term gross fee
        monthly_fee=monthly_fee,
        amortization_months=cal.term_months,
        commitment_hours=H_term,
        exempt_hours=H_term,
        premium_capture_rate=cal.premium_capture_rate,
        premium_floor=cal.premium_floor,
        premium_cap=cal.premium_cap,
        delta_raw=monthly_fee / H_monthly if H_monthly > 0 else 0.0,
        delta_chosen=monthly_fee / H_monthly if H_monthly > 0 else 0.0,
        hospital_normal_3yr_cost=C * H_term,
        hospital_effective_3yr_cost=C * H_term + term_florence_fee - term_fica_offset,
        hospital_premium_per_hr=(monthly_fee - fica_monthly) / H_monthly if H_monthly > 0 else 0.0,
        agency_3yr_cost=A * H_term,
        gross_agency_savings=term_gross_savings,
        net_savings=term_net_savings,
        net_savings_per_hr=net_monthly_savings / H_monthly if H_monthly > 0 else 0.0,
        partner_revenue=partner_monthly * cal.term_months,
        florence_net_revenue=florence_net_term,
        florence_net_monthly_alias=florence_net_monthly,
        calibration_version=cal.version,
    )
    return result


# ---------------------------------------------------------------------------
# Evidence-pack rendering — what the agent emits per quote
# ---------------------------------------------------------------------------

REQUIRED_COMPLIANCE_SENTENCE = (
    "Estimated employer-side FICA offset shown for eligible nurse cohorts only. "
    "Eligibility must be validated by payroll, tax counsel, and immigration counsel. "
    "Employee-side FICA benefit is shown separately as a nurse take-home benefit "
    "and is not included in employer ROI unless presented as combined economic value."
)


def render_evidence_pack(result: PricingResult) -> str:
    """v2 evidence pack — leads with the five primary buyer-facing numbers."""
    lines = [
        f"FLORENCE PRICING — {result.hospital}",
        f"Pricing mode: {result.pricing_mode}   Cohort η = {result.cohort_eta:.2f}",
        f"Calibration version: {result.calibration_version}",
        "",
        "─" * 78,
        "PRIMARY BUYER-FACING NUMBERS (per RN per month)",
        f"  1. Florence Monthly Fee per RN            ${result.florence_monthly_fee_per_rn:>10,.2f}",
        f"  2. Employer FICA Savings per RN/month     ${result.employer_fica_savings_per_rn_per_month:>10,.2f}",
        f"  3. FICA-Adjusted Effective Cost per RN/mo ${result.fica_adjusted_effective_cost_per_rn_month:>10,.2f}",
        f"  4. Actual FICA Offset % of fee            {result.actual_fica_offset_pct:>10.1%}",
        f"  5. Net Monthly Savings per RN             ${result.net_monthly_savings_per_rn:>10,.2f}",
        "",
        "─" * 78,
        "MARKET INPUTS",
        f"  Loaded staff cost (C)         ${result.loaded_staff_cost_per_hr:>8.2f} / hour",
        f"  All-in agency cost (A)        ${result.loaded_staff_cost_per_hr + result.agency_premium_per_hr:>8.2f} / hour",
        f"  Agency premium (M = A − C)    ${result.agency_premium_per_hr:>8.2f} / hour",
        f"  Employer FICA per hour        ${result.employer_fica_per_hr:>8.2f} / hour",
        f"  Monthly hours per covered RN  {result.monthly_hours_rn:>8,}",
        f"  Term (months)                 {result.term_months:>8,}",
        "",
        "PRICING DECISION",
        f"  Suggested fee (pre-guardrails)     ${result.suggested_fee_pre_guardrails:>9,.0f} / RN / month",
        f"  Price floor                        ${result.price_floor_monthly:>9,.0f}",
        f"  Price ceiling                      ${result.price_ceiling_monthly:>9,.0f}",
        f"  Target offset %                    {result.target_offset_pct:>9.0%}",
        f"  Final fee constrained by           {result.final_fee_constrained_by:>9}",
        "",
        f"  AGENCY PREMIUM AVOIDED per RN/mo   ${result.monthly_agency_premium_avoided_per_rn:>10,.2f}",
        "",
    ]

    if result.immigration_addon_monthly > 0:
        lines.extend([
            "IMMIGRATION TRANSITION ADD-ON",
            f"  Add-on monthly                ${result.immigration_addon_monthly:>10,.2f} / RN",
            f"  All-in fee per RN/month       ${result.all_in_florence_fee_per_rn_month:>10,.2f}",
            f"  All-in FICA-adjusted cost     ${result.all_in_fica_adjusted_cost_per_rn_month:>10,.2f}",
            "",
        ])

    lines.extend([
        f"TERM TOTALS (per RN over {result.term_months} months)",
        f"  Florence fee per RN          ${result.term_florence_fee_per_rn:>11,.0f}",
        f"  Employer FICA offset per RN  ${result.term_employer_fica_offset_per_rn:>11,.0f}",
        f"  Effective cost per RN        ${result.term_effective_cost_per_rn:>11,.0f}",
        f"  Gross agency savings per RN  ${result.term_gross_agency_savings_per_rn:>11,.0f}",
        f"  Net savings per RN           ${result.term_net_savings_per_rn:>11,.0f}",
        "",
        "REVENUE SPLIT (monthly)",
        f"  Partner share                  {result.partner_share:>10.0%}",
        f"  Partner revenue / RN / month   ${result.partner_revenue_monthly:>10,.0f}",
        f"  Florence net / RN / month      ${result.florence_net_monthly:>10,.0f}",
        f"  Florence net per RN (term)     ${result.florence_net_term:>10,.0f}",
        "",
        f"FEASIBLE: {result.feasible}    CHANNEL: {result.channel.value}    "
        f"MANUAL REVIEW: {result.manual_review_flag}",
        "",
        "RATIONALE",
    ])
    for r in result.rationale:
        lines.append(f"  • {r}")
    lines.append("")
    lines.append("REQUIRED COMPLIANCE STATEMENT (Florence Workforce Restoration Economics v2)")
    # Word-wrap the required compliance sentence at ~78 chars
    import textwrap
    for ln in textwrap.wrap(REQUIRED_COMPLIANCE_SENTENCE, width=76):
        lines.append(f"  {ln}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demo: run the four-market example set
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Reproduces the multi-market worked-example set in MULTI_MARKET_EXAMPLES.md."""
    cal = Calibration()

    # Hospital profiles drawn from CommonSpirit demo data (rates reflect actual
    # contracted spend / contracted hours).
    # taxable_wage_per_hour and benefit_load are estimated from staff_rate, which
    # in the demo is already loaded; we decompose roughly as:
    #     W = staff_rate / 1.30   (treating staff_rate as ~30% loaded above wage)
    #     B = staff_rate - W - T_emp
    # In production this would come from CMS cost reports + BLS wage decomposition.
    hospitals = [
        HospitalProfile(
            name="Saint Francis Memorial Hospital",
            city="San Francisco", state="CA",
            role="RN — ICU",
            taxable_wage_per_hour=85.00,
            benefit_load_per_hour=27.50,
            all_in_agency_per_hour=230.60,
            notes="Top-of-market SF agency rate; large absolute spread.",
        ),
        HospitalProfile(
            name="Mercy Hospital",
            city="Bakersfield", state="CA",
            role="RN — Med/Surg",
            taxable_wage_per_hour=58.00,
            benefit_load_per_hour=18.00,
            all_in_agency_per_hour=135.19,
            notes="Mid-premium Central Valley market.",
        ),
        HospitalProfile(
            name="St. Mary's Hospital",
            city="Grand Junction", state="CO",
            role="RN — Med/Surg",
            taxable_wage_per_hour=48.00,
            benefit_load_per_hour=14.00,
            all_in_agency_per_hour=125.08,
            notes="Lower-cost Western Colorado market, high agency premium.",
        ),
        HospitalProfile(
            name="Methodist Hospital of Southern California",
            city="Arcadia", state="CA",
            role="RN — Med/Surg",
            taxable_wage_per_hour=68.00,
            benefit_load_per_hour=22.00,
            all_in_agency_per_hour=109.39,
            notes="Tight agency premium (14% in source data); still feasible at default δ.",
        ),
        HospitalProfile(
            name="Hypothetical Compressed-Premium Facility",
            city="(midwest market)", state="—",
            role="RN — Med/Surg",
            taxable_wage_per_hour=42.00,
            benefit_load_per_hour=15.00,
            all_in_agency_per_hour=62.00,
            notes="Synthetic case: agency barely above loaded staff cost. Tests no-quote / AMN-wholesale routing.",
        ),
    ]
    cohorts = [
        ("A — F-1/J-1 (η=1.0)", CohortMix(eta=1.0)),
        ("B — mixed (η=0.3)", CohortMix(eta=0.3)),
        ("C — EB-3 / H-1B (η=0.0)", CohortMix(eta=0.0)),
    ]

    for h in hospitals:
        for label, cohort in cohorts:
            r = price(h, cohort, cal)
            print(f"\n### {h.name} — Scenario {label}")
            print(render_evidence_pack(r))


if __name__ == "__main__":
    _demo()
