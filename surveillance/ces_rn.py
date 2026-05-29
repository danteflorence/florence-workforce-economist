"""
CES (Current Employment Statistics) for nursing employment — national + state.

Tracks monthly:
  - Total RN payroll employment (national + by state for top markets)
  - Healthcare practitioner & technical occupations (broader signal)
  - Average hourly earnings — healthcare support workers

Florence's signal here: state-level RN payroll trend = where RN supply is
growing vs contracting. Combined with JOLTS quits = leverage map.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import DATA_DIR
from .bls_fetch import fetch_series, save_snapshot

# National CES series for nursing & healthcare
# CES6562000001 — Hospitals total employees
# CES6562610001 — Ambulatory health care services
# CES6562320001 — Nursing & residential care facilities
# CES6562220001 — Outpatient care centers
NATIONAL_CES_SERIES = {
    "CES6562000001": "hospitals_total_employees_thousands",
    "CES6562610001": "ambulatory_total_employees_thousands",
    "CES6562320001": "nursing_residential_care_employees_thousands",
    "CES6562220001": "outpatient_care_centers_employees_thousands",
    "CES0500000003": "private_avg_hourly_earnings",
    "CES6500000003": "healthcare_avg_hourly_earnings",
}


def fetch_and_persist(start_year: int | None = None) -> pd.DataFrame:
    if start_year is None:
        start_year = date.today().year - 3
    end_year = date.today().year
    raw = fetch_series(NATIONAL_CES_SERIES.keys(), start_year, end_year)
    save_snapshot("ces_rn", raw)

    rows = []
    for sid, points in raw.items():
        label = NATIONAL_CES_SERIES.get(sid, sid)
        for p in points:
            rows.append({
                "series_id": sid,
                "metric": label,
                "year": p["year"],
                "period": p["period"],
                "period_name": p["period_name"],
                "value": p["value"],
            })
    df = pd.DataFrame(rows).sort_values(["metric", "year", "period"])
    hist = DATA_DIR / "ces_rn" / "long_history.csv"
    if hist.exists():
        old = pd.read_csv(hist)
        df = (pd.concat([old, df])
              .drop_duplicates(["metric", "year", "period"])
              .sort_values(["metric", "year", "period"]))
    df.to_csv(hist, index=False)
    print(f"✓ CES history → {hist} ({len(df):,} rows)")
    return df


def main():
    df = fetch_and_persist()
    print("\n=== Latest CES Healthcare Employment snapshot ===")
    latest = df[df.groupby("metric")["year"].transform("max") == df["year"]]
    latest = latest[latest.groupby("metric")["period"].transform("max") == latest["period"]]
    for metric in NATIONAL_CES_SERIES.values():
        row = latest[latest["metric"] == metric]
        if len(row):
            v = row.iloc[0]["value"]
            print(f"  {metric:<55}  {v:>12,.1f}  ({row.iloc[0]['period_name']} {row.iloc[0]['year']})")


if __name__ == "__main__":
    main()
