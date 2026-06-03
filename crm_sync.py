"""
CRM + Gmail integration — DORMANT until YOU provision keys.

Two complementary surfaces, same posture as the Lob mailer (the agent never
auto-sends and never creates accounts):

  • Gmail  → create a DRAFT in the authorized mailbox (never send). The rep opens
    Gmail, reviews, and hits send — so deliverability + replies stay in their
    inbox. Needs the gmail.compose scope + a stored OAuth token.
  • Streak → find-or-create a box in a pipeline and stamp the deal numbers, so
    the CRM (which lives inside Gmail) is the system of record.

Every function is defensive: with nothing configured it returns a dry-run dict
({"ok": False, "mode": "dry_run", "detail": ...}) and NEVER raises, so the app
runs unchanged until the keys land.

YOU PROVISION (env vars, never committed):
  Gmail   GMAIL_TOKEN_FILE   path to a token.json from a one-time
                             google-auth-oauthlib flow (scope gmail.compose).
                             Shares the Google OAuth client from florence_auth.
          GMAIL_SENDER       optional From: address.
  Streak  STREAK_API_KEY     Streak → Settings → Integrations → API key.
          STREAK_PIPELINE_KEY  target pipeline key.
"""
from __future__ import annotations

import json
import os
from typing import Optional

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
STREAK_BASE = os.environ.get("STREAK_BASE", "https://www.streak.com/api/v1")


def _dry(detail: str, **extra) -> dict:
    return {"ok": False, "mode": "dry_run", "detail": detail, **extra}


# ════════════════════════════════════════════════════════════════════
# Gmail — create a draft (never send)
# ════════════════════════════════════════════════════════════════════
def gmail_is_configured() -> bool:
    tok = os.environ.get("GMAIL_TOKEN_FILE", "")
    if not tok or not os.path.exists(tok):
        return False
    try:
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        return True
    except Exception:
        return False


def _gmail_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(
        os.environ["GMAIL_TOKEN_FILE"], GMAIL_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def create_gmail_draft(*, to: str, subject: str, body: str,
                       sender: Optional[str] = None) -> dict:
    """Create a Gmail DRAFT (not a send). Dry-run if not configured."""
    if not str(to).strip():
        return _dry("No recipient email on the contact — add one to draft.")
    if not gmail_is_configured():
        return _dry("Gmail not connected — set GMAIL_TOKEN_FILE (scope "
                    "gmail.compose) to draft into your inbox.")
    try:
        import base64
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        if sender or os.environ.get("GMAIL_SENDER"):
            msg["From"] = sender or os.environ["GMAIL_SENDER"]
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        svc = _gmail_service()
        draft = svc.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}).execute()
        return {"ok": True, "mode": "draft", "id": draft.get("id", ""),
                "url": "https://mail.google.com/mail/u/0/#drafts",
                "detail": "Draft created in your Gmail → Drafts. Review and send."}
    except Exception as e:
        return {"ok": False, "mode": "failed", "detail": f"Gmail draft failed: {e}"}


# ════════════════════════════════════════════════════════════════════
# Streak — find-or-create a box, stamp the deal numbers
# ════════════════════════════════════════════════════════════════════
def streak_is_configured() -> bool:
    return bool(os.environ.get("STREAK_API_KEY") and os.environ.get("STREAK_PIPELINE_KEY"))


def _streak_get(path: str):
    import requests
    r = requests.get(f"{STREAK_BASE}{path}",
                     auth=(os.environ["STREAK_API_KEY"], ""), timeout=20)
    r.raise_for_status()
    return r.json()


def _streak_post(path: str, payload: dict):
    import requests
    r = requests.post(f"{STREAK_BASE}{path}",
                      auth=(os.environ["STREAK_API_KEY"], ""), json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def streak_upsert_box(*, name: str, fields: Optional[dict] = None,
                      notes: str = "") -> dict:
    """Find-or-create a box by name in STREAK_PIPELINE_KEY, then write a notes
    summary of the deal numbers. Dry-run if not configured.

    (Structured custom-field writes need per-pipeline field keys; we keep v1 to
    notes + name so it works against any pipeline without configuration.)
    """
    if not streak_is_configured():
        return _dry("Streak not connected — set STREAK_API_KEY + "
                    "STREAK_PIPELINE_KEY to log this account to your pipeline.")
    try:
        pk = os.environ["STREAK_PIPELINE_KEY"]
        boxes = _streak_get(f"/pipelines/{pk}/boxes") or []
        existing = next((b for b in boxes
                         if str(b.get("name", "")).strip().lower() == name.strip().lower()), None)
        if existing:
            box = existing
            created = False
        else:
            box = _streak_post(f"/pipelines/{pk}/boxes", {"name": name})
            created = True
        box_key = box.get("boxKey") or box.get("key") or box.get("boxId") or ""
        summary = notes or _fields_to_notes(fields or {})
        if box_key and summary:
            _streak_post(f"/boxes/{box_key}", {"notes": summary})
        return {"ok": True, "mode": "created" if created else "updated",
                "box_key": box_key,
                "detail": f"{'Created' if created else 'Updated'} Streak box '{name}'."}
    except Exception as e:
        return {"ok": False, "mode": "failed", "detail": f"Streak sync failed: {e}"}


def _money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:,.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.2f}K"
    return f"${v:,.2f}"


def _fields_to_notes(f: dict) -> str:
    parts = []
    if f.get("annual_savings") is not None:
        parts.append(f"Est. annual savings: {_money(f['annual_savings'])}")
    if f.get("monthly_fee") is not None:
        parts.append(f"Florence fee: {_money(f['monthly_fee'])}/mo")
    if f.get("rn_need"):
        parts.append(f"RN need: {int(f['rn_need']):,}")
    if f.get("stage"):
        parts.append(f"Stage: {f['stage']}")
    if f.get("code"):
        parts.append(f"Retrieval code: {f['code']}")
    parts.append("Logged from Florence Workforce Economist.")
    return " · ".join(parts)


# ════════════════════════════════════════════════════════════════════
# Unified one-call touch (used by the docs popup)
# ════════════════════════════════════════════════════════════════════
def log_touch(*, org_name: str, email_to: str = "", subject: str = "", body: str = "",
              fields: Optional[dict] = None, do_gmail: bool = True,
              do_streak: bool = True) -> dict:
    """Optionally draft the email in Gmail AND log the box in Streak."""
    out = {}
    if do_gmail:
        out["gmail"] = create_gmail_draft(to=email_to, subject=subject, body=body)
    if do_streak:
        out["streak"] = streak_upsert_box(name=org_name, fields=fields)
    return out


def status() -> dict:
    return {"gmail": gmail_is_configured(), "streak": streak_is_configured()}
