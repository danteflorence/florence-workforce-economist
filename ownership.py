"""
System ownership — assign accounts to reps; powers the "My book" filter.

data/system_owners.csv (gitignored, mutable rep data). Latest assignment per
system wins. Read-only-safe: every accessor tolerates a missing/empty file.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OWNERS = DATA_DIR / "system_owners.csv"
FIELDS = ["system_id", "owner_email", "assigned_at", "assigned_by"]


def _ensure() -> None:
    if not OWNERS.exists():
        OWNERS.parent.mkdir(parents=True, exist_ok=True)
        with open(OWNERS, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure()
    try:
        return pd.read_csv(OWNERS, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)


def assign(system_id: str, owner_email: str, by: str = "") -> bool:
    """Assign (or reassign) a system to a rep. Latest wins."""
    _ensure()
    df = _read()
    if not df.empty:
        df = df[df["system_id"].astype(str) != str(system_id)]
    row = {"system_id": str(system_id), "owner_email": (owner_email or "").strip().lower(),
           "assigned_at": datetime.utcnow().isoformat(timespec="seconds"),
           "assigned_by": (by or "").strip().lower()}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(OWNERS, index=False, columns=FIELDS)
    return True


def unassign(system_id: str) -> bool:
    df = _read()
    if df.empty:
        return False
    keep = df[df["system_id"].astype(str) != str(system_id)]
    keep.to_csv(OWNERS, index=False, columns=FIELDS)
    return len(keep) != len(df)


def owners_map() -> dict:
    df = _read()
    if df.empty:
        return {}
    if "assigned_at" in df.columns:
        df = df.sort_values("assigned_at")
    return {str(r["system_id"]): str(r["owner_email"]) for _, r in df.iterrows()
            if str(r["owner_email"]).strip()}


def owner_of(system_id: str) -> str:
    return owners_map().get(str(system_id), "")


def book_of(owner_email: str) -> set:
    """Set of system_ids owned by a rep."""
    oe = (owner_email or "").strip().lower()
    if not oe:
        return set()
    return {sid for sid, owner in owners_map().items() if owner == oe}
