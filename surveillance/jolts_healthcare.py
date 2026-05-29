"""
JOLTS for Healthcare & Social Assistance (NAICS 62) — national.

Tracks monthly:
  - Job openings (JTS62000000HIL)  — vacancy intensity
  - Hires        (JTS62000000HIR)  — actual hiring activity
  - Quits        (JTS62000000QUL)  — voluntary separations (labor leverage)
  - Layoffs      (JTS62000000LDL)  — involuntary separations
  - Total separations (JTS62000000TSL)

The signal: rising QUITS in healthcare = workers have leverage, wages will follow.
Rising OPENINGS without rising HIRES = labor shortage tightening.

Run monthly. Each run writes JSON snapshot + appends to a long history CSV.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import DATA_DIR
from .bls_fetch import fetch_series, save_snapshot

HEALTHCARE_JOLTS_SERIES = {
    "JTS620000000000000HIL": "job_openings_level",
    "JTS620000000000000HIR": "hires_level",
    "JTS620000000000000QUL": "quits_level",
    "JTS620000000000000LDL": "layoffs_level",
    "JTS620000000000000TSL": "total_separations_level",
    "JTS620000000000000JOR": "job_openings_rate",
    "JTS620000000000000HIR": "hires_rate",
    "JTS620000000000000QUR": "quits_rate",
}


def fetch_and_persist(start_year: int | None = None) -> pd.DataFrame:
    """Fetch latest JOLTS healthcare numbers + persist snapshot + long history."""
    end_year = date.today().year
    if start_year is None:
        start_year = end_year - 3

    raw = fetch_series(HEALTHCARE_JOLTS_SERIES.keys(), start_year, end_year)
    save_snapshot("jolts_healthcare", raw)

    rows = []
    for sid, points in raw.items():
        label = HEALTHCARE_JOLTS_SERIES.get(sid, sid)
        for p in points:
            rows.append({
                "series_id": sid,
                "metric": label,
                "year": p["year"],
                "period": p["period"],
                "period_name": p["period_name"],
                "value": p["value"],
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["metric", "year", "period"])

    # Append to long history
    hist_path = DATA_DIR / "jolts_healthcare" / "long_history.csv"
    if hist_path.exists():
        old = pd.read_csv(hist_path)
        df = pd.concat([old, df]).drop_duplicates(["metric", "year", "period"]).sort_values(["metric", "year", "period"])
    df.to_csv(hist_path, index=False)
    print(f"✓ JOLTS healthcare history → {hist_path} ({len(df):,} rows)")
    return df


def main():
    df = fetch_and_persist()
    print("\n=== Latest JOLTS Healthcare snapshot ===")
    latest = df[df.groupby("metric")["year"].transform("max") == df["year"]]
    latest = latest[latest.groupby("metric")["period"].transform("max") == latest["period"]]
    for metric in ["job_openings_level", "hires_level", "quits_level", "layoffs_level"]:
        row = latest[latest["metric"] == metric]
        if len(row):
            v = row.iloc[0]["value"]
            print(f"  {metric:<30}  {v:>10,.0f}  (thousands, {row.iloc[0]['period_name']} {row.iloc[0]['year']})")


if __name__ == "__main__":
    main()
