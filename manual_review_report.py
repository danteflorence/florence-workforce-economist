"""
Manual-review explanation report.

The pricing engine flags hospitals for manual review when it cannot auto-quote
defensibly (per v2 §10). This module categorizes those hospitals by reason and
suggests what customer disclosure would unblock each one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pricing_engine import Calibration, CohortMix
from pricing_batch import load_universe, price_batch


def categorize(row) -> str:
    reason = (row.get("manual_review_reason") or "").lower()
    if "non-positive" in reason or "negative" in reason:
        return "agency_rate_below_staff_cost"
    if "missing or zero" in reason or "missing" in reason:
        return "missing_agency_rate"
    if "confidence" in reason:
        return "low_confidence_agency_rate"
    return "other"


def suggested_resolution(category: str) -> str:
    return {
        "agency_rate_below_staff_cost": (
            "Hospital's HCRIS-reported contract labor rate is below its loaded "
            "staff cost. Likely cases: (a) vertically-integrated systems with "
            "negotiated MSP rates; (b) systems where HCRIS undercounts MSP "
            "markup (add system-level overlay). RESOLUTION: customer-disclosed "
            "all-in agency rate, or add SystemOverlay for the parent system."
        ),
        "missing_agency_rate": (
            "Hospital didn't report contract labor in HCRIS — likely a low-"
            "agency-dependent facility. RESOLUTION: customer disclosure of actual "
            "agency spend, OR quote at STANDARD_FEE ($1,750/mo)."
        ),
        "low_confidence_agency_rate": (
            "Agency rate is national-imputed (no HCRIS data, no CommonSpirit "
            "anchor). RESOLUTION: customer disclosure preferred; engine already "
            "falls back to STANDARD_FEE in this case."
        ),
        "other": (
            "Other manual-review reason. Inspect manual_review_reason field."
        ),
    }[category]


def main() -> None:
    print("Generating manual-review explanation report...")
    u = load_universe()
    priced = price_batch(u, CohortMix(eta=1.0), Calibration())
    mr = priced[priced["manual_review_flag"]].copy()

    mr["category"] = mr.apply(categorize, axis=1)

    cat_summary = mr.groupby("category").agg(
        n=("ccn", "count"),
        states=("state", "nunique"),
        rn_need=("rn_need", "sum"),
    ).reset_index().sort_values("n", ascending=False)

    print(f"\nTotal manual-review hospitals: {len(mr):,}")
    print("\nBy category:")
    print(cat_summary.to_string(index=False))

    # By system
    sys_breakdown = mr.groupby(["health_system", "category"]).size().unstack(fill_value=0)
    top_sys = mr["health_system"].value_counts().head(15)
    print(f"\nTop 15 systems with manual-review hospitals:")
    print(top_sys.to_string())

    # Generate markdown report
    out = Path("data/manual_review_report.md")
    lines = [
        f"# Manual-Review Hospital Report — {date.today().isoformat()}",
        "",
        f"Total hospitals flagged: **{len(mr):,}** of {len(priced):,} ({len(mr)/len(priced)*100:.1f}%)",
        "",
        "## Categories and resolutions",
        "",
    ]
    for _, r in cat_summary.iterrows():
        lines += [
            f"### `{r['category']}` — {r['n']} hospitals",
            "",
            f"- Across {r['states']} states",
            f"- Aggregate RN need: {r['rn_need']:,.0f} FTE",
            "",
            f"**Resolution:** {suggested_resolution(r['category'])}",
            "",
        ]

    lines.append("## Hospital-by-hospital detail (top 100)")
    lines.append("")
    lines.append("| CCN | Hospital | State | System | Category | Reason |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in mr.sort_values("rn_need", ascending=False).head(100).iterrows():
        reason = (r.get("manual_review_reason") or "")[:80]
        lines.append(
            f"| {r['ccn']} | {r['name']} | {r['state']} | "
            f"{r.get('health_system','')} | `{r['category']}` | {reason} |"
        )

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {out}")

    # Also write the raw data
    mr_export = mr[["ccn", "name", "city", "state", "health_system",
                    "loaded_staff_cost_per_hr", "all_in_agency_per_hr",
                    "agency_premium_per_hr", "data_source", "confidence",
                    "category", "manual_review_reason"]]
    csv_path = Path("data/manual_review_hospitals.csv")
    mr_export.to_csv(csv_path, index=False)
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
