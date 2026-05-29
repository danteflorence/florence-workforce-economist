"""
Detect changes in hospital / facility ownership between snapshots.

For each CCN we know about, compare the current health_system_id against the
last snapshot. Output a list of ownership changes that occurred. This catches:
  - Acquisitions (Independent → HCA)
  - Divestitures (HCA → Independent or HCA → Tenet)
  - System mergers (CommonSpirit/Dignity rebranding)
  - Reassignments via our System Ownership tool

Florence cares because:
  - New owner = new decision-maker = sales opportunity reset
  - Acquirers often standardize on a single agency-labor strategy → Florence pitch
  - Divestitures often signal cost pressure → Florence pitch
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from . import DATA_DIR

UNIVERSE = DATA_DIR.parent / "hospital_universe.csv"
NH_FACILITIES = DATA_DIR.parent / "non_hospital_facilities.csv"
SNAPSHOTS_DIR = DATA_DIR / "ownership_snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _today_snapshot_path(name: str) -> Path:
    return SNAPSHOTS_DIR / f"{name}_{date.today().isoformat()}.csv"


def take_snapshot() -> None:
    """Persist today's ownership snapshot for hospital + non-hospital."""
    for src, name in [(UNIVERSE, "hospital"), (NH_FACILITIES, "non_hospital")]:
        if not src.exists():
            print(f"  Source missing: {src}")
            continue
        df = pd.read_csv(src, dtype={"ccn": str})
        df["ccn"] = df["ccn"].astype(str).str.zfill(6)
        if "facility_type" not in df.columns:
            df["facility_type"] = "HOSPITAL"
        snap = df[["ccn", "name", "state", "facility_type",
                   "health_system_id", "health_system"]].copy()
        out = _today_snapshot_path(name)
        snap.to_csv(out, index=False)
        print(f"  ✓ Snapshot: {out} ({len(snap):,} facilities)")


def detect_changes(name: str = "hospital") -> list[dict]:
    """Compare today's snapshot against the previous one."""
    today_path = _today_snapshot_path(name)
    if not today_path.exists():
        return []
    snaps = sorted(SNAPSHOTS_DIR.glob(f"{name}_*.csv"))
    if len(snaps) < 2:
        return []
    prev_path = snaps[-2]
    today_df = pd.read_csv(today_path, dtype={"ccn": str})
    prev_df = pd.read_csv(prev_path, dtype={"ccn": str})
    merged = today_df.merge(
        prev_df[["ccn", "health_system_id", "health_system"]],
        on="ccn", how="left", suffixes=("", "_prev"),
    )
    changes = merged[merged["health_system_id"] != merged["health_system_id_prev"]]
    out = []
    for _, r in changes.iterrows():
        out.append({
            "ccn": r["ccn"],
            "name": r["name"],
            "state": r["state"],
            "facility_type": r["facility_type"],
            "from_system": r["health_system_prev"] or "(missing)",
            "to_system": r["health_system"] or "(missing)",
            "detected": date.today().isoformat(),
        })
    return out


def main():
    print("Owner-change detection")
    take_snapshot()
    all_changes = []
    for name in ["hospital", "non_hospital"]:
        changes = detect_changes(name)
        if changes:
            print(f"\n[{name}] {len(changes)} changes")
            for c in changes[:20]:
                print(f"  {c['ccn']} {c['name'][:40]:<40}  {c['from_system'][:25]:<25} → {c['to_system']}")
        all_changes.extend(changes)
    out = SNAPSHOTS_DIR / f"changes_{date.today().isoformat()}.json"
    out.write_text(json.dumps(all_changes, indent=2))
    print(f"\n✓ {len(all_changes)} changes saved → {out}")


if __name__ == "__main__":
    main()
