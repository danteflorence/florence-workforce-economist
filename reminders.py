"""
Snooze / reminders — defer an account to a future date; feeds the Today list.

A rep snoozes a system ("remind me in N days"); until that date it's suppressed
from Today's "due" + "start these". data/snoozes.csv (gitignored, mutable); one
active snooze per entity (latest wins). All accessors tolerate a missing file.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
SNOOZES = DATA_DIR / "snoozes.csv"
FIELDS = ["entity_type", "entity_id", "snooze_until", "note", "by", "created_at"]


def _ensure() -> None:
    if not SNOOZES.exists():
        SNOOZES.parent.mkdir(parents=True, exist_ok=True)
        with open(SNOOZES, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure()
    try:
        return pd.read_csv(SNOOZES, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)


def _today(now=None) -> str:
    return (now or datetime.utcnow()).date().isoformat()


def snooze(entity_type: str, entity_id: str, days: int, note: str = "", by: str = "") -> str:
    """Snooze an entity for `days`. Returns the snooze-until date (ISO)."""
    _ensure()
    df = _read()
    if not df.empty:
        df = df[~((df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id)))]
    until = (datetime.utcnow() + timedelta(days=int(days))).date().isoformat()
    row = {"entity_type": entity_type, "entity_id": str(entity_id), "snooze_until": until,
           "note": note, "by": by, "created_at": datetime.utcnow().isoformat(timespec="seconds")}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(SNOOZES, index=False, columns=FIELDS)
    return until


def clear(entity_type: str, entity_id: str) -> bool:
    df = _read()
    if df.empty:
        return False
    keep = df[~((df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id)))]
    keep.to_csv(SNOOZES, index=False, columns=FIELDS)
    return len(keep) != len(df)


def snoozed_until(entity_type: str, entity_id: str, now=None) -> str:
    """The snooze-until date if the entity is still snoozed (future), else ''."""
    df = _read()
    if df.empty:
        return ""
    m = df[(df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))]
    if m.empty:
        return ""
    until = str(m.iloc[-1].get("snooze_until", ""))
    return until if until >= _today(now) else ""


def is_snoozed(entity_type: str, entity_id: str, now=None) -> bool:
    return bool(snoozed_until(entity_type, entity_id, now))


def active(now=None) -> list[dict]:
    """All entities currently snoozed (until >= today), soonest first."""
    df = _read()
    if df.empty:
        return []
    today = _today(now)
    df = df[df["snooze_until"] >= today]
    return df.sort_values("snooze_until").to_dict("records")
