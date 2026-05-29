"""
Pricing change alerts — diff between snapshots.

For any two pricing snapshots, find hospitals whose key metrics moved beyond
configurable thresholds. Output: a markdown alert report.

In production this runs nightly and dispatches Slack/email alerts when
material changes occur (rate revisions, data refreshes, calibration changes).

Public API:
    diff_to_markdown(date_old, date_new, threshold_pct=0.05) -> str
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from snapshots import list_snapshots, load_snapshot

OUTPUT_DIR = Path(__file__).parent / "data" / "alerts"

# Fields to monitor for movement
MONITORED_FIELDS = [
    ("florence_monthly_fee_per_rn",            "Florence Monthly Fee",    "${:,.0f}/mo"),
    ("all_in_agency_per_hr",                   "Agency Rate",             "${:.2f}/hr"),
    ("employer_fica_savings_per_rn_per_month", "FICA Savings",            "${:,.0f}/mo"),
    ("actual_fica_offset_pct",                 "Actual FICA Offset %",    "{:.1%}"),
    ("net_monthly_savings_per_rn",             "Net Monthly Savings",     "${:,.0f}/mo"),
]


def diff_snapshots(date_old: date, date_new: date,
                   threshold_pct: float = 0.05,
                   threshold_abs_dollars: float = 50.0) -> pd.DataFrame:
    """Find hospitals with material changes between two snapshots."""
    old = load_snapshot(date_old).set_index("ccn")
    new = load_snapshot(date_new).set_index("ccn")
    common = old.index.intersection(new.index)
    changes = []
    for ccn in common:
        row = {
            "ccn": ccn,
            "name": new.at[ccn, "name"] if "name" in new.columns else "",
            "state": new.at[ccn, "state"] if "state" in new.columns else "",
            "health_system": new.at[ccn, "health_system"] if "health_system" in new.columns else "",
        }
        material_change = False
        for field, _, _ in MONITORED_FIELDS:
            if field not in old.columns or field not in new.columns:
                continue
            old_v = old.at[ccn, field]
            new_v = new.at[ccn, field]
            if pd.isna(old_v) or pd.isna(new_v):
                continue
            row[f"{field}_old"] = old_v
            row[f"{field}_new"] = new_v
            abs_diff = new_v - old_v
            row[f"{field}_diff"] = abs_diff
            pct_diff = abs_diff / old_v if old_v else 0
            row[f"{field}_pct_change"] = pct_diff
            # Trigger if either threshold exceeded
            if abs(pct_diff) >= threshold_pct or abs(abs_diff) >= threshold_abs_dollars:
                material_change = True
        if material_change:
            changes.append(row)
    return pd.DataFrame(changes)


def diff_to_markdown(date_old: date, date_new: date,
                     threshold_pct: float = 0.05) -> str:
    """Render the diff as a markdown alert report."""
    diffs = diff_snapshots(date_old, date_new, threshold_pct=threshold_pct)
    if len(diffs) == 0:
        return (f"# Pricing Change Alert — {date_new.isoformat()}\n\n"
                f"No material changes vs. {date_old.isoformat()}.\n")

    lines = [
        f"# Pricing Change Alert — {date_new.isoformat()}",
        "",
        f"Snapshot diff: **{date_old.isoformat()}** → **{date_new.isoformat()}**  ",
        f"Threshold: ±{threshold_pct*100:.0f}% or ±$50",
        f"Hospitals with material changes: **{len(diffs):,}**",
        "",
    ]

    # Movement summary
    fee_field = "florence_monthly_fee_per_rn_diff"
    if fee_field in diffs.columns:
        up = (diffs[fee_field] > 0).sum()
        down = (diffs[fee_field] < 0).sum()
        median_move = diffs[fee_field].median()
        lines += [
            "## Fee movement summary",
            f"- Hospitals with fee increase: {up:,}",
            f"- Hospitals with fee decrease: {down:,}",
            f"- Median fee change: ${median_move:,.0f}/mo",
            "",
        ]

    # By system
    if "health_system" in diffs.columns:
        sys_summary = diffs.groupby("health_system").size().sort_values(ascending=False).head(10)
        lines += ["## By health system (top 10 most affected)", ""]
        for sys, n in sys_summary.items():
            lines.append(f"- **{sys}**: {n} facilities changed")
        lines.append("")

    # Top 25 by absolute fee change
    if fee_field in diffs.columns:
        top = diffs.reindex(diffs[fee_field].abs().sort_values(ascending=False).index).head(25)
        lines += [
            "## Top 25 hospitals by absolute Florence fee change",
            "",
            "| Hospital | State | System | Fee old | Fee new | Δ | Δ% |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for _, r in top.iterrows():
            lines.append(
                f"| {r['name']} | {r['state']} | {r['health_system']} | "
                f"${r['florence_monthly_fee_per_rn_old']:,.0f} | "
                f"${r['florence_monthly_fee_per_rn_new']:,.0f} | "
                f"${r['florence_monthly_fee_per_rn_diff']:+,.0f} | "
                f"{r['florence_monthly_fee_per_rn_pct_change']:+.1%} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    snaps = list_snapshots()
    if len(snaps) < 2:
        print(f"Need at least 2 snapshots; have {len(snaps)}: {snaps}")
        print("Generating a synthetic 'yesterday' snapshot for demo...")
        # Synthesize a "yesterday" snapshot for demo purposes by altering today's
        from datetime import date
        from pricing_engine import Calibration, CohortMix
        from pricing_batch import load_universe, price_batch
        from snapshots import write_snapshot
        # Generate yesterday with a slightly different calibration to force diffs
        cal = Calibration(target_offset_pct=0.45)  # 45% instead of 50% → fees lower
        priced = price_batch(load_universe(), CohortMix(eta=1.0), cal)
        yesterday = date.today() - timedelta(days=1)
        write_snapshot(priced, snapshot_date=yesterday, calibration_version=cal.version + "-synthetic")
        snaps = list_snapshots()
        print(f"Created synthetic snapshot; now have: {snaps}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_old, date_new = snaps[-2], snaps[-1]
    md = diff_to_markdown(date_old, date_new)
    out = OUTPUT_DIR / f"alert_{date_new.isoformat()}.md"
    out.write_text(md, encoding="utf-8")
    print(f"\nWrote {out}")
    print("---")
    print(md[:2000])


if __name__ == "__main__":
    main()
