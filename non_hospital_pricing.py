"""
FICA-only pricing for non-hospital care settings (ASC, HHA, SNF, Hospice, Dialysis).

Unlike hospital pricing which anchors on the HCRIS contract-labor rate, these
settings don't have a public agency-rate dataset. The economic narrative is
different:

    EMPLOYER PAYS
        wage (BLS prevailing) +
        Florence_fee (sized as FICA_savings / target_offset_pct)

    EMPLOYER SAVES
        FICA_savings on the wage (because F-1 RN is exempt)

    EMPLOYER GAINS
        capacity_revenue (each net-new RN unlocks $X in incremental revenue
        the labor-constrained operator otherwise can't capture)

So the pitch is: "Your net cost is small Y per RN per month, you gain Z per RN
per month in incremental revenue. Z >> Y."

All numbers are per-RN per-month unless noted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"

EMPLOYER_FICA_RATE = 0.0765           # 6.2% SS + 1.45% Medicare
HOURS_PER_MONTH = 156                  # 36hr × 52wk / 12mo


@dataclass
class NonHospitalCalibration:
    target_offset_pct: float = 0.40       # FICA covers 40% of fee (Florence protects more of the core rate)
    price_floor_monthly: float = 750.0
    price_ceiling_monthly: float = 2000.0
    term_months: int = 24


def price_non_hospital(
    facilities: pd.DataFrame,
    cal: NonHospitalCalibration | None = None,
) -> pd.DataFrame:
    """Compute the full FICA-only economics + capacity-uplift story for every
    non-hospital facility. Returns a DataFrame with the same row ordering as
    the input plus the pricing columns."""
    cal = cal or NonHospitalCalibration()

    df = facilities.copy()
    wage = pd.to_numeric(df["rn_wage_hourly"], errors="coerce").fillna(40.0)
    rn_n = pd.to_numeric(df["rn_estimate"], errors="coerce").fillna(5).astype(int)
    rev_per_rn_annual = pd.to_numeric(
        df["capacity_revenue_per_rn_annual"], errors="coerce"
    ).fillna(250_000)

    # FICA math (per RN per month)
    monthly_wage = wage * HOURS_PER_MONTH
    monthly_fica_savings = monthly_wage * EMPLOYER_FICA_RATE
    target_fee = monthly_fica_savings / cal.target_offset_pct
    florence_fee = target_fee.clip(
        lower=cal.price_floor_monthly,
        upper=cal.price_ceiling_monthly,
    )
    actual_offset_pct = monthly_fica_savings / florence_fee
    # employer's net cost = fee - FICA savings (the "real" net rate of Florence)
    employer_net_cost_per_rn_month = florence_fee - monthly_fica_savings
    # capacity revenue (incremental per RN per month)
    rev_per_rn_month = rev_per_rn_annual / 12
    # what employer NETS (revenue uplift minus net cost)
    employer_monthly_net_benefit_per_rn = rev_per_rn_month - employer_net_cost_per_rn_month

    df["monthly_wage_per_rn"] = monthly_wage.round(2)
    df["monthly_fica_savings_per_rn"] = monthly_fica_savings.round(2)
    df["florence_fee_per_rn_month"] = florence_fee.round(2)
    df["actual_fica_offset_pct"] = actual_offset_pct.round(3)
    df["employer_net_cost_per_rn_month"] = employer_net_cost_per_rn_month.round(2)
    df["capacity_revenue_per_rn_month"] = rev_per_rn_month.round(2)
    df["employer_monthly_net_benefit_per_rn"] = employer_monthly_net_benefit_per_rn.round(2)

    # Account-level (× rn_estimate)
    df["account_monthly_florence_fee"] = (florence_fee * rn_n).round(2)
    df["account_monthly_fica_savings"] = (monthly_fica_savings * rn_n).round(2)
    df["account_monthly_net_cost"] = (employer_net_cost_per_rn_month * rn_n).round(2)
    df["account_monthly_revenue_uplift"] = (rev_per_rn_month * rn_n).round(2)
    df["account_monthly_net_benefit"] = (employer_monthly_net_benefit_per_rn * rn_n).round(2)

    # Term totals (24 months)
    T = cal.term_months
    df["account_term_florence_fee"] = (df["account_monthly_florence_fee"] * T).round(2)
    df["account_term_net_cost"] = (df["account_monthly_net_cost"] * T).round(2)
    df["account_term_revenue_uplift"] = (df["account_monthly_revenue_uplift"] * T).round(2)
    df["account_term_net_benefit"] = (df["account_monthly_net_benefit"] * T).round(2)

    # ROI multiple = revenue_uplift / florence_fee (the headline pitch number)
    df["roi_revenue_to_fee"] = (
        df["account_term_revenue_uplift"] / df["account_term_florence_fee"]
    ).round(2)

    df["pricing_mode"] = "FICA_ONLY"
    df["calibration_target_offset_pct"] = cal.target_offset_pct
    df["calibration_term_months"] = T
    return df


def main() -> None:
    src = DATA / "non_hospital_facilities.csv"
    facilities = pd.read_csv(src, dtype={"ccn": str})
    facilities["ccn"] = facilities["ccn"].astype(str).str.zfill(6)

    print(f"Pricing {len(facilities):,} non-hospital facilities…")
    priced = price_non_hospital(facilities)
    out = DATA / "non_hospital_priced.parquet"
    priced.to_parquet(out, index=False)
    print(f"✓ Wrote {out}")
    print()
    print("=== By facility type — median per-RN economics ===")
    grp = priced.groupby("facility_type").agg(
        n_facilities=("ccn", "count"),
        rn_total=("rn_estimate", "sum"),
        med_fee=("florence_fee_per_rn_month", "median"),
        med_fica=("monthly_fica_savings_per_rn", "median"),
        med_net_cost=("employer_net_cost_per_rn_month", "median"),
        med_rev_uplift=("capacity_revenue_per_rn_month", "median"),
        med_roi=("roi_revenue_to_fee", "median"),
    ).round(0).astype(int)
    print(grp.to_string())
    print()
    print(f"Aggregate term value (across all {len(priced):,} facilities):")
    print(f"  Total Florence fees (24mo):       ${priced['account_term_florence_fee'].sum()/1e9:.2f}B")
    print(f"  Total employer FICA savings:      ${(priced['account_monthly_fica_savings']*24).sum()/1e9:.2f}B")
    print(f"  Total employer net cost (24mo):   ${priced['account_term_net_cost'].sum()/1e9:.2f}B")
    print(f"  Total revenue uplift (24mo):      ${priced['account_term_revenue_uplift'].sum()/1e12:.2f}T")


if __name__ == "__main__":
    main()
