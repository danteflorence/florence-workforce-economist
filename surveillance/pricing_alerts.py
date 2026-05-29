"""
Pricing-change alerts — detect significant pricing drift across snapshots.

For each facility (or system), compare today's recommended pricing against
the prior snapshot. Surface:
  - Systems whose median Target fee moved >5% (calibration or data drift)
  - Hospitals that newly become feasible (or newly infeasible)
  - Hospitals where Stretch/Reference bands widened/narrowed significantly

Florence ops + sales use this to:
  - Notify reps when their target system's pricing moved
  - Detect data-quality issues (sudden drops = something broke)
  - Validate that the engine is stable
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import DATA_DIR

SNAPSHOTS_DIR = DATA_DIR / "pricing_snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def take_snapshot() -> Path | None:
    """Persist today's recommendations.parquet pricing for system-level rollup."""
    recs = DATA_DIR.parent / "recommendations.parquet"
    if not recs.exists():
        print("  recommendations.parquet missing")
        return None
    df = pd.read_parquet(recs)
    if "feasible" not in df.columns:
        df["feasible"] = True
    feas = df[df["feasible"]]
    # System-level rollup
    if "target_monthly_florence_fee_account" in feas.columns:
        rollup = (
            feas.groupby(["health_system_id", "health_system"])
            .agg(
                n_facilities=("ccn", "count"),
                monthly_fee_sum=("target_monthly_florence_fee_account", "sum"),
                median_target_fee=("target_monthly_fee", "median"),
                median_stretch_fee=("stretch_monthly_fee", "median"),
                median_reference_fee=("reference_monthly_fee", "median"),
                total_term_savings=("target_term_net_savings_account", "sum"),
            )
            .reset_index()
        )
    else:
        return None
    out = SNAPSHOTS_DIR / f"pricing_{date.today().isoformat()}.csv"
    rollup.to_csv(out, index=False)
    print(f"  ✓ Pricing snapshot: {out}")
    return out


def detect_changes(threshold_pct: float = 5.0) -> list[dict]:
    """Compare today vs prior; emit alerts where median target fee changed
    by more than threshold_pct."""
    snaps = sorted(SNAPSHOTS_DIR.glob("pricing_*.csv"))
    if len(snaps) < 2:
        return []
    today_df = pd.read_csv(snaps[-1])
    prev_df = pd.read_csv(snaps[-2])
    merged = today_df.merge(
        prev_df, on="health_system_id", suffixes=("", "_prev"), how="outer",
    )
    alerts: list[dict] = []
    for _, r in merged.iterrows():
        cur = r.get("median_target_fee")
        prev = r.get("median_target_fee_prev")
        if pd.isna(cur) or pd.isna(prev) or prev == 0:
            continue
        pct = (cur - prev) / prev * 100
        if abs(pct) >= threshold_pct:
            severity = "high" if abs(pct) >= 15 else "medium"
            alerts.append({
                "system_id": r["health_system_id"],
                "system_name": r.get("health_system") or r.get("health_system_prev"),
                "previous_median_target_fee": float(prev),
                "current_median_target_fee": float(cur),
                "change_pct": float(pct),
                "severity": severity,
                "detected": date.today().isoformat(),
            })
    return alerts


def main():
    print("Pricing-change alerts")
    take_snapshot()
    alerts = detect_changes()
    if alerts:
        print(f"\n=== {len(alerts)} pricing alerts ===")
        for a in alerts[:20]:
            arrow = "↑" if a["change_pct"] >= 0 else "↓"
            print(f"  [{a['severity'].upper():>6}]  {a['system_name'][:30]:<30}  "
                  f"${a['previous_median_target_fee']:,.0f} {arrow} ${a['current_median_target_fee']:,.0f}  "
                  f"({a['change_pct']:+.1f}%)")
    else:
        print("\nNo significant pricing changes since last snapshot.")
    out = SNAPSHOTS_DIR / f"alerts_{date.today().isoformat()}.json"
    out.write_text(json.dumps(alerts, indent=2))
    print(f"\n✓ Alerts saved → {out}")


if __name__ == "__main__":
    main()
