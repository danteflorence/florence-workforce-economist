"""
Recommendation engine — per-facility optimal pricing for the sales tool.

For each hospital, searches the calibration space (target FICA offset %) and
picks the configuration that maximizes expected revenue:

    E[revenue] = fee × P(close)

where P(close) is a transparent 5-component heuristic:

    1. Savings:Fee ratio    (30% weight) — higher = easier CFO sell
    2. Contract labor intensity (20%)    — higher = more pain → more motivation
    3. FICA target adherence (20%)       — closer to 50% = clean "tax pays half" story
    4. Agency premium magnitude (15%)    — visible dollar savings
    5. Data confidence (15%)             — fewer pricing objections

Returns a Recommendation with the optimal fee, the rationale paragraph, and
the per-signal breakdown so sales can see WHY this price.

Public API:
    recommend_pricing(hospital_row, base_cal=None) -> Recommendation
    batch_recommend(universe_df, base_cal=None) -> pd.DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from pricing_engine import Calibration, CohortMix, price
from pricing_batch import row_to_profile


# ---------------------------------------------------------------------------
# Configurable search space + heuristic weights
# ---------------------------------------------------------------------------

# Calibration variants the engine evaluates per hospital. The win-probability
# heuristic re-scores each one and the engine picks the max(fee × P_close).
TARGET_OFFSET_GRID = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]

# Heuristic weights — must sum to 1.0. Tunable as Florence accumulates real
# win-rate data (replace with logistic regression on actual closed/lost outcomes).
# Note: savings_ratio + fee_magnitude must keep meaningful weight together so
# P_close actually moves with fee size (otherwise the engine just picks the
# highest fee within guardrails).
WIN_PROB_WEIGHTS = {
    "savings_ratio":      0.30,
    "fee_magnitude":      0.15,    # NEW: penalize fees near the ceiling
    "cl_intensity":       0.15,
    "fica_target_match":  0.15,
    "premium_size":       0.15,
    "data_confidence":    0.10,
}
assert abs(sum(WIN_PROB_WEIGHTS.values()) - 1.0) < 1e-6, "weights must sum to 1.0"

# Score-normalization thresholds.
SCORE_THRESHOLDS = {
    "cl_intensity_high":     0.20,     # 20% contract labor share = top
    "premium_high":          30.0,     # $30/hr agency premium = top
    "fica_target":           0.50,     # 50% offset target — peaks here
    # Savings ratio uses an asymptotic curve (no hard cap):
    "savings_ratio_scale":   6.0,      # score = 1 - exp(-ratio/scale); approaches 1.0 asymptotically
    # Fee magnitude penalty — quadratic ramp from $750 floor → 0 at $2,000 ceiling
    "fee_ceiling_ref":       2000.0,
    "fee_floor_ref":         750.0,
}


@dataclass
class SignalBreakdown:
    """Per-component contributions to the win-probability score."""
    savings_ratio_raw: float
    savings_ratio_score: float
    fee_magnitude_raw: float
    fee_magnitude_score: float
    cl_intensity_raw: float
    cl_intensity_score: float
    fica_offset_raw: float
    fica_offset_score: float
    premium_raw: float
    premium_score: float
    confidence_raw: float
    confidence_score: float


@dataclass
class PriceTier:
    """A single price-tier within the negotiation band."""
    tier_label: str                       # "Stretch" | "Target" | "Reference"
    target_offset_pct: float
    monthly_fee: float
    hourly_fee: float                     # monthly_fee / 156
    fica_savings_per_rn_per_month: float
    fica_adjusted_effective_cost: float
    net_monthly_savings_per_rn: float
    savings_ratio: float
    deal_score: float                     # 0-1 attractiveness score
    monthly_florence_fee_account: float
    term_florence_fee_account: float
    term_net_savings_account: float


@dataclass
class Recommendation:
    """Per-facility pricing recommendation with 3-tier negotiation band."""
    ccn: str
    hospital_name: str
    recommended_term_months: int
    rn_need: float
    monthly_hours_rn: int = 156

    # The negotiation band — three tiers for the sales rep
    stretch: PriceTier = None             # Highest viable fee (deal-score ≥ threshold)
    target: PriceTier = None              # Balanced max(fee × deal-score)
    reference: PriceTier = None           # Lowest-fee / max-customer-savings pitch

    # Signal breakdown (computed at TARGET tier; same hospital data drives all 3)
    signals: SignalBreakdown = None
    rationale: str = ""

    # Used by sorts/filters
    primary_state: str = ""
    health_system: str = ""
    health_system_id: str = ""
    city: str = ""


# ---------------------------------------------------------------------------
# Win probability heuristic
# ---------------------------------------------------------------------------

def _score_savings_ratio(ratio: float) -> float:
    """Higher savings:fee ratio = easier sell. Asymptotic curve: 1 - exp(-ratio/scale).
    No hard cap so even high ratios keep differentiating."""
    import math
    if ratio <= 0:
        return 0.0
    return 1.0 - math.exp(-ratio / SCORE_THRESHOLDS["savings_ratio_scale"])


def _score_fee_magnitude(fee_monthly: float) -> float:
    """Lower fee = easier to slide past procurement. Score 1.0 at floor, 0 at ceiling."""
    floor = SCORE_THRESHOLDS["fee_floor_ref"]
    ceiling = SCORE_THRESHOLDS["fee_ceiling_ref"]
    if fee_monthly <= floor:
        return 1.0
    if fee_monthly >= ceiling:
        return 0.0
    # Quadratic decay from 1.0 at floor to 0.0 at ceiling
    norm = (fee_monthly - floor) / (ceiling - floor)
    return max(0.0, 1.0 - norm ** 2)


def _score_cl_intensity(cl_intensity: Optional[float]) -> float:
    """Higher contract-labor share = hospital is in more pain. Caps at 20%."""
    if cl_intensity is None or pd.isna(cl_intensity):
        return 0.3  # neutral score if unknown
    return min(cl_intensity / SCORE_THRESHOLDS["cl_intensity_high"], 1.0)


def _score_fica_target(actual_offset_pct: float) -> float:
    """FICA offset closest to 50% target = cleanest 'tax pays half' story.
    Score peaks at 50% and falls off symmetrically."""
    distance = abs(actual_offset_pct - SCORE_THRESHOLDS["fica_target"])
    return max(0.0, 1.0 - distance * 2.0)


def _score_premium(premium_per_hr: float) -> float:
    """Visible dollar savings. Caps at $30/hr premium."""
    if premium_per_hr <= 0:
        return 0.0
    return min(premium_per_hr / SCORE_THRESHOLDS["premium_high"], 1.0)


def _score_confidence(confidence: float) -> float:
    """Data confidence directly scales — high-conf data is harder to dispute."""
    return max(0.0, min(confidence, 1.0))


def win_probability(
    fee_monthly: float,
    net_savings_monthly: float,
    actual_fica_offset_pct: float,
    cl_intensity: Optional[float],
    agency_premium_per_hr: float,
    confidence: float,
) -> tuple[float, SignalBreakdown]:
    """Heuristic P(close) on [0, 1] for a given hospital + fee combination."""
    ratio = net_savings_monthly / fee_monthly if fee_monthly > 0 else 0
    s_ratio  = _score_savings_ratio(ratio)
    s_fee    = _score_fee_magnitude(fee_monthly)
    s_cl     = _score_cl_intensity(cl_intensity)
    s_fica   = _score_fica_target(actual_fica_offset_pct)
    s_prem   = _score_premium(agency_premium_per_hr)
    s_conf   = _score_confidence(confidence)

    score = (
        s_ratio  * WIN_PROB_WEIGHTS["savings_ratio"]
        + s_fee  * WIN_PROB_WEIGHTS["fee_magnitude"]
        + s_cl   * WIN_PROB_WEIGHTS["cl_intensity"]
        + s_fica * WIN_PROB_WEIGHTS["fica_target_match"]
        + s_prem * WIN_PROB_WEIGHTS["premium_size"]
        + s_conf * WIN_PROB_WEIGHTS["data_confidence"]
    )

    breakdown = SignalBreakdown(
        savings_ratio_raw=ratio, savings_ratio_score=s_ratio,
        fee_magnitude_raw=fee_monthly, fee_magnitude_score=s_fee,
        cl_intensity_raw=cl_intensity or 0.0, cl_intensity_score=s_cl,
        fica_offset_raw=actual_fica_offset_pct, fica_offset_score=s_fica,
        premium_raw=agency_premium_per_hr, premium_score=s_prem,
        confidence_raw=confidence, confidence_score=s_conf,
    )
    return score, breakdown


# ---------------------------------------------------------------------------
# Rationale generator (sales-friendly full paragraph)
# ---------------------------------------------------------------------------

def _rationale_paragraph(rec: Recommendation, sys_overlay_used: bool = False) -> str:
    """Paragraph explaining the negotiation band for sales-rep consumption."""
    s = rec.signals
    t = rec.target
    parts = []

    # Lead sentence: target recommendation + band
    parts.append(
        f"**Recommended monthly invoice: ${t.monthly_fee:,.0f}/RN/month** at a "
        f"{t.target_offset_pct:.0%} FICA-offset target. "
        f"Negotiation band: open at **${rec.stretch.monthly_fee:,.0f}** (stretch), land at "
        f"**${t.monthly_fee:,.0f}** (target), walk away below **${rec.reference.monthly_fee:,.0f}** "
        f"(reference / max customer-savings pitch)."
    )

    # FICA story
    parts.append(
        f"At the target price, each F-1 nurse generates **${t.fica_savings_per_rn_per_month:,.0f}/month "
        f"in employer payroll-tax savings** for the hospital (~{s.fica_offset_raw*100:.0f}% of the "
        f"Florence fee). True Florence cost after the tax offset is "
        f"**${t.fica_adjusted_effective_cost:,.0f}/RN/month**."
    )

    # Savings story with band context
    ratio_text = (
        f"a **{t.savings_ratio:.1f}× return** on the Florence fee at target "
        f"(stretch = {rec.stretch.savings_ratio:.1f}×, reference = {rec.reference.savings_ratio:.1f}×)"
        if t.savings_ratio >= 0.5
        else f"**only a {t.savings_ratio:.2f}× return** — the agency premium at this "
             "facility is too thin for a compelling pitch; deprioritize unless customer "
             "discloses additional agency spend not captured in HCRIS"
    )
    parts.append(
        f"Against the all-in agency labor this hospital reports (HCRIS line 01100"
        f"{' + AMN MSP overlay' if sys_overlay_used else ''}, agency premium "
        f"${s.premium_raw:,.2f}/hr), the hospital nets **${t.net_monthly_savings_per_rn:,.0f}/month "
        f"in savings per nurse** at the target price — {ratio_text}."
    )

    # Motivation signal (CL share)
    if s.cl_intensity_raw and s.cl_intensity_raw > 0.01:
        intensity_label = (
            "high" if s.cl_intensity_raw >= 0.20 else
            "moderate" if s.cl_intensity_raw >= 0.10 else
            "low"
        )
        parts.append(
            f"Their contract-labor intensity is **{s.cl_intensity_raw*100:.1f}% of total compensation** "
            f"({intensity_label}), which signals "
            + ("real budget pain from agency labor and motivation to convert to permanent staff."
               if s.cl_intensity_raw >= 0.10 else
               "modest agency reliance — pitch may benefit from emphasizing margin protection rather than crisis response.")
        )

    # Confidence caveat
    if s.confidence_raw < 0.85:
        parts.append(
            f"⚠️ Data confidence is {s.confidence_raw:.2f} (agency rate sourced from "
            f"regional benchmarks; customer disclosure recommended before binding the quote)."
        )

    # Close: deal-attractiveness scores across band
    parts.append(
        f"Deal-attractiveness score: **{t.deal_score*100:.0f}/100 at target** "
        f"(stretch {rec.stretch.deal_score*100:.0f}/100, reference {rec.reference.deal_score*100:.0f}/100). "
        "This is a structural heuristic combining savings ratio, fee magnitude, CL share, "
        "agency premium, FICA-target alignment, and data confidence — not an empirical close-rate."
    )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Tier builders
# ---------------------------------------------------------------------------

# Minimum deal-score required for the "Stretch" tier — i.e., highest fee where
# we still believe the deal is closeable. Tunable.
STRETCH_MIN_DEAL_SCORE = 0.55


def _tier_from_result(label: str, target_pct: float, result, deal_score: float,
                      rn_need: float, monthly_hours: int) -> PriceTier:
    return PriceTier(
        tier_label=label,
        target_offset_pct=target_pct,
        monthly_fee=result.florence_monthly_fee_per_rn,
        hourly_fee=result.florence_monthly_fee_per_rn / monthly_hours if monthly_hours else 0,
        fica_savings_per_rn_per_month=result.employer_fica_savings_per_rn_per_month,
        fica_adjusted_effective_cost=result.fica_adjusted_effective_cost_per_rn_month,
        net_monthly_savings_per_rn=result.net_monthly_savings_per_rn,
        savings_ratio=(result.net_monthly_savings_per_rn / result.florence_monthly_fee_per_rn
                       if result.florence_monthly_fee_per_rn > 0 else 0),
        deal_score=deal_score,
        monthly_florence_fee_account=result.florence_monthly_fee_per_rn * rn_need,
        term_florence_fee_account=result.term_florence_fee_per_rn * rn_need,
        term_net_savings_account=result.term_net_savings_per_rn * rn_need,
    )


# ---------------------------------------------------------------------------
# Core recommend function
# ---------------------------------------------------------------------------

def _price_at_target(
    hospital_row: pd.Series, target_pct: float, base_cal: Calibration, cohort: CohortMix
):
    """Build a Calibration variant + run the pricing engine. Returns (PricingResult, rn_need)."""
    cal = Calibration(
        pricing_mode=base_cal.pricing_mode,
        target_offset_pct=target_pct,
        price_floor_monthly=base_cal.price_floor_monthly,
        price_ceiling_monthly=base_cal.price_ceiling_monthly,
        standard_monthly_fee=base_cal.standard_monthly_fee,
        term_months=base_cal.term_months,
        fica_eligible_months_default=base_cal.fica_eligible_months_default,
        immigration_addon_enabled=base_cal.immigration_addon_enabled,
        amn_partner_markup_pct=base_cal.amn_partner_markup_pct,
        direct_partner_markup_pct=base_cal.direct_partner_markup_pct,
        rn_share_of_contracted_labor=base_cal.rn_share_of_contracted_labor,
        coverage_fill_factor=base_cal.coverage_fill_factor,
        agency_displacement_factor=base_cal.agency_displacement_factor,
        placeholder_msp_markup_pct=base_cal.placeholder_msp_markup_pct,
    )
    # Apply placeholder overlay logic (same as price_batch)
    from system_overlays import placeholder_system_ids
    placeholder_ids = set(placeholder_system_ids(cal.placeholder_msp_markup_pct).keys())
    profile = row_to_profile(hospital_row)
    profile.agency_rate_confidence = float(hospital_row.get("confidence", 0.85) or 0.85)
    profile.agency_rate_source = str(hospital_row.get("data_source", "unspecified"))
    system_id = hospital_row.get("health_system_id", "independent")
    if system_id in placeholder_ids and profile.all_in_agency_per_hour > 0:
        profile.all_in_agency_per_hour *= (1 + cal.placeholder_msp_markup_pct)
    result = price(profile, cohort, cal)

    # RN need (matches pricing_batch._compute_rn_need)
    cl_dollars = hospital_row.get("contract_labor_dollars")
    agency_rate = hospital_row.get("all_in_agency_per_hour")
    if (cl_dollars is not None and pd.notna(cl_dollars) and cl_dollars > 0
            and agency_rate is not None and pd.notna(agency_rate) and agency_rate > 0):
        contracted_hours_per_yr = cl_dollars / agency_rate
        contracted_fte = contracted_hours_per_yr / cal.annual_hours_rn
        rn_need = contracted_fte * cal.rn_share_of_contracted_labor * cal.coverage_fill_factor
    else:
        rn_need = float(hospital_row.get("estimated_rn_need_fte", 0) or 0)
    return result, rn_need, system_id in placeholder_ids


def recommend_pricing(
    hospital_row: pd.Series,
    base_cal: Optional[Calibration] = None,
    cohort: Optional[CohortMix] = None,
    bias_exponent: float = 1.0,
) -> Optional[Recommendation]:
    """Compute the 3-tier negotiation band (Stretch / Target / Reference).

    Logic:
      * Target    = max(fee × deal_score^bias) across TARGET_OFFSET_GRID
      * Stretch   = highest fee at which deal_score ≥ STRETCH_MIN_DEAL_SCORE
                    (fallback to Target if no tier clears threshold)
      * Reference = highest target_offset_pct = lowest fee (best customer-savings pitch)
    """
    base_cal = base_cal or Calibration()
    cohort = cohort or CohortMix(eta=1.0)

    evaluated = []   # list of (target_pct, result, rn_need, deal_score, breakdown, used_placeholder)
    for target in TARGET_OFFSET_GRID:
        result, rn_need, used_placeholder = _price_at_target(
            hospital_row, target, base_cal, cohort
        )
        if not result.feasible or result.florence_monthly_fee_per_rn <= 0:
            continue
        score, breakdown = win_probability(
            fee_monthly=result.florence_monthly_fee_per_rn,
            net_savings_monthly=result.net_monthly_savings_per_rn,
            actual_fica_offset_pct=result.actual_fica_offset_pct,
            cl_intensity=hospital_row.get("contract_labor_intensity"),
            agency_premium_per_hr=result.agency_premium_per_hr,
            confidence=float(hospital_row.get("confidence", 0.85) or 0.85),
        )
        evaluated.append((target, result, rn_need, score, breakdown, used_placeholder))

    if not evaluated:
        return None

    monthly_hours = base_cal.monthly_hours_rn

    # --- Target: max(fee × deal_score^bias) ---
    target_eval = max(
        evaluated,
        key=lambda x: x[1].florence_monthly_fee_per_rn * (x[3] ** bias_exponent),
    )
    target_tier = _tier_from_result(
        "Target", target_eval[0], target_eval[1], target_eval[3],
        target_eval[2], monthly_hours,
    )

    # --- Stretch: highest fee where deal_score ≥ STRETCH_MIN_DEAL_SCORE ---
    closeable = [e for e in evaluated if e[3] >= STRETCH_MIN_DEAL_SCORE]
    if closeable:
        stretch_eval = max(closeable, key=lambda x: x[1].florence_monthly_fee_per_rn)
    else:
        # No tier clears the threshold — fall back to whatever has the highest score
        stretch_eval = max(evaluated, key=lambda x: x[3])
    stretch_tier = _tier_from_result(
        "Stretch", stretch_eval[0], stretch_eval[1], stretch_eval[3],
        stretch_eval[2], monthly_hours,
    )

    # --- Reference: highest target % = lowest fee (max customer savings) ---
    reference_eval = max(evaluated, key=lambda x: x[0])  # highest target_offset_pct
    reference_tier = _tier_from_result(
        "Reference", reference_eval[0], reference_eval[1], reference_eval[3],
        reference_eval[2], monthly_hours,
    )

    rec = Recommendation(
        ccn=str(hospital_row["ccn"]).zfill(6),
        hospital_name=str(hospital_row["name"]),
        recommended_term_months=target_eval[1].term_months,
        rn_need=target_eval[2],
        monthly_hours_rn=monthly_hours,
        stretch=stretch_tier,
        target=target_tier,
        reference=reference_tier,
        signals=target_eval[4],
        primary_state=str(hospital_row.get("state", "")),
        health_system=str(hospital_row.get("health_system", "")),
        health_system_id=str(hospital_row.get("health_system_id", "")),
        city=str(hospital_row.get("city", "")),
    )
    rec.rationale = _rationale_paragraph(rec, sys_overlay_used=target_eval[5])
    return rec


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def _tier_dict(t: PriceTier, prefix: str) -> dict:
    """Flatten a PriceTier into columns prefixed with tier name."""
    return {
        f"{prefix}_target_offset_pct": round(t.target_offset_pct, 4),
        f"{prefix}_monthly_fee": round(t.monthly_fee, 2),
        f"{prefix}_hourly_fee": round(t.hourly_fee, 2),
        f"{prefix}_fica_savings_per_rn_per_month": round(t.fica_savings_per_rn_per_month, 2),
        f"{prefix}_fica_adjusted_effective_cost": round(t.fica_adjusted_effective_cost, 2),
        f"{prefix}_net_monthly_savings_per_rn": round(t.net_monthly_savings_per_rn, 2),
        f"{prefix}_savings_ratio": round(t.savings_ratio, 2),
        f"{prefix}_deal_score": round(t.deal_score, 4),
        f"{prefix}_monthly_florence_fee_account": round(t.monthly_florence_fee_account, 2),
        f"{prefix}_term_florence_fee_account": round(t.term_florence_fee_account, 2),
        f"{prefix}_term_net_savings_account": round(t.term_net_savings_account, 2),
    }


def batch_recommend(
    universe: pd.DataFrame,
    base_cal: Optional[Calibration] = None,
    cohort: Optional[CohortMix] = None,
    bias_exponent: float = 1.0,
) -> pd.DataFrame:
    """Pre-compute 3-tier recommendations for every hospital."""
    base_cal = base_cal or Calibration()
    cohort = cohort or CohortMix(eta=1.0)
    rows = []
    for _, h in universe.iterrows():
        try:
            rec = recommend_pricing(h, base_cal, cohort, bias_exponent)
            if rec is None:
                rows.append({"ccn": str(h["ccn"]).zfill(6), "feasible": False,
                             "reason": "manual_review_or_infeasible"})
                continue
            row = {
                "ccn": rec.ccn,
                "name": rec.hospital_name,
                "city": rec.city,
                "state": rec.primary_state,
                "health_system": rec.health_system,
                "health_system_id": rec.health_system_id,
                "feasible": True,
                "recommended_term_months": rec.recommended_term_months,
                "rn_need": round(rec.rn_need, 2),
                "monthly_hours_rn": rec.monthly_hours_rn,
                "rationale": rec.rationale,
                # Signal raw values
                "signal_savings_ratio": round(rec.signals.savings_ratio_raw, 2),
                "signal_cl_intensity": round(rec.signals.cl_intensity_raw, 4),
                "signal_fica_offset_pct": round(rec.signals.fica_offset_raw, 4),
                "signal_agency_premium": round(rec.signals.premium_raw, 2),
                "signal_data_confidence": round(rec.signals.confidence_raw, 2),
            }
            row.update(_tier_dict(rec.stretch, "stretch"))
            row.update(_tier_dict(rec.target, "target"))
            row.update(_tier_dict(rec.reference, "reference"))
            rows.append(row)
        except Exception as e:
            rows.append({"ccn": str(h["ccn"]).zfill(6), "feasible": False, "reason": str(e)})
    return pd.DataFrame(rows)


def main() -> None:
    from pathlib import Path
    from pricing_batch import load_universe

    print("Pre-computing 3-tier recommendations for the full universe...")
    u = load_universe()
    df = batch_recommend(u)
    feas = df[df["feasible"]]
    print(f"  Total hospitals: {len(df):,}")
    print(f"  Quotable with recommendation: {len(feas):,}")
    print()
    print(f"Distribution by target tier:")
    print(feas["target_target_offset_pct"].value_counts().sort_index().to_string())
    print()
    print(f"Stretch-tier vs Target vs Reference (medians):")
    print(f"  Stretch fee:   ${feas['stretch_monthly_fee'].median():,.0f}/RN/mo  "
          f"(deal score {feas['stretch_deal_score'].median()*100:.0f}/100, "
          f"savings ratio {feas['stretch_savings_ratio'].median():.1f}×)")
    print(f"  Target fee:    ${feas['target_monthly_fee'].median():,.0f}/RN/mo  "
          f"(deal score {feas['target_deal_score'].median()*100:.0f}/100, "
          f"savings ratio {feas['target_savings_ratio'].median():.1f}×)")
    print(f"  Reference fee: ${feas['reference_monthly_fee'].median():,.0f}/RN/mo  "
          f"(deal score {feas['reference_deal_score'].median()*100:.0f}/100, "
          f"savings ratio {feas['reference_savings_ratio'].median():.1f}×)")
    print()
    print(f"Aggregate monthly Florence revenue across tiers:")
    print(f"  Stretch:   ${feas['stretch_monthly_florence_fee_account'].sum()/1e6:,.0f}M/mo")
    print(f"  Target:    ${feas['target_monthly_florence_fee_account'].sum()/1e6:,.0f}M/mo")
    print(f"  Reference: ${feas['reference_monthly_florence_fee_account'].sum()/1e6:,.0f}M/mo")

    out = Path("data/recommendations.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
