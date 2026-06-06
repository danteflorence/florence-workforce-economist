"""
lob_send.py
===========
Thin, correct wrapper over Lob's Print & Mail API for the Florence non-hospital
postcard. Verified against https://docs.lob.com (Postcards › Create).

What it does
------------
1. Renders the themed front/back HTML via `florence_postcard.render_postcard`.
2. POSTs to https://api.lob.com/v1/postcards with HTTP Basic auth.
3. Passes the recipient address INLINE — Lob verifies + standardizes every US
   address for free and returns the corrected version (no separate NPPES step
   required, though you can still pre-clean if you like).
4. Sends an Idempotency-Key so a retried batch never double-mails a facility.

Design ↔ API mapping (all confirmed in the Lob docs)
----------------------------------------------------
  render_postcard().front  -> `front`  (HTML string, rendered to `size`)
  render_postcard().back   -> `back`   (HTML string; address zone left BLANK —
                                        Lob prints address + IMb barcode there)
  facility address         -> `to`     (inline; Lob verifies/corrects)
  Florence return address  -> `from`
  size "6x11"/"6x9"        -> `size`
  "marketing"              -> `use_type`   (REQUIRED by Lob)
  ccn + code + quote       -> `metadata`   (for match-back / tracking)

Auth
----
  export LOB_API_KEY="test_xxx"   # test key: renders a real preview PDF, no mail, no charge
  # then, only for the approved segment:
  export LOB_API_KEY="live_xxx"

Install:  pip install requests "qrcode[pil]"
"""
from __future__ import annotations

import os
import uuid

import requests

from florence_postcard import render_postcard


def code_for(ccn: str) -> str:
    """Deterministic activation code per facility (matches the preview tool).
    Stable for a given CCN, so re-runs reuse the same FLOR-XXXXX code."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    h = 2166136261
    for ch in str(ccn):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    out = ""
    for _ in range(5):
        h = (h * 1103515245 + 12345) & 0xFFFFFFFF
        out += alphabet[h % len(alphabet)]
    return "FLOR-" + out

LOB_BASE = "https://api.lob.com/v1/postcards"

# Florence return address (printed by Lob in the return-address slot).
FROM_ADDRESS = {
    "name": "Florence",
    "address_line1": "4130 Overland Ave",
    "address_city": "Culver City",
    "address_state": "CA",
    "address_zip": "90230",
}


def send_postcard(
    *,
    # ── recipient (from your non_hospital_facilities row) ──
    org_name: str,
    facility_type: str,
    city: str,
    state: str,
    zip: str,
    address_line1: str,
    contact_name: str = "",          # e.g. "Director of Nursing"
    address_line2: str = "",
    ccn: str = "",
    # ── quote (from non_hospital_pricing) ──
    fee_per_rn_month: float = 0,
    rn_estimate: int = 5,
    code: str = "",
    # ── creative options ──
    theme: str = "teal",             # "teal" | "purple"
    color_mix: str = "split",        # "accent" | "split" | "duotone"
    headline: str = "quote",         # "quote" | "market"
    size: str = "6x11",              # "6x11" | "6x9"
    mail_type: str = "usps_first_class",   # or "usps_standard" (cheaper, 6x9/6x11 only)
    native_qr: bool = False,         # True = Lob places a trackable QR (scan analytics in dashboard)
    # ── safety ──
    live: bool = False,              # False = build the request + return it, DO NOT POST
    api_key: str | None = None,
    session: requests.Session | None = None,
) -> dict:
    """Render + (optionally) mail one postcard.

    With `live=False` (default) this returns the exact payload WITHOUT calling
    Lob — use it to dry-run a whole batch and eyeball the count before spending
    a cent. With `live=True` it POSTs and returns Lob's postcard object
    (including the signed preview `url` and `expected_delivery_date`).
    """
    pieces = render_postcard(
        org_name=org_name, facility_type=facility_type, city=city, state=state,
        fee_per_rn_month=fee_per_rn_month, rn_estimate=rn_estimate, code=code,
        theme=theme, color_mix=color_mix, headline=headline, size=size,
        qr_mode="reserve" if native_qr else "embedded",
        include_address_preview=False,   # production: leave Lob's address zone clear
    )

    payload = {
        "description": f"Florence — {org_name}",
        "to": {
            # Facility name on its own line, contact above it (Lob prints both).
            "company": org_name[:40],
            "name": (contact_name or "Administrator")[:40],
            "address_line1": address_line1,
            "address_line2": address_line2,
            "address_city": city,
            "address_state": state,
            "address_zip": str(zip),
        },
        "from": FROM_ADDRESS,
        "front": pieces["front"],
        "back": pieces["back"],
        "size": size,
        "use_type": "marketing",          # REQUIRED by Lob
        "mail_type": mail_type,
        "metadata": {                      # shows up on the postcard object + webhooks
            "ccn": str(ccn)[:40],
            "code": code[:40],
            "theme": theme,
            "fee_per_rn_month": str(int(fee_per_rn_month or 0)),
        },
    }

    if native_qr:
        # Lob renders + tracks the QR itself and hosts the redirect for scan
        # analytics. Position is from the BACK's top-left, in inches; these line
        # up with the reserved QR box in the creative. VERIFY with a test print
        # and nudge if needed — printer trim varies slightly.
        payload["qr_code"] = {
            "position": "relative",
            "redirect_url": f"{os.environ.get('FLORENCE_SIGNUP_URL', 'https://florenceedu.com/activate')}?code={code}",
            "width": "1.33",
            "top": "3.55",
            "left": "0.62",
            "pages": "back",
        }

    if not live:
        return {"_dry_run": True, "payload_preview": {
            "to": payload["to"], "size": size, "use_type": "marketing",
            "mail_type": mail_type, "metadata": payload["metadata"],
            "front_bytes": len(pieces["front"]), "back_bytes": len(pieces["back"]),
        }}

    key = api_key or os.environ["LOB_API_KEY"]
    # Idempotency-Key: a retried batch with the same key never double-mails.
    idem = f"florence-{ccn or code or uuid.uuid4().hex}-{size}-{theme}-{color_mix}"
    s = session or requests
    resp = s.post(
        LOB_BASE,
        auth=(key, ""),                    # API key as username, blank password
        headers={"Idempotency-Key": idem},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Batch runner — dry-run the whole segment first, then flip live on approval.
# ─────────────────────────────────────────────────────────────────────────────
def run_segment(rows, *, live=False, **creative):
    """`rows` is any iterable of dicts with the facility + quote fields below.
    Returns a list of results (dry-run previews or Lob postcard objects)."""
    out = []
    with requests.Session() as session:
        for r in rows:
            out.append(send_postcard(
                org_name=r["name"], facility_type=r["facility_type"],
                city=r["city"], state=r["state"], zip=r["zip"],
                address_line1=r.get("address1", ""), contact_name=r.get("contact", ""),
                ccn=r.get("ccn", ""),
                fee_per_rn_month=r["florence_fee_per_rn_month"],
                rn_estimate=int(r.get("rn_estimate", 5)),
                code=r.get("code") or code_for(r.get("ccn", "")),
                live=live, session=session, **creative,
            ))
    return out


if __name__ == "__main__":
    # Smoke test — dry run, no network, no charge.
    demo = dict(
        name="Beatriz Home Health Care Inc", facility_type="HHA",
        city="Miami Beach", state="FL", zip="33140",
        address1="4308 Alton Rd, Ste 210", contact="Director of Nursing",
        ccn="109167", florence_fee_per_rn_month=1178, rn_estimate=10,
        code="FLOR-YZEPC",
    )
    res = run_segment([demo], live=False, theme="teal", color_mix="split", headline="quote")
    import json
    print(json.dumps(res, indent=2))
