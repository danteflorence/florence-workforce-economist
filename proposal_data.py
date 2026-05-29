"""
Proposal-data assembly layer.

Takes a target (single hospital, or a health system) and produces a
structured ProposalData object containing every slide-ready data point a
PPTX / HTML / PDF renderer would need.

Separated from the renderers so the data is computed once and rendered
in multiple formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from pricing_batch import load_universe, price_batch, row_to_profile
from pricing_engine import (
    Calibration,
    Channel,
    CohortMix,
    PricingResult,
    price,
)


# ---------------------------------------------------------------------------
# Structured data objects — one per slide section
# ---------------------------------------------------------------------------

@dataclass
class CoverSlide:
    target_name: str                       # "Kaiser Permanente" or "Mercy General Hospital"
    target_type: str                       # "Health System" or "Hospital"
    subtitle: str                          # location summary or tagline
    generated_date: str
    calibration_version: str


@dataclass
class ExecutiveSummary:
    """The one-page financial picture for all parties."""
    n_hospitals: int
    n_feasible: int
    total_rn_need_fte: float
    median_loaded_staff_per_hr: float
    median_agency_per_hr: float
    median_agency_premium_per_hr: float
    median_florence_fee: float

    gross_revenue_total: float             # what hospitals pay (per nurse × FTE)
    hospital_savings_total: float          # vs all-in agency
    partner_revenue_total: float           # to channel partner (AMN etc.)
    florence_net_total: float              # net to Florence

    headline_one_liner: str                # for the deck headline


@dataclass
class PricingMethodology:
    """The 'how' slide — explains the market-sensitive math."""
    alpha: float
    zeta: float
    delta_floor: float
    delta_cap: float
    commitment_years: int
    annual_hours: int
    cohort_eta: float
    partner_share_direct: float
    partner_share_amn: float
    formula_text: str                      # human-readable formula description


@dataclass
class HospitalRow:
    """One row in the per-hospital pricing table."""
    name: str
    city: str
    state: str
    rn_need_fte: float
    loaded_staff_per_hr: float
    agency_per_hr: float
    delta_per_hr: float
    fee_per_nurse: float
    florence_net_per_nurse: float
    partner_per_nurse: float
    hospital_save_per_hr: float
    contract_labor_share: Optional[float]
    operating_margin: Optional[float]
    channel: str
    feasible: bool


@dataclass
class MarketContext:
    """Demographics / supply-side context for the target market(s)."""
    states_covered: list[str]
    msa_summary: str
    median_contract_labor_share: float
    n_hospitals_high_cl: int               # CL share ≥ 15%
    aggregate_total_fte: float             # all-workforce FTE


@dataclass
class TaxAssumption:
    """Boilerplate FICA / visa disclaimer block."""
    text: str = (
        "FICA capture under IRC §3121(b)(19) applies only to F-1, J-1, M-1, "
        "Q-1, and Q-2 nonresident aliens during their nonresident-alien tax "
        "period. EB-3 / H-1B / TN / U.S. citizen placements carry no FICA "
        "component (η = 0). Florence does not provide tax, payroll, "
        "immigration, or legal advice. The hospital's tax, payroll, "
        "immigration, and legal teams must independently verify visa status, "
        "work authorization, tax residency, and per-placement applicability "
        "before relying on the projected FICA component of this pricing."
    )


@dataclass
class ProposalData:
    cover: CoverSlide
    executive_summary: ExecutiveSummary
    methodology: PricingMethodology
    hospitals: list[HospitalRow]
    market_context: MarketContext
    tax_assumption: TaxAssumption
    raw_pricing_df: pd.DataFrame           # carried for renderers that want extras


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _format_states_summary(states: list[str]) -> str:
    if not states:
        return "—"
    if len(states) <= 4:
        return ", ".join(sorted(states))
    return ", ".join(sorted(states)[:4]) + f" + {len(states) - 4} more"


def _format_headline(target_name: str, florence_net: float, hospital_save: float,
                     n_hospitals: int) -> str:
    if n_hospitals == 1:
        return (
            f"Florence pricing for {target_name}: "
            f"${florence_net:,.0f} Florence revenue, "
            f"${hospital_save:,.0f} hospital savings vs agency labor."
        )
    return (
        f"Florence pricing for {target_name}: ${florence_net/1e6:.1f}M Florence "
        f"revenue across {n_hospitals} hospitals, ${hospital_save/1e6:.0f}M in "
        "hospital savings vs all-in agency labor."
    )


def build_hospital_proposal(
    ccn: str,
    calibration: Calibration | None = None,
    cohort: CohortMix | None = None,
) -> ProposalData:
    """Build proposal data for a single hospital (by CCN)."""
    cal = calibration or Calibration()
    coh = cohort or CohortMix(eta=0.0)
    universe = load_universe()
    universe["ccn"] = universe["ccn"].astype(str).str.zfill(6)
    ccn = str(ccn).zfill(6)

    hospital_row = universe[universe["ccn"] == ccn]
    if hospital_row.empty:
        raise ValueError(f"Hospital CCN {ccn} not found in universe.")
    h = hospital_row.iloc[0]

    result = price(row_to_profile(h), coh, cal)
    rn_need = float(h.get("estimated_rn_need_fte", 0) or 0)

    cover = CoverSlide(
        target_name=h["name"],
        target_type="Hospital",
        subtitle=f"{h['city']}, {h['state']} · CCN {ccn} · "
                 f"{h.get('health_system', 'Independent')}",
        generated_date=date.today().isoformat(),
        calibration_version=result.calibration_version,
    )

    gross = result.f_total * rn_need
    fl_net = result.florence_net_revenue * rn_need
    ptr = result.partner_revenue * rn_need
    save = result.savings_vs_agency * rn_need

    exec_summary = ExecutiveSummary(
        n_hospitals=1,
        n_feasible=1 if result.feasible else 0,
        total_rn_need_fte=rn_need,
        median_loaded_staff_per_hr=result.loaded_staff_cost_per_hr,
        median_agency_per_hr=result.loaded_staff_cost_per_hr + result.agency_premium_per_hr,
        median_agency_premium_per_hr=result.agency_premium_per_hr,
        median_florence_fee=result.f_total,
        gross_revenue_total=gross,
        hospital_savings_total=save,
        partner_revenue_total=ptr,
        florence_net_total=fl_net,
        headline_one_liner=_format_headline(h["name"], fl_net, save, 1),
    )

    methodology = PricingMethodology(
        alpha=cal.alpha,
        zeta=cal.zeta,
        delta_floor=cal.delta_floor,
        delta_cap=cal.delta_cap,
        commitment_years=cal.commitment_years,
        annual_hours=cal.annual_hours,
        cohort_eta=coh.eta,
        partner_share_direct=cal.direct_partner_share,
        partner_share_amn=cal.amn_partner_share,
        formula_text=(
            f"δ_per_hospital = clamp(α × (M − ζ), δ_floor, δ_cap), where M is the "
            f"local agency premium and α={cal.alpha:.2f} is Florence's share. "
            f"Hospital captures (1 − α) of the premium."
        ),
    )

    hospitals = [HospitalRow(
        name=h["name"], city=h["city"], state=h["state"],
        rn_need_fte=rn_need,
        loaded_staff_per_hr=result.loaded_staff_cost_per_hr,
        agency_per_hr=result.loaded_staff_cost_per_hr + result.agency_premium_per_hr,
        delta_per_hr=result.delta_chosen,
        fee_per_nurse=result.f_total,
        florence_net_per_nurse=result.florence_net_revenue,
        partner_per_nurse=result.partner_revenue,
        hospital_save_per_hr=result.savings_vs_agency_per_hr,
        contract_labor_share=h.get("contract_labor_intensity"),
        operating_margin=h.get("operating_margin"),
        channel=result.channel.value,
        feasible=result.feasible,
    )]

    market_context = MarketContext(
        states_covered=[h["state"]],
        msa_summary=f"{h['city']}, {h['state']}",
        median_contract_labor_share=h.get("contract_labor_intensity") or 0.0,
        n_hospitals_high_cl=(
            1 if h.get("contract_labor_intensity") and h["contract_labor_intensity"] >= 0.15
            else 0
        ),
        aggregate_total_fte=h.get("hcris_total_fte") or 0.0,
    )

    raw_df = price_batch(universe[universe["ccn"] == ccn], coh, cal)

    return ProposalData(
        cover=cover,
        executive_summary=exec_summary,
        methodology=methodology,
        hospitals=hospitals,
        market_context=market_context,
        tax_assumption=TaxAssumption(),
        raw_pricing_df=raw_df,
    )


def build_system_proposal(
    health_system: str,
    calibration: Calibration | None = None,
    cohort: CohortMix | None = None,
    max_hospitals_in_table: int = 50,
) -> ProposalData:
    """Build proposal data for a parent health system (all owned hospitals)."""
    cal = calibration or Calibration()
    coh = cohort or CohortMix(eta=0.0)
    universe = load_universe()

    sys_universe = universe[universe["health_system"] == health_system]
    if sys_universe.empty:
        raise ValueError(f"Health system '{health_system}' not found in universe.")

    priced = price_batch(sys_universe, coh, cal)
    feas = priced[priced["feasible"]]

    states = sorted(sys_universe["state"].unique().tolist())

    cover = CoverSlide(
        target_name=health_system,
        target_type="Health System",
        subtitle=(
            f"{len(sys_universe)} hospitals across {len(states)} states · "
            f"{_format_states_summary(states)}"
        ),
        generated_date=date.today().isoformat(),
        calibration_version=cal.version,
    )

    total_rn_need = sys_universe["estimated_rn_need_fte"].sum()
    gross = feas["gross_revenue_at_rn_need"].sum()
    fl_net = feas["florence_net_at_rn_need"].sum()
    ptr = feas["partner_revenue_at_rn_need"].sum()
    save = feas["hospital_savings_at_rn_need"].sum()

    exec_summary = ExecutiveSummary(
        n_hospitals=len(sys_universe),
        n_feasible=len(feas),
        total_rn_need_fte=total_rn_need,
        median_loaded_staff_per_hr=priced["loaded_staff_cost_per_hr"].median(),
        median_agency_per_hr=priced["all_in_agency_per_hr"].median(),
        median_agency_premium_per_hr=priced["agency_premium_per_hr"].median(),
        median_florence_fee=feas["f_total"].median() if len(feas) else 0,
        gross_revenue_total=gross,
        hospital_savings_total=save,
        partner_revenue_total=ptr,
        florence_net_total=fl_net,
        headline_one_liner=_format_headline(health_system, fl_net, save, len(sys_universe)),
    )

    methodology = PricingMethodology(
        alpha=cal.alpha,
        zeta=cal.zeta,
        delta_floor=cal.delta_floor,
        delta_cap=cal.delta_cap,
        commitment_years=cal.commitment_years,
        annual_hours=cal.annual_hours,
        cohort_eta=coh.eta,
        partner_share_direct=cal.direct_partner_share,
        partner_share_amn=cal.amn_partner_share,
        formula_text=(
            f"δ_per_hospital = clamp(α × (M − ζ), δ_floor, δ_cap). "
            f"α={cal.alpha:.2f}, ζ=${cal.zeta:.2f}/hr. Each hospital in the system "
            "gets a price reflecting its local agency premium."
        ),
    )

    # Per-hospital table (sorted by Florence net, capped at max_hospitals_in_table)
    sorted_h = priced.sort_values("florence_net_at_rn_need", ascending=False)
    hospitals = []
    for _, h in sorted_h.head(max_hospitals_in_table).iterrows():
        hospitals.append(HospitalRow(
            name=h["name"], city=h["city"], state=h["state"],
            rn_need_fte=float(h["estimated_rn_need_fte"] or 0),
            loaded_staff_per_hr=h["loaded_staff_cost_per_hr"],
            agency_per_hr=h["all_in_agency_per_hr"],
            delta_per_hr=h["delta_chosen"],
            fee_per_nurse=h["f_total"],
            florence_net_per_nurse=h["florence_net_per_nurse"],
            partner_per_nurse=h["partner_revenue_per_nurse"],
            hospital_save_per_hr=h["savings_vs_agency_per_hr"],
            contract_labor_share=h.get("contract_labor_intensity"),
            operating_margin=h.get("operating_margin"),
            channel=h["channel"],
            feasible=bool(h["feasible"]),
        ))

    cl_intensity_series = sys_universe["contract_labor_intensity"].dropna()
    market_context = MarketContext(
        states_covered=states,
        msa_summary=f"{len(sys_universe)} hospitals in {len(states)} states",
        median_contract_labor_share=(
            float(cl_intensity_series.median()) if len(cl_intensity_series) else 0.0
        ),
        n_hospitals_high_cl=int((cl_intensity_series >= 0.15).sum()),
        aggregate_total_fte=float(sys_universe["hcris_total_fte"].sum()),
    )

    return ProposalData(
        cover=cover,
        executive_summary=exec_summary,
        methodology=methodology,
        hospitals=hospitals,
        market_context=market_context,
        tax_assumption=TaxAssumption(),
        raw_pricing_df=priced,
    )


# ---------------------------------------------------------------------------
# Quick-look text summary (for the Streamlit preview pane and unit tests)
# ---------------------------------------------------------------------------

def render_text_summary(data: ProposalData) -> str:
    es = data.executive_summary
    lines = [
        f"═══ PROPOSAL — {data.cover.target_name} ({data.cover.target_type}) ═══",
        data.cover.subtitle,
        f"Generated {data.cover.generated_date} · {data.cover.calibration_version}",
        "",
        "EXECUTIVE SUMMARY",
        f"  {es.headline_one_liner}",
        "",
        f"  Hospitals:                {es.n_hospitals:,} ({es.n_feasible:,} feasible)",
        f"  Total RN need:            {es.total_rn_need_fte:,.0f} FTE",
        f"  Median loaded staff:      ${es.median_loaded_staff_per_hr:,.2f}/hr",
        f"  Median agency rate:       ${es.median_agency_per_hr:,.2f}/hr",
        f"  Median agency premium:    ${es.median_agency_premium_per_hr:,.2f}/hr",
        f"  Median Florence fee:      ${es.median_florence_fee:,.0f}/nurse",
        "",
        "FINANCIAL PICTURE (at full RN-need conversion)",
        f"  Hospital pays (gross):    ${es.gross_revenue_total:,.0f}",
        f"  Hospital saves vs agency: ${es.hospital_savings_total:,.0f}",
        f"  Partner revenue:          ${es.partner_revenue_total:,.0f}",
        f"  Florence net revenue:     ${es.florence_net_total:,.0f}",
        "",
        "METHODOLOGY",
        f"  {data.methodology.formula_text}",
        f"  α={data.methodology.alpha:.2f}  ζ=${data.methodology.zeta:.2f}/hr  "
        f"δ_floor=${data.methodology.delta_floor:.2f}  δ_cap=${data.methodology.delta_cap:.2f}",
        f"  Commitment: {data.methodology.commitment_years} years × "
        f"{data.methodology.annual_hours} hrs/yr",
        f"  Cohort visa-exempt share η = {data.methodology.cohort_eta:.2f}",
        "",
        f"HOSPITALS IN PROPOSAL: {len(data.hospitals)}",
    ]
    for h in data.hospitals[:5]:
        lines.append(
            f"  {h.name[:40]:40} {h.city:18} {h.state}  "
            f"δ=${h.delta_per_hr:5.2f}/hr  fee=${h.fee_per_nurse:>7,.0f}  "
            f"FL net=${h.florence_net_per_nurse:>7,.0f}"
        )
    if len(data.hospitals) > 5:
        lines.append(f"  … and {len(data.hospitals) - 5} more")
    lines += ["", "TAX ASSUMPTION", f"  {data.tax_assumption.text}"]
    return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test: build a Kaiser proposal and print summary
    print("Building Kaiser Permanente system proposal...")
    data = build_system_proposal("Kaiser Permanente")
    print(render_text_summary(data))
