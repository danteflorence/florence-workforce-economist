"""
lob_webhook.py
==============
Receiver for Lob tracking events so the platform shows per-piece USPS status
(in_transit → in_local_area → processed_for_delivery → delivered, plus
re-routed / returned_to_sender).

Lob POSTs a JSON event to your webhook URL for every state change. Configure the
URL + which events to send in the Lob dashboard (Settings → Webhooks), then
verify each request with the signature header so nobody can spoof status.

Docs: https://docs.lob.com  (Webhooks / Tracking Events)

Run (dev):
    pip install flask
    export LOB_WEBHOOK_SECRET="whsec_..."   # from the dashboard, per-webhook
    flask --app lob_webhook run --port 8080
Point a tunnel (ngrok/cloudflared) at it, paste the public URL into Lob, send a
test event from the dashboard.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

from flask import Flask, request, abort

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("LOB_WEBHOOK_SECRET", "")
# Reject events whose timestamp is older than this (replay protection).
TOLERANCE_SECONDS = 5 * 60


def verify_signature(req) -> bool:
    """Lob signs each webhook. The signature is HMAC-SHA256 of
    '{timestamp}.{raw_body}' keyed with your webhook secret, compared against
    the `Lob-Signature` header (with `Lob-Signature-Timestamp`)."""
    if not WEBHOOK_SECRET:
        return True  # dev only — NEVER leave the secret unset in production
    ts = req.headers.get("Lob-Signature-Timestamp", "")
    sig = req.headers.get("Lob-Signature", "")
    if not ts or not sig:
        return False
    if abs(time.time() - int(ts)) > TOLERANCE_SECONDS:
        return False  # stale → likely a replay
    signed = f"{ts}.{req.get_data(as_text=True)}".encode()
    expected = hmac.new(WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@app.post("/webhooks/lob")
def lob_webhook():
    if not verify_signature(request):
        abort(401)

    event = request.get_json(force=True, silent=True) or {}
    event_type = event.get("event_type", {}).get("id") or event.get("event_type")
    body = event.get("body", {})              # the postcard (or tracking) resource
    psc_id = body.get("id")
    metadata = body.get("metadata", {})       # ← our ccn / code / theme land here
    ccn = metadata.get("ccn")
    code = metadata.get("code")

    # ----- Wire these to your datastore -----
    # Map Lob's mailpiece + tracking events back onto the facility via metadata.
    # e.g. UPDATE mailings SET status=?, last_event=? WHERE ccn=? OR psc_id=?
    record = {
        "psc_id": psc_id,
        "ccn": ccn,
        "code": code,
        "event_type": event_type,
        "expected_delivery_date": body.get("expected_delivery_date"),
        "received_at": time.time(),
    }
    app.logger.info("Lob event: %s", json.dumps(record))
    # persist(record)   # <- your DB call

    return ("", 200)     # 2xx tells Lob the event was accepted


# Events worth subscribing to in the dashboard:
#   postcard.created, postcard.rendered_pdf, postcard.rendered_thumbnails,
#   postcard.delivered, postcard.in_transit, postcard.in_local_area,
#   postcard.processed_for_delivery, postcard.re-routed, postcard.returned_to_sender
if __name__ == "__main__":
    app.run(port=8080, debug=True)
