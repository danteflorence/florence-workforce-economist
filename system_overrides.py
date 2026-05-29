"""
System-ownership override layer.

Hospitals get sold between systems. Systems merge. Florence's sales reps need
to model "what if HCA acquires X?" scenarios without rebuilding the universe.

This module stores per-CCN overrides in `data/system_overrides.json` and applies
them on top of `hospital_universe.csv` at load time. All downstream code
(recommendations, Excel, PDF, the customer deck) sees the override-applied
ownership without knowing anything about overrides.

Override schema:
{
    "version": 1,
    "updated_at": "2026-05-28T15:30:00",
    "overrides": [
        {
            "ccn": "100000",
            "new_system_id": "hca",
            "new_system_name": "HCA",
            "note": "Acquired Q1 2026",
            "created_at": "2026-05-28T15:30:00"
        },
        ...
    ]
}
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OVERRIDES_PATH = DATA_DIR / "system_overrides.json"


@dataclass
class OverrideRecord:
    ccn: str
    new_system_id: str
    new_system_name: str
    note: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)


def load_overrides() -> list[OverrideRecord]:
    """Read the override file. Returns empty list if file missing/malformed."""
    if not OVERRIDES_PATH.exists():
        return []
    try:
        with open(OVERRIDES_PATH) as f:
            blob = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return [
        OverrideRecord(
            ccn=str(r["ccn"]).zfill(6),
            new_system_id=str(r["new_system_id"]),
            new_system_name=str(r.get("new_system_name", "")),
            note=str(r.get("note", "")),
            created_at=str(r.get("created_at", "")),
        )
        for r in blob.get("overrides", [])
    ]


def save_overrides(records: Iterable[OverrideRecord]) -> None:
    """Atomically write the override file."""
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "version": 1,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "overrides": [r.to_dict() for r in records],
    }
    tmp = OVERRIDES_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=2)
    tmp.replace(OVERRIDES_PATH)


def overrides_mtime() -> float:
    """Return mtime of override file (or 0 if missing). Used as cache key
    so Streamlit invalidates dataframes when overrides change."""
    return OVERRIDES_PATH.stat().st_mtime if OVERRIDES_PATH.exists() else 0.0


def apply_overrides(universe: pd.DataFrame) -> pd.DataFrame:
    """Apply all overrides to a universe DataFrame in-place style (returns new df)."""
    overrides = load_overrides()
    if not overrides:
        return universe
    u = universe.copy()
    u["ccn"] = u["ccn"].astype(str).str.zfill(6)
    over_df = pd.DataFrame(
        [{"ccn": r.ccn, "new_system_id": r.new_system_id, "new_system_name": r.new_system_name}
         for r in overrides]
    )
    u = u.merge(over_df, on="ccn", how="left")
    # For rows with an override, replace the system fields
    mask = u["new_system_id"].notna()
    u.loc[mask, "health_system_id"] = u.loc[mask, "new_system_id"]
    # If override didn't include a display name, keep the old one
    name_mask = mask & u["new_system_name"].fillna("").ne("")
    u.loc[name_mask, "health_system"] = u.loc[name_mask, "new_system_name"]
    return u.drop(columns=["new_system_id", "new_system_name"])


def append_override(
    ccn: str,
    new_system_id: str,
    new_system_name: str,
    note: str = "",
) -> None:
    """Add or replace a single override."""
    ccn = str(ccn).zfill(6)
    records = [r for r in load_overrides() if r.ccn != ccn]
    records.append(
        OverrideRecord(
            ccn=ccn,
            new_system_id=new_system_id,
            new_system_name=new_system_name,
            note=note,
        )
    )
    save_overrides(records)


def append_overrides_bulk(rows: Iterable[dict]) -> int:
    """Add or replace multiple overrides. Returns count added.
    Each row: {ccn, new_system_id, new_system_name, note?}"""
    existing = {r.ccn: r for r in load_overrides()}
    n_added = 0
    for row in rows:
        ccn = str(row["ccn"]).zfill(6)
        existing[ccn] = OverrideRecord(
            ccn=ccn,
            new_system_id=row["new_system_id"],
            new_system_name=row.get("new_system_name", ""),
            note=row.get("note", ""),
        )
        n_added += 1
    save_overrides(existing.values())
    return n_added


def delete_override(ccn: str) -> bool:
    """Remove an override. Returns True if it was found and removed."""
    ccn = str(ccn).zfill(6)
    records = load_overrides()
    new_records = [r for r in records if r.ccn != ccn]
    if len(new_records) == len(records):
        return False
    save_overrides(new_records)
    return True


def delete_all_overrides() -> int:
    """Wipe all overrides. Returns count deleted."""
    records = load_overrides()
    n = len(records)
    save_overrides([])
    return n


def known_systems(universe: pd.DataFrame) -> pd.DataFrame:
    """Return {system_id, system_name, n_hospitals} for every system currently
    present in the universe (after overrides). Useful for system dropdowns."""
    return (
        universe.groupby(["health_system_id", "health_system"])
        .size()
        .reset_index(name="n_hospitals")
        .sort_values("n_hospitals", ascending=False)
    )


if __name__ == "__main__":
    print(f"Overrides file: {OVERRIDES_PATH}")
    print(f"Current overrides: {len(load_overrides())}")
    for r in load_overrides():
        print(f"  {r.ccn} → {r.new_system_id} ({r.note})")
