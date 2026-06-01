"""
Sales intelligence — prioritize the book, de-dupe touches, pace the cadence.

Three read-only helpers layered over lob_mailer (mail_log) + contacts:

  • reachability(contact)  → how completely we can reach an account (named
    contact / phone / email / mailable street address). Doubles as a
    "go-find-the-missing-piece" signal on otherwise high-value targets.
  • rank_systems(...)      → order systems by savings × reachability so reps
    work the highest-yield, most-reachable accounts first.
  • touch history + cadence → one coordinated sequence per SYSTEM (mail → email
    → email → call), surfaced as the next-best touch + when it's due, so a
    system isn't blasted twice.

No side effects — pure functions over the existing stores.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional

# Reachability weights — what actually lets a rep make contact.
_W = {"named": 0.30, "phone": 0.25, "email": 0.25, "mailable": 0.20}


def reachability(contact: dict) -> dict:
    """Score 0–100 of how completely we can reach an account, + what's missing."""
    contact = contact or {}
    have = {
        "named": bool(str(contact.get("contact_name", "")).strip()),
        "phone": bool(str(contact.get("phone", "")).strip()),
        "email": bool(str(contact.get("email", "")).strip()),
        "mailable": bool(contact.get("mailable")),
    }
    score = sum(_W[k] for k, v in have.items() if v)
    pct = round(score * 100)
    if pct >= 80:
        label = "Reachable"
    elif pct >= 40:
        label = "Partial"
    else:
        label = "No contact"
    missing = [k for k in ("email", "phone", "mailable", "named") if not have[k]]
    return {"score": score, "pct": pct, "label": label, "have": have, "missing": missing}


def priority_score(term_savings, reach_score: float) -> float:
    """Blend customer impact with reachability. Big savings still rank, but a
    reachable account of equal size outranks one we can't contact yet."""
    try:
        s = float(term_savings or 0)
    except (TypeError, ValueError):
        s = 0.0
    return s * (0.4 + 0.6 * float(reach_score or 0))


def rank_systems(records: list[dict], get_contact: Callable[[str, str], dict],
                 limit: int = 30) -> list[dict]:
    """Rank system records (each: health_system_id, health_system,
    term_savings_target, rn_need, monthly_fee_target) by priority.

    To bound cost, we take the top `limit` by raw savings, then score those by
    savings × reachability and re-sort.
    """
    pre = sorted(records, key=lambda r: float(r.get("term_savings_target") or 0),
                 reverse=True)[:limit]
    out = []
    for r in pre:
        sid = str(r.get("health_system_id", ""))
        reach = reachability(get_contact("system", sid))
        out.append({
            "system_id": sid,
            "name": str(r.get("health_system", sid)),
            "term_savings": float(r.get("term_savings_target") or 0),
            "rn_need": int(r.get("rn_need") or 0),
            "monthly_fee": float(r.get("monthly_fee_target") or 0),
            "reach_pct": reach["pct"],
            "reach_label": reach["label"],
            "missing": reach["missing"],
            "score": priority_score(r.get("term_savings_target"), reach["score"]),
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


# ─── Touch history + de-dupe (system-level) ─────────────────────────
def _parse(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def touch_history(entity_type: str, entity_id: str) -> list[dict]:
    """All logged mailpieces for one account, oldest→newest. Empty on any error."""
    try:
        import lob_mailer
        df = lob_mailer._read()
    except Exception:
        return []
    if df.empty:
        return []
    m = df[(df["entity_type"] == entity_type)
           & (df["entity_id"].astype(str) == str(entity_id))]
    return m.to_dict("records")


def already_touched(entity_type: str, entity_id: str) -> Optional[dict]:
    """Summary of the most recent touch, or None. Drives the de-dupe banner so a
    system gets one coordinated sequence rather than duplicate sends."""
    hist = touch_history(entity_type, entity_id)
    if not hist:
        return None
    last = hist[-1]
    when = last.get("sent_at") or last.get("drafted_at") or ""
    return {
        "count": len(hist),
        "status": last.get("status", ""),
        "piece_type": last.get("piece_type", ""),
        "when": str(when)[:10],
        "code": last.get("retrieval_code", ""),
        "responded": any(r.get("status") == "responded" for r in hist),
    }


# ─── Cadence — the next coordinated touch + when it's due ────────────
# Day gaps between touches. Index = number of touches already made.
_CADENCE = [
    {"label": "Send the intro — branded letter or the prefilled email", "channel": "mail/email", "gap": 0},
    {"label": "Follow-up email referencing the savings number", "channel": "email", "gap": 3},
    {"label": "Second follow-up — share a couple of meeting windows", "channel": "email", "gap": 4},
    {"label": "Call the named contact", "channel": "phone", "gap": 6},
]


def cadence_next(entity_type: str, entity_id: str, now: Optional[datetime] = None) -> dict:
    """Suggest the next touch + when it's due, based on logged history.

    NOTE: only logged mailpieces count toward the sequence; emails a rep sends
    from their own inbox aren't tracked here, so treat this as a floor.
    """
    now = now or datetime.utcnow()
    hist = touch_history(entity_type, entity_id)
    if any(r.get("status") == "responded" for r in hist):
        return {"label": "They responded — move to the deal pipeline.", "channel": "",
                "ready": False, "due_in_days": None, "done": True}
    count = len(hist)
    if count >= len(_CADENCE):
        return {"label": "Sequence complete — pause, or mark not-interested.",
                "channel": "", "ready": False, "due_in_days": None, "done": True}
    step = _CADENCE[count]
    if count == 0:
        return {"label": step["label"], "channel": step["channel"], "ready": True,
                "due_in_days": 0, "done": False, "step": 1}
    last_when = None
    for r in reversed(hist):
        last_when = _parse(r.get("sent_at") or r.get("drafted_at") or "")
        if last_when:
            break
    if last_when is None:
        due_in = 0
    else:
        due_date = last_when + timedelta(days=step["gap"])
        due_in = (due_date.date() - now.date()).days
    return {"label": step["label"], "channel": step["channel"],
            "ready": due_in <= 0, "due_in_days": due_in, "done": False, "step": count + 1}
