"""
ATS Connect handoff — closed-won deals flow into the production system.

When a deal closes won in the Workbench, the full deal payload is queued
durably to data/ats_outbox.jsonl (backed up by ops_backup). Delivery to
ATS Connect is gated and best-effort:

    ATS_HANDOFF_ENABLED=1                     turn delivery on (default OFF)
    ATS_HANDOFF_URL=https://.../api/ops/demand/intake/closed-won
    ATS_HANDOFF_TOKEN=<bearer>                Core-minted M2M token

Payload contract (what the ATS intake endpoint receives):
    {
      "kind": "economist.closed_won",
      "ts": "...", "deal_id": "...", "rep_email": "...",
      "system_id": "...", "system_name": "...",
      "agreed_fee_per_rn_mo": 1850.0, "engine_quote_per_rn_mo": 1852.75,
      "n_rns": 40, "notes": "..."
    }

Design notes: queuing NEVER blocks or fails the close flow; delivery marks
entries delivered/failed with attempt counts and retries on the next close
(or via `python3 ats_handoff.py flush`). Reservations in ATS are per demand
job, so the intake side (not this side) decides how a won account maps to
jobs — this module only guarantees the signal arrives durably.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUTBOX = Path(__file__).resolve().parent / "data" / "ats_outbox.jsonl"
MAX_ATTEMPTS = 10


def _enabled() -> bool:
    return (os.environ.get("ATS_HANDOFF_ENABLED", "").lower() in ("1", "true", "yes")
            and bool(os.environ.get("ATS_HANDOFF_URL", "").strip()))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def queue_closed_won(deal: dict, *, agreed_fee_per_rn_mo=None,
                     engine_quote_per_rn_mo=None, n_rns=None,
                     notes: str = "") -> None:
    """Durably queue a closed-won event. Never raises into the close flow."""
    try:
        entry = {
            "kind": "economist.closed_won",
            "ts": _now(),
            "deal_id": deal.get("deal_id", ""),
            "rep_email": deal.get("rep_email", ""),
            "system_id": deal.get("system_id", ""),
            "system_name": deal.get("system_name", ""),
            "agreed_fee_per_rn_mo": agreed_fee_per_rn_mo,
            "engine_quote_per_rn_mo": engine_quote_per_rn_mo,
            "n_rns": n_rns,
            "notes": notes,
            "status": "queued",
            "attempts": 0,
        }
        OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    # Opportunistic delivery; a failure just leaves the entry queued.
    try:
        flush(timeout=5)
    except Exception:
        pass


def _post(entry: dict, timeout: int) -> bool:
    url = os.environ["ATS_HANDOFF_URL"].strip()
    payload = {k: v for k, v in entry.items() if k not in ("status", "attempts")}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"content-type": "application/json",
                 **({"authorization": f"Bearer {t}"}
                    if (t := os.environ.get("ATS_HANDOFF_TOKEN", "").strip()) else {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return 200 <= resp.status < 300


def flush(timeout: int = 15) -> dict:
    """Attempt delivery of queued entries. Returns counts; safe to call anytime."""
    if not OUTBOX.exists():
        return {"queued": 0, "delivered": 0, "failed": 0, "enabled": _enabled()}
    entries = [json.loads(l) for l in OUTBOX.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    if not _enabled():
        n_q = sum(1 for e in entries if e.get("status") == "queued")
        return {"queued": n_q, "delivered": 0, "failed": 0, "enabled": False}
    delivered = failed = 0
    for e in entries:
        if e.get("status") != "queued" or e.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        try:
            ok = _post(e, timeout)
        except Exception:
            ok = False
        e["attempts"] = e.get("attempts", 0) + 1
        if ok:
            e["status"], e["delivered_at"] = "delivered", _now()
            delivered += 1
        else:
            failed += 1
    with open(OUTBOX, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    n_q = sum(1 for e in entries if e.get("status") == "queued")
    return {"queued": n_q, "delivered": delivered, "failed": failed, "enabled": True}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "flush":
        print(json.dumps(flush(), indent=2))
    else:
        print(__doc__)
