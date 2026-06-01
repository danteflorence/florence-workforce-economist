"""
Direct-mail composer + tracker for the AI SDR (Lob).

PRINCIPLE: the SDR *drafts and queues*; a human *sends*. Physical mail costs
money per piece and reaches real organizations, so `draft_and_send` only calls
the Lob API when LOB_API_KEY is set AND `live=True` is explicitly passed;
otherwise it returns a dry-run preview and logs the piece as 'drafted'. Every
action is tracked by org in data/mail_log.csv.

YOU PROVISION (the agent can't): a Lob account + the LOB_API_KEY env var.
Real sending also needs a deliverable street address (enrich via NPPES by NPI,
or rep-entered) — see contacts.py `address1` / `zip`.

Copy is purely the value + activation path. No FICA / IRS / visa / tax language
ever goes on a mailpiece (standing compliance rule).
"""
from __future__ import annotations

import csv
import os
import secrets
import string
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
MAIL_LOG = DATA_DIR / "mail_log.csv"
SIGNUP_BASE = os.environ.get("FLORENCE_SIGNUP_URL", "https://app.florence.health/activate")

FIELDS = [
    "entity_type", "entity_id", "org_name", "piece_type", "retrieval_code",
    "to_name", "address1", "city", "state", "zip", "status", "lob_id",
    "monthly_fee", "term_impact", "drafted_at", "sent_at", "responded_at",
    "by", "notes",
]
# status: drafted | sent | responded | failed


def retrieval_code() -> str:
    """Human-friendly activation code, e.g. FLOR-7QК… (ambiguous chars removed)."""
    alphabet = "".join(c for c in (string.ascii_uppercase + string.digits)
                       if c not in "O0I1")
    return "FLOR-" + "".join(secrets.choice(alphabet) for _ in range(5))


def is_configured() -> bool:
    return bool(os.environ.get("LOB_API_KEY"))


def _ensure() -> None:
    if not MAIL_LOG.exists():
        MAIL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(MAIL_LOG, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure()
    try:
        df = pd.read_csv(MAIL_LOG, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)
    for c in FIELDS:
        if c not in df.columns:
            df[c] = ""
    return df


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.0f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return f"${v:,.0f}"


def compose(*, org_name: str, contact_name: str, monthly_fee, term_impact,
            code: str, piece_type: str = "postcard") -> dict:
    """On-brand, compliance-clean mail copy. The SDR drafts this."""
    url = f"{SIGNUP_BASE}?code={code}"
    body = (
        f"{org_name}: at your current premium-agency spend, Florence projects about "
        f"{_money(term_impact)} of impact over 24 months — the same hours, staffed by "
        f"permanent, internationally educated RNs at {_money(monthly_fee)}/mo. Activate "
        f"your quote and review available candidates with code {code}."
    )
    return {
        "piece_type": piece_type,
        "to": contact_name or "Nursing leadership",
        "headline": "Same shifts. Permanent nurses. A lower number.",
        "body": body,
        "cta": f"Activate at {url}",
        "url": url,
        "code": code,
    }


def _log(**row) -> None:
    _ensure()
    df = _read()
    rec = {c: "" for c in FIELDS}
    rec.update({k: ("" if v is None else str(v)) for k, v in row.items()})
    df = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)
    df.to_csv(MAIL_LOG, index=False, columns=FIELDS)


def draft_and_send(entity_type: str, entity_id: str, *, org_name: str, to_name: str,
                   address1: str, city: str, state: str, zip: str,
                   monthly_fee, term_impact, piece_type: str = "postcard",
                   by: str = "", live: bool = False) -> dict:
    """Draft a mailpiece (always) and send it (only if live + key + address).

    Returns a dict with `ok`, `mode` ('dry_run'|'sent'|'failed'), the retrieval
    `code`, the composed `preview`, and a human `detail`.
    """
    code = retrieval_code()
    preview = compose(org_name=org_name, contact_name=to_name, monthly_fee=monthly_fee,
                      term_impact=term_impact, code=code, piece_type=piece_type)
    now = datetime.utcnow().isoformat(timespec="seconds")
    common = dict(
        entity_type=entity_type, entity_id=str(entity_id), org_name=org_name,
        piece_type=piece_type, retrieval_code=code, to_name=to_name,
        address1=address1, city=city, state=state, zip=zip,
        monthly_fee=monthly_fee, term_impact=term_impact, drafted_at=now, by=by,
    )

    if not (str(address1).strip() and str(zip).strip()):
        return {"ok": False, "reason": "missing_address", "code": code, "preview": preview,
                "detail": "Needs a street address + ZIP (enrich via NPPES, or enter it on the contact)."}

    if not (live and is_configured()):
        _log(status="drafted", **common)
        return {"ok": True, "mode": "dry_run", "code": code, "preview": preview,
                "detail": ("Drafted (dry run). Set LOB_API_KEY and confirm a live send to mail."
                           if not is_configured() else "Drafted — confirm a live send to mail.")}

    # ── live send (human-confirmed) ──────────────────────────────────
    try:
        import requests
        endpoint = "postcards" if piece_type == "postcard" else "letters"
        r = requests.post(
            f"https://api.lob.com/v1/{endpoint}",
            auth=(os.environ["LOB_API_KEY"], ""),
            data={
                "description": f"Florence — {org_name}",
                "to[name]": to_name or org_name,
                "to[address_line1]": address1,
                "to[address_city]": city,
                "to[address_state]": state,
                "to[address_zip]": zip,
                "merge_variables[code]": code,
            },
            timeout=30,
        )
        ok = r.status_code in (200, 201)
        lob_id = r.json().get("id", "") if ok else ""
        _log(status=("sent" if ok else "failed"), sent_at=now, lob_id=lob_id, **common)
        return {"ok": ok, "mode": "sent" if ok else "failed", "code": code,
                "lob_id": lob_id, "preview": preview,
                "detail": None if ok else f"Lob {r.status_code}: {r.text[:200]}"}
    except Exception as e:  # network / missing requests / API error
        _log(status="failed", **common)
        return {"ok": False, "reason": str(e), "code": code, "preview": preview,
                "detail": f"Send failed: {e}"}


def record_response(entity_type: str, entity_id: str, note: str = "") -> bool:
    """Mark the latest mailpiece for an org as responded (they used the code)."""
    df = _read()
    mask = (df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))
    if not mask.any():
        return False
    idx = df[mask].index[-1]
    df.loc[idx, "status"] = "responded"
    df.loc[idx, "responded_at"] = datetime.utcnow().isoformat(timespec="seconds")
    if note:
        df.loc[idx, "notes"] = note
    df.to_csv(MAIL_LOG, index=False, columns=FIELDS)
    return True


def status_for(entity_type: str, entity_id: str) -> dict | None:
    df = _read()
    mask = (df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))
    if not mask.any():
        return None
    return df[mask].iloc[-1].to_dict()


def summary() -> dict:
    df = _read()
    if df.empty:
        return {"total": 0, "drafted": 0, "sent": 0, "responded": 0}
    vc = df["status"].value_counts().to_dict()
    return {"total": int(len(df)), "drafted": int(vc.get("drafted", 0)),
            "sent": int(vc.get("sent", 0)), "responded": int(vc.get("responded", 0))}
