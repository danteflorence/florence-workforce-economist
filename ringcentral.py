"""
RingCentral RingOut — DORMANT until creds are set.

RingOut is server-initiated click-to-call: RingCentral rings the AGENT's phone
first, then bridges to the facility. Click-to-dial (tel: / the RingCentral app)
works without any of this; RingOut just makes it one button inside the app and
lets us pull call records later.

Human-initiated only — never an auto/predictive dialer (an agent clicks per call).

YOU PROVISION (the agent can't): a RingCentral app with JWT auth, then env:
  RINGCENTRAL_CLIENT_ID, RINGCENTRAL_CLIENT_SECRET, RINGCENTRAL_JWT
  RINGCENTRAL_SERVER (optional; default https://platform.ringcentral.com)
Each agent supplies their own phone number in the UI (rings them first).
"""
from __future__ import annotations

import os

SERVER = os.environ.get("RINGCENTRAL_SERVER", "https://platform.ringcentral.com")


def is_configured() -> bool:
    return bool(os.environ.get("RINGCENTRAL_CLIENT_ID") and os.environ.get("RINGCENTRAL_JWT"))


def _access_token() -> tuple[str, str]:
    import base64
    import requests
    cid = os.environ["RINGCENTRAL_CLIENT_ID"]
    sec = os.environ.get("RINGCENTRAL_CLIENT_SECRET", "")
    auth = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = requests.post(
        f"{SERVER}/restapi/oauth/token",
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
              "assertion": os.environ["RINGCENTRAL_JWT"]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"], SERVER


def ringout(*, agent_number: str, to_number: str, caller_id: str = "") -> dict:
    """Ring the agent, then bridge to the facility. Dry-run if not configured.
    Returns {ok, mode, detail}. Never raises."""
    if not is_configured():
        return {"ok": False, "mode": "dry_run",
                "detail": "RingCentral not connected — set RINGCENTRAL_CLIENT_ID/JWT to "
                          "enable one-click RingOut. Click-to-dial still works."}
    if not (str(agent_number).strip() and str(to_number).strip()):
        return {"ok": False, "mode": "failed",
                "detail": "Need your phone number + the facility number for RingOut."}
    try:
        tok, server = _access_token()
        import requests
        body = {"from": {"phoneNumber": agent_number},
                "to": {"phoneNumber": to_number}, "playPrompt": False}
        if caller_id:
            body["callerId"] = {"phoneNumber": caller_id}
        r = requests.post(
            f"{server}/restapi/v1.0/account/~/extension/~/ring-out",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=body, timeout=20,
        )
        ok = r.status_code in (200, 201)
        return {"ok": ok, "mode": "ringout" if ok else "failed",
                "detail": ("Ringing your phone now — answer to connect to the facility."
                           if ok else f"RingCentral {r.status_code}: {r.text[:160]}")}
    except Exception as e:
        return {"ok": False, "mode": "failed", "detail": f"RingOut failed: {e}"}
