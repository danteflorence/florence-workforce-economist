"""
Forecasting layer — project JOLTS healthcare signals 12-24 months forward.

For each labor market signal (openings, hires, quits, layoffs), fit a
seasonal ARIMA model on the historical data and project N months ahead with
confidence intervals.

Florence uses this for:
  - Annual sales planning (where will demand be in 12 months?)
  - Pricing power forecasting (rising openings = increasing pricing power)
  - Fundraising story (multi-year projection of TAM)
"""
from __future__ import annotations

import json
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import DATA_DIR

warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")
warnings.filterwarnings("ignore", category=Warning, module="statsmodels")


def fit_and_forecast(
    series: pd.Series, periods: int = 12,
    seasonal_period: int = 12,
) -> dict:
    """Fit a SARIMA model and return forecast + confidence intervals."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    s = pd.Series(series.dropna().astype(float).values)
    if len(s) < 24:
        return {"error": "Series too short for forecasting (need ≥24 points)"}

    try:
        model = SARIMAX(
            s, order=(1, 1, 1),
            seasonal_order=(1, 1, 0, seasonal_period),
            enforce_stationarity=False, enforce_invertibility=False,
        )
        results = model.fit(disp=False)
    except Exception as e:
        return {"error": f"Model fit failed: {e}"}

    fc = results.get_forecast(steps=periods)
    mean = fc.predicted_mean
    ci = fc.conf_int(alpha=0.20)  # 80% CI
    return {
        "forecast_mean": mean.tolist(),
        "ci_lower": ci.iloc[:, 0].tolist(),
        "ci_upper": ci.iloc[:, 1].tolist(),
        "last_observed": float(s.iloc[-1]),
        "n_observed": len(s),
        "aic": float(results.aic) if hasattr(results, "aic") else None,
    }


def forecast_jolts_metric(metric: str, periods: int = 12) -> dict:
    """Load JOLTS history and forecast the given metric."""
    hist_path = DATA_DIR / "jolts_healthcare" / "long_history.csv"
    if not hist_path.exists():
        return {"error": "No JOLTS history; run surveillance.jolts_healthcare first"}
    df = pd.read_csv(hist_path)
    df = df[df["metric"] == metric].copy()
    if df.empty:
        return {"error": f"Metric '{metric}' not in history"}
    df["period_num"] = df["period"].str.replace("M", "").astype(int, errors="ignore")
    df = df.sort_values(["year", "period_num"])
    return fit_and_forecast(df["value"], periods=periods)


def forecast_all_jolts(periods: int = 12) -> dict:
    """Forecast every JOLTS metric we have."""
    results: dict = {}
    for metric in ["job_openings_level", "hires_level", "quits_level", "layoffs_level"]:
        r = forecast_jolts_metric(metric, periods=periods)
        results[metric] = r
        if "error" not in r:
            curr = r["last_observed"]
            future = r["forecast_mean"][-1]
            pct = (future - curr) / curr * 100 if curr else 0
            print(f"  {metric:<30}  current={curr:>7,.0f}  "
                  f"{periods}mo→{future:>7,.0f}  ({pct:+.1f}%)")
    return results


def main():
    print("Forecasting JOLTS healthcare signals (12-month horizon)")
    print()
    fc = forecast_all_jolts(periods=12)
    out = DATA_DIR / "forecasts" / f"jolts_{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, indent=2, default=str))
    print(f"\n✓ Forecast saved → {out}")

    # Narrative interpretation
    print("\n=== Narrative ===")
    openings = fc.get("job_openings_level", {})
    quits = fc.get("quits_level", {})
    if "forecast_mean" in openings and "forecast_mean" in quits:
        future_op = openings["forecast_mean"][-1]
        future_qt = quits["forecast_mean"][-1]
        current_ratio = openings["last_observed"] / max(quits["last_observed"], 1)
        future_ratio = future_op / max(future_qt, 1)
        direction = "TIGHTENING" if future_ratio > current_ratio else "SOFTENING"
        print(f"  Openings:quits ratio: {current_ratio:.2f} (today) → {future_ratio:.2f} (12mo)")
        print(f"  Direction: {direction}")
        print(f"  Florence implication: pricing power "
              f"{'expanding' if future_ratio > current_ratio else 'normalizing'} over the next year.")


if __name__ == "__main__":
    main()
