"""
Account activity log — a real CRM timeline before Streak.

An append-only log of calls / notes / meetings per account, MERGED with the
mailpiece log (lob_mailer) so each account shows one chronological history of
every touch and outcome. Plus freeform notes a rep can log and search.

data/activity_log.csv — mutable rep data (gitignored).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
LOG = DATA_DIR / "activity_log.csv"
FIELDS = ["ts", "entity_type", "entity_id", "org_name", "kind", "detail", "by"]
KINDS = ["call", "note", "meeting", "email"]


def _ensure() -> None:
    if not LOG.exists():
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure()
    try:
        return pd.read_csv(LOG, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)


def log(entity_type: str, entity_id: str, kind: str, detail: str,
        org_name: str = "", by: str = "") -> bool:
    """Append one activity event."""
    _ensure()
    row = {
        "ts": datetime.utcnow().isoformat(timespec="seconds"),
        "entity_type": entity_type, "entity_id": str(entity_id),
        "org_name": org_name, "kind": kind, "detail": detail, "by": by,
    }
    df = pd.concat([_read(), pd.DataFrame([row])], ignore_index=True)
    df.to_csv(LOG, index=False, columns=FIELDS)
    return True


def _mail_events(entity_type: str, entity_id: str) -> list[dict]:
    """Surface mailpiece/outcome rows from lob_mailer as timeline events."""
    try:
        import lob_mailer
        m = lob_mailer._read()
    except Exception:
        return []
    if m.empty:
        return []
    m = m[(m["entity_type"] == entity_type) & (m["entity_id"].astype(str) == str(entity_id))]
    out = []
    for _, r in m.iterrows():
        status = str(r.get("status", ""))
        when = r.get("responded_at") or r.get("sent_at") or r.get("drafted_at") or ""
        kind = "outcome" if status == "responded" else "mail"
        detail = f"{r.get('piece_type', 'mail') or 'mail'} · {status}"
        if str(r.get("notes", "")).strip():
            detail += f" · {r['notes']}"
        out.append({"ts": str(when), "kind": kind, "detail": detail, "by": str(r.get("by", ""))})
    return out


def timeline(entity_type: str, entity_id: str) -> list[dict]:
    """Merged, newest-first history for one account (logged notes + mailpieces)."""
    rows: list[dict] = []
    df = _read()
    if not df.empty:
        m = df[(df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))]
        rows += m[["ts", "kind", "detail", "by"]].to_dict("records")
    rows += _mail_events(entity_type, entity_id)
    rows = [r for r in rows if str(r.get("ts", "")).strip()]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows


def search(query: str = "", limit: int = 50) -> pd.DataFrame:
    """Search logged activity (detail + org) across all accounts, newest first."""
    df = _read()
    if df.empty:
        return df
    q = str(query or "").strip().lower()
    if q:
        mask = (df["detail"].str.lower().str.contains(q, na=False)
                | df["org_name"].str.lower().str.contains(q, na=False))
        df = df[mask]
    return df.sort_values("ts", ascending=False).head(limit)
