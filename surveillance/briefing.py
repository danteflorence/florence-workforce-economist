"""
Florence Workforce Surveillance — weekly briefing summarizer.

Reads all surveillance feeds, computes month-over-month deltas, surfaces:
  - Top movers in labor market signals
  - Florence pricing implications
  - Specific systems/MSAs to prioritize

Produces:
  - data/surveillance/briefings/YYYY-MM-DD.md  — human-readable briefing
  - data/surveillance/briefings/YYYY-MM-DD.json — machine-readable for dashboard
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from . import DATA_DIR

BRIEFINGS_DIR = DATA_DIR / "briefings"
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR = DATA_DIR / "pricing_snapshots"  # for ownership/pricing-changes references


def load_jolts() -> pd.DataFrame | None:
    path = DATA_DIR / "jolts_healthcare" / "long_history.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["period_num"] = df["period"].str.replace("M", "").astype(int, errors="ignore")
    df = df.sort_values(["metric", "year", "period_num"])
    return df


def load_ces() -> pd.DataFrame | None:
    path = DATA_DIR / "ces_rn" / "long_history.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["period_num"] = df["period"].str.replace("M", "").astype(int, errors="ignore")
    df = df.sort_values(["metric", "year", "period_num"])
    return df


def latest_two_periods(df: pd.DataFrame, metric: str) -> tuple[dict, dict] | None:
    sub = df[df["metric"] == metric].dropna(subset=["value"]).tail(2)
    if len(sub) < 2:
        return None
    return (sub.iloc[-2].to_dict(), sub.iloc[-1].to_dict())


def fmt_delta(curr: float, prev: float, unit: str = "k") -> str:
    delta = curr - prev
    pct = (delta / prev * 100) if prev != 0 else 0
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:,.0f}{unit} ({sign}{pct:.1f}%)"


def build_briefing() -> dict[str, Any]:
    """Compute the briefing data structure."""
    today = date.today()
    insights: list[dict[str, Any]] = []
    jolts = load_jolts()
    ces = load_ces()

    # ─── JOLTS labor leverage signals ────────────────────────────────
    if jolts is not None:
        for metric, label, threshold_pct in [
            ("job_openings_level", "Healthcare job openings", 2),
            ("hires_level",       "Healthcare hires",         3),
            ("quits_level",       "Healthcare quits",         3),
            ("layoffs_level",     "Healthcare layoffs",       5),
        ]:
            pair = latest_two_periods(jolts, metric)
            if pair is None: continue
            prev, curr = pair
            delta_pct = (curr["value"] - prev["value"]) / prev["value"] * 100 if prev["value"] else 0
            severity = "high" if abs(delta_pct) >= threshold_pct else "info"
            insights.append({
                "category": "Labor market",
                "metric": label,
                "current": curr["value"],
                "previous": prev["value"],
                "delta_pct": delta_pct,
                "period": f"{curr['period_name']} {curr['year']}",
                "prior_period": f"{prev['period_name']} {prev['year']}",
                "severity": severity,
                "interpretation": _interpret_jolts(metric, delta_pct),
            })

    # ─── CES employment trends ──────────────────────────────────────
    if ces is not None:
        for metric, label in [
            ("hospitals_total_employees_thousands", "Hospital sector employees"),
            ("nursing_residential_care_employees_thousands", "Nursing & residential care employees"),
            ("healthcare_avg_hourly_earnings",      "Healthcare avg hourly earnings"),
        ]:
            pair = latest_two_periods(ces, metric)
            if pair is None: continue
            prev, curr = pair
            delta_pct = (curr["value"] - prev["value"]) / prev["value"] * 100 if prev["value"] else 0
            insights.append({
                "category": "Employment & wages",
                "metric": label,
                "current": curr["value"],
                "previous": prev["value"],
                "delta_pct": delta_pct,
                "period": f"{curr['period_name']} {curr['year']}",
                "prior_period": f"{prev['period_name']} {prev['year']}",
                "severity": "high" if abs(delta_pct) >= 0.5 else "info",
                "interpretation": _interpret_ces(metric, delta_pct),
            })

    # ─── Headline summary ────────────────────────────────────────────
    # Florence's key combination: openings rising + quits high = tight labor mkt
    if jolts is not None:
        op = latest_two_periods(jolts, "job_openings_level")
        qt = latest_two_periods(jolts, "quits_level")
        if op and qt:
            op_curr = op[1]["value"]
            qt_curr = qt[1]["value"]
            ratio = op_curr / max(qt_curr, 1)
            headline = (
                f"**Healthcare labor market is {'TIGHT' if ratio > 1.3 else 'BALANCED'}.** "
                f"As of {op[1]['period_name']} {op[1]['year']}, healthcare has "
                f"{op_curr:,.0f}K job openings against {qt_curr:,.0f}K quits "
                f"(ratio: {ratio:.2f}). "
                f"{'Operators are competing for talent — Florence positioning is strongest in tight markets.' if ratio > 1.3 else 'Hiring intensity is normalizing.'}"
            )
        else:
            headline = "Insufficient JOLTS data yet — run more surveillance refreshers."
    else:
        headline = "No surveillance data yet — run python -m surveillance.jolts_healthcare first."

    # ─── News mentions (if available) ───────────────────────────────
    news_path = DATA_DIR / "news_feeds" / "mentions.csv"
    news_recent = []
    if news_path.exists():
        try:
            import pandas as pd
            news_df = pd.read_csv(news_path)
            news_df["date_fetched"] = pd.to_datetime(news_df["date_fetched"])
            # Mentions from past 7 days
            cutoff = pd.Timestamp(today) - pd.Timedelta(days=7)
            recent = news_df[news_df["date_fetched"] >= cutoff]
            news_recent = recent.head(20).to_dict(orient="records")
        except Exception:
            pass

    # ─── Ownership changes (if available) ───────────────────────────
    ownership_changes = []
    own_path = SNAPSHOTS_DIR.parent / "ownership_snapshots" / f"changes_{today.isoformat()}.json"
    if own_path.exists():
        try:
            ownership_changes = json.loads(own_path.read_text())
        except Exception:
            pass

    # ─── Forecast narrative (if forecast exists) ────────────────────
    forecast_narrative = None
    forecast_path = DATA_DIR / "forecasts"
    if forecast_path.exists():
        forecasts = sorted(forecast_path.glob("jolts_*.json"))
        if forecasts:
            try:
                fc = json.loads(forecasts[-1].read_text())
                op = fc.get("job_openings_level", {})
                qt = fc.get("quits_level", {})
                if "forecast_mean" in op and "forecast_mean" in qt:
                    cur_ratio = op["last_observed"] / max(qt["last_observed"], 1)
                    fut_ratio = op["forecast_mean"][-1] / max(qt["forecast_mean"][-1], 1)
                    forecast_narrative = (
                        f"12-month projection: openings/quits ratio "
                        f"{cur_ratio:.2f} → {fut_ratio:.2f}. "
                        f"Florence pricing power "
                        f"{'expanding' if fut_ratio > cur_ratio else 'normalizing'} over the next year."
                    )
            except Exception:
                pass

    briefing = {
        "as_of": today.isoformat(),
        "headline": headline,
        "insights": insights,
        "news_mentions_7d": news_recent,
        "ownership_changes_today": ownership_changes,
        "forecast_narrative": forecast_narrative,
        "feeds_status": {
            "jolts_healthcare": "current" if jolts is not None else "missing",
            "ces_rn":            "current" if ces is not None else "missing",
            "news_feeds":        "current" if news_recent else "missing",
            "forecasts":         "current" if forecast_narrative else "missing",
        },
    }

    # Write JSON + markdown
    json_path = BRIEFINGS_DIR / f"{today.isoformat()}.json"
    json_path.write_text(json.dumps(briefing, indent=2, default=str))
    md_path = BRIEFINGS_DIR / f"{today.isoformat()}.md"
    md_path.write_text(_render_markdown(briefing))
    return briefing


def _interpret_jolts(metric: str, delta_pct: float) -> str:
    direction = "rose" if delta_pct >= 0 else "fell"
    abs_pct = abs(delta_pct)
    if metric == "job_openings_level":
        if delta_pct > 0:
            return f"Openings {direction} {abs_pct:.1f}% — demand intensifying. Florence pricing power increases."
        return f"Openings {direction} {abs_pct:.1f}% — slight softening. Maintain pricing discipline."
    if metric == "quits_level":
        if delta_pct > 0:
            return f"Quits {direction} {abs_pct:.1f}% — workers have more leverage. Wage pressure on operators."
        return f"Quits {direction} {abs_pct:.1f}% — workers feeling less mobile. Less wage pressure."
    if metric == "layoffs_level":
        if delta_pct > 0:
            return f"Layoffs {direction} {abs_pct:.1f}% — operators tightening payroll. May signal cost-pressure conversations."
        return f"Layoffs {direction} {abs_pct:.1f}% — stable headcount."
    return f"{direction} {abs_pct:.1f}%"


def _interpret_ces(metric: str, delta_pct: float) -> str:
    direction = "rose" if delta_pct >= 0 else "fell"
    abs_pct = abs(delta_pct)
    if "earnings" in metric:
        if delta_pct > 0.3:
            return f"Wages {direction} {abs_pct:.2f}% — refresh Florence wage base for FICA calculations."
        return f"Wages stable ({direction} {abs_pct:.2f}%)."
    if "hospitals" in metric:
        return f"Hospital employment {direction} {abs_pct:.2f}% — { 'capacity growing' if delta_pct > 0 else 'sector contracting'}."
    return f"{direction} {abs_pct:.2f}%"


def _render_markdown(briefing: dict[str, Any]) -> str:
    lines = [
        f"# Florence Workforce Briefing — {briefing['as_of']}",
        "",
        f"## Headline",
        briefing["headline"],
        "",
        "## Insights",
    ]
    by_cat: dict[str, list] = {}
    for ins in briefing["insights"]:
        by_cat.setdefault(ins["category"], []).append(ins)
    for cat, items in by_cat.items():
        lines.append(f"\n### {cat}\n")
        for ins in items:
            arrow = "↑" if ins["delta_pct"] >= 0 else "↓"
            sev_mark = "🔴" if ins["severity"] == "high" else "—"
            lines.append(
                f"- {sev_mark} **{ins['metric']}**: "
                f"{ins['current']:,.1f} ({ins['period']}) "
                f"{arrow} {ins['delta_pct']:+.1f}% from {ins['prior_period']}"
            )
            lines.append(f"  - _{ins['interpretation']}_")
    return "\n".join(lines)


def main():
    b = build_briefing()
    print(b["headline"])
    print()
    for ins in b["insights"]:
        arrow = "↑" if ins["delta_pct"] >= 0 else "↓"
        sev = "[!]" if ins["severity"] == "high" else "[-]"
        print(f"{sev} {ins['metric']:<45}  {ins['current']:>10,.1f}  {arrow} {ins['delta_pct']:+6.1f}%")
    print(f"\n✓ Briefing written to {BRIEFINGS_DIR}")


if __name__ == "__main__":
    main()
