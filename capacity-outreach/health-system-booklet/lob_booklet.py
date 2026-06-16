"""
lob_booklet.py
==============
Send the personalized Florence Health-System Capacity booklet (9x6", 8pp) through
Lob's **Campaigns API** — the right surface for a large, mail-merged booklet run.

Why Campaigns (not the single Print&Mail call we used for postcards):
  - Booklets are an Enterprise-Edition format.
  - You have thousands of recipients, each with their OWN per-system merge vars
    ({{system_name}}, {{rn_need}}, {{n_facilities}}, {{list_rate}}, {{effective_cost}},
    plus the tracked {{landing_url}}/{{qr_url}}).
  - The Campaigns API takes an HTML template + a CSV audience and fans out the
    merge for you, with one cancel window over the whole run.

Pipeline (each step is a documented Lob endpoint):
  1. POST /v1/templates              → save the booklet HTML, get tmpl_id
  2. POST /v1/campaigns              → name, schedule_type, use_type, cancel window
  3. POST /v1/creatives             → attach the booklet creative (references tmpl_id)
  4. POST /v1/uploads               → declare address + merge-variable column mapping
  5. POST /v1/uploads/{id}/file     → upload the audience CSV (byte stream)
  6. POST /v1/campaigns/{id}/send   → execute (or schedule)

Auth: HTTP Basic, API key as username, blank password (same as postcards).
Install: pip install requests

⚠️ ENTERPRISE + ACCOUNT-SPECIFIC FIELDS
   Booklets require Enterprise Edition and the booklet creative payload
   (resource_type, page count, address-placement) is provisioned per account.
   Fields marked `# CONFIRM` below must be verified against your Lob booklet
   spec / account team before a live run. Everything else follows the public
   Campaigns API.
"""
from __future__ import annotations

import os
import requests

BASE = "https://api.lob.com/v1"


def _auth():
    return (os.environ["LOB_API_KEY"], "")


# ──────────────────────────────────────────────────────────────────────────
# 1. Save the booklet HTML as a Lob template (returns a template id + version)
# ──────────────────────────────────────────────────────────────────────────
def create_template(html: str, description: str = "Florence Hospital Network booklet"):
    r = requests.post(f"{BASE}/templates", auth=_auth(),
                      data={"description": description, "html": html}, timeout=30)
    r.raise_for_status()
    t = r.json()
    return t["id"], t.get("published_version", {}).get("id")


# ──────────────────────────────────────────────────────────────────────────
# 2. Create the campaign (one cancel window governs the whole run)
# ──────────────────────────────────────────────────────────────────────────
def create_campaign(name: str, cancel_window_minutes: int = 120):
    r = requests.post(f"{BASE}/campaigns", auth=_auth(), json={
        "name": name,
        "schedule_type": "immediate",          # or set a future ISO-8601 send time
        "use_type": "marketing",               # REQUIRED
        "cancel_window_campaign_minutes": str(cancel_window_minutes),
    }, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


# ──────────────────────────────────────────────────────────────────────────
# 3. Attach the booklet creative (references the saved template)
# ──────────────────────────────────────────────────────────────────────────
def create_creative(campaign_id: str, template_id: str, *, size="9x6", pages=8):
    payload = {
        "campaign_id": campaign_id,
        "resource_type": "booklet",            # CONFIRM exact value for your account
        "from": {                              # printed return address
            "name": "Florence",
            "address_line1": "4130 Overland Ave",
            "address_city": "Culver City",
            "address_state": "CA",
            "address_zip": "90230",
        },
        "details": {                           # CONFIRM booklet detail keys w/ Lob
            "html_template_id": template_id,
            "size": size,                      # 9x6 personalizable booklet
            "pages": pages,                    # 8 / 12 / 16
        },
    }
    r = requests.post(f"{BASE}/creatives", auth=_auth(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


# ──────────────────────────────────────────────────────────────────────────
# 4. Declare the audience upload (address + merge-variable column mapping)
#    Your CSV columns → Lob fields. The merge-variable mapping MUST match the
#    columns hospital_audience.build_audience_csv writes (and the {{vars}} in the
#    booklet template), or Lob silently fails to merge. `upload_payload` is a
#    pure builder so the contract can be asserted offline (see verify_capacity_outreach).
# ──────────────────────────────────────────────────────────────────────────
def upload_payload(campaign_id: str) -> dict:
    return {
        "campaignId": campaign_id,
        "requiredAddressColumnMapping": {
            "name": "contact_name",
            "address_line1": "address_line1",
            "address_city": "address_city",
            "address_state": "address_state",
            "address_zip": "address_zip",
        },
        "optionalAddressColumnMapping": {
            "company": "system_name",          # print the health system as the company line
            "address_line2": "address_line2",
        },
        # Per-system booklet merge variables (must equal hospital_audience.MERGE_COLS).
        "mergeVariableColumnMapping": {
            "system_name": "system_name",
            "short_name": "short_name",
            "effective_cost": "effective_cost",
            "list_rate": "list_rate",
            "rn_need": "rn_need",
            "n_facilities": "n_facilities",
            "landing_url": "landing_url",       # per-system tracked landing page (UTM)
            "qr_url": "qr_url",                 # per-system tracked QR target
        },
    }


def create_upload(campaign_id: str):
    r = requests.post(f"{BASE}/uploads", auth=_auth(), json=upload_payload(campaign_id), timeout=30)
    r.raise_for_status()
    return r.json()["id"]


# ──────────────────────────────────────────────────────────────────────────
# 5. Upload the audience CSV as a byte stream
# ──────────────────────────────────────────────────────────────────────────
def upload_file(upload_id: str, csv_path: str):
    with open(csv_path, "rb") as f:
        r = requests.post(f"{BASE}/uploads/{upload_id}/file", auth=_auth(),
                          files={"file": (os.path.basename(csv_path), f, "text/csv")},
                          timeout=120)
    r.raise_for_status()
    return r.json()


# ──────────────────────────────────────────────────────────────────────────
# 6. Execute (or schedule) the campaign
# ──────────────────────────────────────────────────────────────────────────
def send_campaign(campaign_id: str):
    r = requests.post(f"{BASE}/campaigns/{campaign_id}/send", auth=_auth(),
                      json={"use_type": "marketing"}, timeout=30)
    r.raise_for_status()
    return r.json()


# ──────────────────────────────────────────────────────────────────────────
# Orchestration — dry_run builds everything EXCEPT the final send.
# ──────────────────────────────────────────────────────────────────────────
def run_booklet_campaign(*, template_html: str, csv_path: str,
                         campaign_name: str, label="hospital",
                         size="9x6", pages=8, dry_run: bool = True):
    template_id, _ = create_template(template_html,
                                     f"Florence Hospital booklet — {label}")
    campaign_id = create_campaign(campaign_name)
    creative_id = create_creative(campaign_id, template_id, size=size, pages=pages)
    upload_id = create_upload(campaign_id)
    upload_file(upload_id, csv_path)

    info = {"campaign_id": campaign_id, "template_id": template_id,
            "creative_id": creative_id, "upload_id": upload_id}
    if dry_run:
        info["status"] = "BUILT — not sent. Review in the Lob dashboard, then call send_campaign()."
        return info
    info["send"] = send_campaign(campaign_id)
    info["status"] = "SENT"
    return info


if __name__ == "__main__":
    # 1) build the template with build_hospital_booklet.html (Download Lob template)
    # 2) build the audience CSV with hospital_audience.build_audience_csv(...)
    # 3) run this (dry_run=True builds the campaign without sending)
    html = open("florence-hospital-booklet-teal.html", encoding="utf-8").read()
    out = run_booklet_campaign(
        template_html=html,
        csv_path="hospital_run.csv",
        campaign_name="Florence Hospital Booklet — Tier 1",
        label="teal",
        dry_run=True,               # builds the campaign; does NOT send
    )
    import json
    print(json.dumps(out, indent=2))
