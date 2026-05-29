"""
hospital_market_snapshot persistence — v2 Data Model section §3.

Every pricing batch run writes a timestamped snapshot of the priced universe
to data/snapshots/{snapshot_date}.parquet so we can:
  - Reproduce historical pricing decisions
  - Show "rate has moved X% since last snapshot" change indicators
  - Audit which pricing snapshot was used in any given proposal

In production this becomes a Supabase table. For now it's per-day parquet
files that the Streamlit app can list and diff.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"


def snapshot_path(snapshot_date: date | None = None) -> Path:
    snapshot_date = snapshot_date or date.today()
    return SNAPSHOT_DIR / f"snapshot_{snapshot_date.isoformat()}.parquet"


def write_snapshot(priced_df: pd.DataFrame, snapshot_date: date | None = None,
                   calibration_version: str = "") -> Path:
    """Write a snapshot of priced hospitals. Idempotent per day."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_date = snapshot_date or date.today()
    out = priced_df.copy()
    out["snapshot_date"] = snapshot_date.isoformat()
    out["snapshot_taken_at"] = datetime.now().isoformat(timespec="seconds")
    out["calibration_version_at_snapshot"] = calibration_version
    path = snapshot_path(snapshot_date)
    # Drop unhashable columns that parquet can't handle
    out = out.drop(columns=[c for c in out.columns if out[c].apply(lambda x: isinstance(x, (list, dict))).any()], errors="ignore")
    try:
        out.to_parquet(path, index=False)
    except Exception:
        # Fallback to CSV if pyarrow not installed
        path = path.with_suffix(".csv")
        out.to_csv(path, index=False)
    return path


def list_snapshots() -> list[date]:
    """List all snapshot dates available."""
    if not SNAPSHOT_DIR.exists():
        return []
    dates = []
    for f in sorted(SNAPSHOT_DIR.glob("snapshot_*.*")):
        try:
            d = date.fromisoformat(f.stem.replace("snapshot_", ""))
            dates.append(d)
        except ValueError:
            continue
    return sorted(set(dates))


def load_snapshot(snapshot_date: date) -> pd.DataFrame:
    """Load a specific snapshot."""
    pq = snapshot_path(snapshot_date)
    if pq.exists():
        return pd.read_parquet(pq)
    csv = pq.with_suffix(".csv")
    if csv.exists():
        return pd.read_csv(csv)
    raise FileNotFoundError(f"No snapshot for {snapshot_date}")


def diff_snapshots(date_old: date, date_new: date,
                   fields: tuple[str, ...] = ("florence_monthly_fee_per_rn",
                                              "all_in_agency_per_hr",
                                              "actual_fica_offset_pct")) -> pd.DataFrame:
    """Compute change in key pricing fields between two snapshots."""
    old = load_snapshot(date_old).set_index("ccn")
    new = load_snapshot(date_new).set_index("ccn")
    common = old.index.intersection(new.index)
    out = pd.DataFrame(index=common)
    out["name"] = new.loc[common, "name"]
    out["state"] = new.loc[common, "state"]
    for f in fields:
        if f in old.columns and f in new.columns:
            out[f"{f}_old"] = old.loc[common, f]
            out[f"{f}_new"] = new.loc[common, f]
            out[f"{f}_pct_change"] = (
                (new.loc[common, f] - old.loc[common, f]) / old.loc[common, f]
            ).replace([float("inf"), -float("inf")], 0)
    return out.reset_index()


def main() -> None:
    """Generate today's snapshot from the live priced universe."""
    from pricing_engine import Calibration, CohortMix
    from pricing_batch import load_universe, price_batch

    print("Generating today's pricing snapshot...")
    u = load_universe()
    cal = Calibration()
    cohort = CohortMix(eta=1.0)
    priced = price_batch(u, cohort, cal)
    path = write_snapshot(priced, calibration_version=cal.version)
    print(f"  Wrote {path}")
    print(f"  Rows: {len(priced):,}")
    print(f"  Snapshots available: {list_snapshots()}")


if __name__ == "__main__":
    main()
