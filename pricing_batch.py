"""
Batch pricing + calibration-sweep layer on top of pricing_engine.

Used by the Streamlit app and any CLI / notebook analysis.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from pricing_engine import (
    Calibration,
    Channel,
    CohortMix,
    HospitalProfile,
    PricingResult,
    price,
)

DATA_DIR = Path(__file__).parent / "data"
UNIVERSE_CSV = DATA_DIR / "hospital_universe.csv"


# ---------------------------------------------------------------------------
# Universe loading
# ---------------------------------------------------------------------------

def load_universe(path: Path = UNIVERSE_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ccn": str, "zip": str})
    return df


def row_to_profile(row: pd.Series) -> HospitalProfile:
    return HospitalProfile(
        name=row["name"],
        city=row["city"],
        state=row["state"],
        role="RN — Med/Surg",
        taxable_wage_per_hour=float(row["taxable_wage_per_hour"]),
        benefit_load_per_hour=float(row["benefit_load_per_hour"]),
        all_in_agency_per_hour=float(row["all_in_agency_per_hour"]),
        notes=str(row.get("data_source", "")),
    )


# ---------------------------------------------------------------------------
# Batch pricing
# ---------------------------------------------------------------------------

def _compute_rn_need(h: pd.Series, cal: Calibration) -> float:
    """RN need per Florence product plan §Core Pricing Model:
    RN Need = Contracted Labor FTE × RN_share × coverage_factor

    Where Contracted Labor FTE is derived from HCRIS contract-labor dollars
    divided by the agency rate, when both are available. Falls back to
    estimated_rn_need_fte (HCRIS total FTE × 0.27) only when no contract-labor
    signal exists.
    """
    cl_dollars = h.get("contract_labor_dollars")
    agency_rate = h.get("all_in_agency_per_hour")
    if (
        cl_dollars is not None and pd.notna(cl_dollars) and cl_dollars > 0
        and agency_rate is not None and pd.notna(agency_rate) and agency_rate > 0
    ):
        contracted_hours_per_yr = cl_dollars / agency_rate
        contracted_fte = contracted_hours_per_yr / cal.annual_hours_rn
        return contracted_fte * cal.rn_share_of_contracted_labor * cal.coverage_fill_factor
    # Fallback only — no contracted-labor signal
    return float(h.get("estimated_rn_need_fte", 0) or 0)


def price_batch(
    universe: pd.DataFrame,
    cohort: CohortMix,
    calibration: Calibration | None = None,
) -> pd.DataFrame:
    """
    Run pricing engine over every hospital in the universe. Returns one row
    per hospital with market inputs, pricing decision, fees, manual-review
    flag, and aggregated account-level revenue/savings figures.

    Placeholder MSP overlay (v2 §5.2) — applied at PRICING TIME (not universe
    build) so the Streamlit slider can adjust it live without rebuilds.
    Hospitals in placeholder-eligible systems get their agency rate bumped
    by cal.placeholder_msp_markup_pct × base_agency_rate.
    """
    from system_overlays import placeholder_system_ids
    cal = calibration or Calibration()

    # Lookup table of placeholder-eligible health_system_ids
    placeholder_ids = set(placeholder_system_ids(cal.placeholder_msp_markup_pct).keys())

    out_rows = []
    for _, h in universe.iterrows():
        try:
            profile = row_to_profile(h)
            # Attach data provenance for manual-review decision
            profile.agency_rate_confidence = float(h.get("confidence", 0.85) or 0.85)
            profile.agency_rate_source = str(h.get("data_source", "unspecified"))

            # Apply placeholder MSP overlay if this hospital is in a placeholder system
            placeholder_overlay_per_hr = 0.0
            system_id = h.get("health_system_id", "independent")
            if system_id in placeholder_ids and profile.all_in_agency_per_hour > 0:
                placeholder_overlay_per_hr = (
                    profile.all_in_agency_per_hour * cal.placeholder_msp_markup_pct
                )
                profile.all_in_agency_per_hour += placeholder_overlay_per_hr

            r = price(profile, cohort, cal, system_id=system_id)

            # Product-plan RN need (contracted-labor-based)
            rn_need = _compute_rn_need(h, cal)

            out_rows.append({
                "ccn": h["ccn"],
                "name": h["name"],
                "city": h["city"],
                "state": h["state"],
                "county": h.get("county", ""),
                "hospital_type": h.get("hospital_type", ""),
                "ownership": h.get("ownership", ""),
                "data_source": h.get("data_source", ""),
                "confidence": h.get("confidence", 0.0),

                # RN need (product plan formula) + fallback
                "rn_need": round(rn_need, 1),
                "rn_need_fallback_fte": float(h.get("estimated_rn_need_fte", 0) or 0),

                # Geocode + system + CBSA
                "lat": h.get("lat"),
                "lon": h.get("lon"),
                "health_system": h.get("health_system") or "Independent / Unknown",
                "health_system_id": h.get("health_system_id") or "independent",
                "cbsa_code": h.get("cbsa_code"),
                "cbsa_title": h.get("cbsa_title"),
                "rural_flag": h.get("rural_flag"),

                # Wage source + MSP overlay provenance
                "wage_source": h.get("wage_source"),
                "wage_confidence": h.get("wage_confidence"),
                "msp_overlay_per_hour": h.get("msp_overlay_per_hour", 0),  # universe-time (Kaiser)
                "msp_overlay_source": h.get("msp_overlay_source", ""),
                "all_in_agency_per_hour_pre_overlay": h.get("all_in_agency_per_hour_pre_overlay"),

                # Placeholder overlay (applied at pricing time, controlled by slider)
                "placeholder_msp_overlay_per_hour": round(placeholder_overlay_per_hr, 2),
                "placeholder_msp_markup_pct_used": cal.placeholder_msp_markup_pct
                    if system_id in placeholder_ids else 0.0,
                "is_placeholder_system": system_id in placeholder_ids,

                # HCRIS-derived signals (pass through)
                "contract_labor_dollars": h.get("contract_labor_dollars"),
                "contract_labor_intensity": h.get("contract_labor_intensity"),
                "operating_margin": h.get("operating_margin"),
                "hcris_total_fte": h.get("hcris_total_fte"),

                # Inputs
                "loaded_staff_cost_per_hr": r.loaded_staff_cost_per_hr,
                "all_in_agency_per_hr": (
                    r.loaded_staff_cost_per_hr + r.agency_premium_per_hr
                ),
                "agency_premium_per_hr": r.agency_premium_per_hr,
                "employer_fica_per_hr": r.employer_fica_per_hr,

                # Pricing decision (v2)
                "pricing_mode": r.pricing_mode,
                "suggested_fee_pre_guardrails": r.suggested_fee_pre_guardrails,
                "final_fee_constrained_by": r.final_fee_constrained_by,
                "target_offset_pct": r.target_offset_pct,
                "price_floor_monthly": r.price_floor_monthly,
                "price_ceiling_monthly": r.price_ceiling_monthly,
                "feasible": r.feasible,
                "channel": r.channel.value,
                "manual_review_flag": r.manual_review_flag,
                "manual_review_reason": r.manual_review_reason,

                # --- v2 FIVE PRIMARY BUYER-FACING NUMBERS (per RN per month) ---
                "florence_monthly_fee_per_rn": r.florence_monthly_fee_per_rn,
                "employer_fica_savings_per_rn_per_month": r.employer_fica_savings_per_rn_per_month,
                "fica_adjusted_effective_cost_per_rn_month": r.fica_adjusted_effective_cost_per_rn_month,
                "actual_fica_offset_pct": r.actual_fica_offset_pct,
                "net_monthly_savings_per_rn": r.net_monthly_savings_per_rn,

                # Immigration add-on
                "immigration_addon_monthly": r.immigration_addon_monthly,
                "all_in_florence_fee_per_rn_month": r.all_in_florence_fee_per_rn_month,
                "all_in_fica_adjusted_cost_per_rn_month": r.all_in_fica_adjusted_cost_per_rn_month,

                # Agency premium economics
                "monthly_agency_premium_avoided_per_rn": r.monthly_agency_premium_avoided_per_rn,

                # Term totals (per RN)
                "term_florence_fee_per_rn": r.term_florence_fee_per_rn,
                "term_employer_fica_offset_per_rn": r.term_employer_fica_offset_per_rn,
                "term_effective_cost_per_rn": r.term_effective_cost_per_rn,
                "term_gross_agency_savings_per_rn": r.term_gross_agency_savings_per_rn,
                "term_net_savings_per_rn": r.term_net_savings_per_rn,

                # Term length
                "term_months": r.term_months,
                "monthly_hours_rn": r.monthly_hours_rn,

                # Revenue split
                "partner_share": r.partner_share,
                "partner_revenue_monthly_per_rn": r.partner_revenue_monthly,
                "florence_net_monthly_per_rn": r.florence_net_monthly,
                "florence_net_term_per_rn": r.florence_net_term,

                # ---- Account-level aggregates (at RN need) ----
                # Monthly aggregates
                "monthly_florence_fee_account": (
                    r.florence_monthly_fee_per_rn * rn_need if r.feasible else 0.0
                ),
                "monthly_fica_offset_account": (
                    r.employer_fica_savings_per_rn_per_month * rn_need if r.feasible else 0.0
                ),
                "monthly_effective_cost_account": (
                    r.fica_adjusted_effective_cost_per_rn_month * rn_need if r.feasible else 0.0
                ),
                "monthly_agency_avoided_account": (
                    r.monthly_agency_premium_avoided_per_rn * rn_need if r.feasible else 0.0
                ),
                "monthly_net_savings_account": (
                    r.net_monthly_savings_per_rn * rn_need if r.feasible else 0.0
                ),
                # Term aggregates
                "term_florence_fee_account": (
                    r.term_florence_fee_per_rn * rn_need if r.feasible else 0.0
                ),
                "term_fica_offset_account": (
                    r.term_employer_fica_offset_per_rn * rn_need if r.feasible else 0.0
                ),
                "term_net_savings_account": (
                    r.term_net_savings_per_rn * rn_need if r.feasible else 0.0
                ),
                "term_gross_agency_savings_account": (
                    r.term_gross_agency_savings_per_rn * rn_need if r.feasible else 0.0
                ),
                "florence_net_term_account": (
                    r.florence_net_term * rn_need if r.feasible else 0.0
                ),
                "partner_revenue_term_account": (
                    r.partner_revenue_monthly * cal.term_months * rn_need
                    if r.feasible else 0.0
                ),

                # ---- Legacy aliases (existing app code) ----
                "premium_capture_rate": r.premium_capture_rate,
                "delta_chosen": r.delta_chosen,
                "f_total": r.f_total,
                "monthly_fee_per_nurse": r.florence_monthly_fee_per_rn,
                "florence_net_per_nurse": r.florence_net_term,
                "partner_revenue_per_nurse": r.partner_revenue_monthly * cal.term_months,
                "hospital_premium_per_hr": r.hospital_premium_per_hr,
                "gross_agency_savings_per_nurse": r.term_gross_agency_savings_per_rn,
                "net_savings_per_nurse": r.term_net_savings_per_rn,
                "net_savings_per_hr": r.net_savings_per_hr,
                "total_florence_fee": (r.term_florence_fee_per_rn * rn_need if r.feasible else 0.0),
                "monthly_florence_fee": (r.florence_monthly_fee_per_rn * rn_need if r.feasible else 0.0),
                "florence_net_total": (r.florence_net_term * rn_need if r.feasible else 0.0),
                "partner_revenue_total": (
                    r.partner_revenue_monthly * cal.term_months * rn_need if r.feasible else 0.0
                ),
                "gross_agency_savings_total": (
                    r.term_gross_agency_savings_per_rn * rn_need if r.feasible else 0.0
                ),
                "net_savings_total": (r.term_net_savings_per_rn * rn_need if r.feasible else 0.0),
                "cohort_eta": cohort.eta,
                "calibration_version": cal.version,
            })
        except Exception as e:
            out_rows.append({
                "ccn": h["ccn"], "name": h["name"], "state": h["state"],
                "error": str(e),
            })
    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# Calibration sweep — what δ, ζ, η produces what total addressable revenue?
# ---------------------------------------------------------------------------

def calibration_sweep(
    universe: pd.DataFrame,
    target_offset_pcts: Iterable[float] = (0.25, 0.33, 0.40, 0.50, 0.60, 0.75, 1.0),
    etas: Iterable[float] = (0.0, 0.5, 1.0),
) -> pd.DataFrame:
    """
    Sweep across target_offset_pct (v2 FICA-offset target) × η (cohort eligibility).
    Returns aggregates at each combination per Florence Methodology v2.
    """
    from pricing_engine import PricingMode
    rows = []
    for eta in etas:
        cohort = CohortMix(eta=eta)
        for target in target_offset_pcts:
            cal = Calibration(
                pricing_mode=PricingMode.FICA_OFFSET_TARGET,
                target_offset_pct=target,
            )
            priced = price_batch(universe, cohort, cal)
            feas = priced[priced["feasible"]]
            rows.append({
                "target_offset_pct": target,
                "eta": eta,
                "hospitals_total": len(priced),
                "hospitals_feasible": len(feas),
                "feasibility_rate": len(feas) / len(priced) if len(priced) else 0,
                "manual_review_count": int(priced["manual_review_flag"].sum()),
                "addressable_rn_need": feas["rn_need"].sum(),
                "median_monthly_fee_per_rn": feas["florence_monthly_fee_per_rn"].median() if len(feas) else 0,
                "median_fica_savings_per_rn": feas["employer_fica_savings_per_rn_per_month"].median() if len(feas) else 0,
                "median_effective_cost_per_rn": feas["fica_adjusted_effective_cost_per_rn_month"].median() if len(feas) else 0,
                "median_actual_offset_pct": feas["actual_fica_offset_pct"].median() if len(feas) else 0,
                "median_net_savings_per_rn_month": feas["net_monthly_savings_per_rn"].median() if len(feas) else 0,
                "total_monthly_florence_fee": feas["monthly_florence_fee_account"].sum(),
                "total_monthly_fica_offset": feas["monthly_fica_offset_account"].sum(),
                "total_monthly_net_savings": feas["monthly_net_savings_account"].sum(),
                "total_term_florence_fee": feas["term_florence_fee_account"].sum(),
                "total_term_florence_net": feas["florence_net_term_account"].sum(),
                "total_term_partner_revenue": feas["partner_revenue_term_account"].sum(),
                "total_term_net_savings": feas["term_net_savings_account"].sum(),
                "constrained_floor": int((priced["final_fee_constrained_by"] == "floor").sum()),
                "constrained_target": int((priced["final_fee_constrained_by"] == "target").sum()),
                "constrained_ceiling": int((priced["final_fee_constrained_by"] == "ceiling").sum()),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Market aggregation — roll up by state / ownership / health system
# ---------------------------------------------------------------------------

def market_aggregate(priced: pd.DataFrame, group_by: str = "state") -> pd.DataFrame:
    """Roll up per Florence Methodology v2 §7 — additive sums only, no simple averages."""
    feas = priced[priced["feasible"]].copy()
    g = priced.groupby(group_by)

    agg = pd.DataFrame({
        "hospitals_total": g.size(),
        "median_loaded_staff_cost": g["loaded_staff_cost_per_hr"].median(),
        "median_agency_rate": g["all_in_agency_per_hr"].median(),
        "median_agency_premium": g["agency_premium_per_hr"].median(),
        "median_confidence": g["confidence"].median(),
        "manual_review_count": g["manual_review_flag"].sum(),
    })
    fg = feas.groupby(group_by)
    agg["hospitals_feasible"] = fg.size().reindex(agg.index).fillna(0).astype(int)
    agg["feasibility_rate"] = agg["hospitals_feasible"] / agg["hospitals_total"]
    agg["total_rn_need"] = fg["rn_need"].sum().reindex(agg.index).fillna(0)

    # v2 primary numbers — monthly aggregates (additive)
    agg["monthly_florence_fee"] = (
        fg["monthly_florence_fee_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["monthly_fica_offset"] = (
        fg["monthly_fica_offset_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["monthly_effective_cost"] = (
        fg["monthly_effective_cost_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["monthly_agency_premium_avoided"] = (
        fg["monthly_agency_avoided_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["monthly_net_savings"] = (
        fg["monthly_net_savings_account"].sum().reindex(agg.index).fillna(0)
    )

    # Term aggregates
    agg["term_florence_fee"] = (
        fg["term_florence_fee_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["term_fica_offset"] = (
        fg["term_fica_offset_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["term_florence_net"] = (
        fg["florence_net_term_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["term_partner_revenue"] = (
        fg["partner_revenue_term_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["term_gross_agency_savings"] = (
        fg["term_gross_agency_savings_account"].sum().reindex(agg.index).fillna(0)
    )
    agg["term_net_savings"] = (
        fg["term_net_savings_account"].sum().reindex(agg.index).fillna(0)
    )

    # Portfolio Florence fee per RN per month (per v2 §7 rule: sum(fee) / sum(RN need))
    agg["portfolio_florence_monthly_fee_per_rn"] = (
        agg["monthly_florence_fee"] / agg["total_rn_need"]
    ).replace([float('inf'), -float('inf')], 0).fillna(0)
    agg["portfolio_actual_offset_pct"] = (
        agg["monthly_fica_offset"] / agg["monthly_florence_fee"]
    ).replace([float('inf'), -float('inf')], 0).fillna(0)

    # Legacy aliases for existing app code
    agg["total_florence_fee"] = agg["term_florence_fee"]
    agg["total_monthly_florence_fee"] = agg["monthly_florence_fee"]
    agg["total_florence_net"] = agg["term_florence_net"]
    agg["total_partner_revenue"] = agg["term_partner_revenue"]
    agg["total_net_savings"] = agg["term_net_savings"]
    agg["median_fee_per_nurse"] = (
        fg["term_florence_fee_per_rn"].median().reindex(agg.index).fillna(0)
    )
    agg["median_monthly_fee_per_nurse"] = (
        fg["florence_monthly_fee_per_rn"].median().reindex(agg.index).fillna(0)
    )

    agg = agg.reset_index().sort_values("term_florence_net", ascending=False)
    return agg


# ---------------------------------------------------------------------------
# CLI entry point for quick verification
# ---------------------------------------------------------------------------

def main() -> None:
    universe = load_universe()
    print(f"Universe: {len(universe):,} hospitals\n")

    cal = Calibration()  # v2 default: FICA_OFFSET_TARGET, 50% target, $1500-$2000
    cohort = CohortMix(eta=1.0)  # F-1 cohort (Florence's confirmed pipeline)
    print(f"Running batch pricing at v2 defaults "
          f"(mode={cal.pricing_mode.value}, target={cal.target_offset_pct:.0%}, "
          f"floor=${cal.price_floor_monthly:.0f}, ceiling=${cal.price_ceiling_monthly:.0f}, "
          f"term={cal.term_months}mo, η=1.0)...")
    priced = price_batch(universe, cohort, cal)
    feas = priced[priced["feasible"]]
    print(f"  Feasible:                          {len(feas):,} / {len(priced):,}")
    print(f"  Manual review flagged:             {priced['manual_review_flag'].sum():,}")
    print(f"  Total RN need:                     {feas['rn_need'].sum():,.0f} FTE")
    print()
    print(f"  Median monthly fee per RN:         ${feas['florence_monthly_fee_per_rn'].median():,.2f}")
    print(f"  Median FICA savings per RN:        ${feas['employer_fica_savings_per_rn_per_month'].median():,.2f}")
    print(f"  Median effective cost per RN:      ${feas['fica_adjusted_effective_cost_per_rn_month'].median():,.2f}")
    print(f"  Median actual FICA offset %:       {feas['actual_fica_offset_pct'].median():.1%}")
    print(f"  Median net monthly savings/RN:     ${feas['net_monthly_savings_per_rn'].median():,.2f}")
    print()
    print(f"  Constrained-by distribution:")
    for k, n in priced['final_fee_constrained_by'].value_counts().items():
        print(f"    {k:>15}  {n:>5}")
    print()
    print(f"  Total monthly Florence billings:   ${feas['monthly_florence_fee_account'].sum()/1e6:,.1f}M/mo")
    print(f"  Total monthly FICA offset:         ${feas['monthly_fica_offset_account'].sum()/1e6:,.1f}M/mo")
    print(f"  Total monthly net savings:         ${feas['monthly_net_savings_account'].sum()/1e6:,.1f}M/mo")
    print(f"  Term ({cal.term_months}-mo) Florence fee:        ${feas['term_florence_fee_account'].sum()/1e9:.2f}B")
    print(f"  Term net savings (after fee):      ${feas['term_net_savings_account'].sum()/1e9:.2f}B")

    print("\nTop 10 states by term Florence net revenue:")
    top = market_aggregate(priced, "state").head(10)
    cols = ["state", "hospitals_total", "hospitals_feasible",
            "median_agency_premium", "median_monthly_fee_per_nurse",
            "total_rn_need", "term_florence_net", "term_net_savings"]
    print(top[cols].to_string(index=False))


if __name__ == "__main__":
    main()
