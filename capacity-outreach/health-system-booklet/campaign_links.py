"""
campaign_links.py
=================
Per-system tracked landing-page + QR URLs for the Capacity Outreach mailers.
Every mailpiece gets its OWN URL so a scan/visit is attributable to the system,
campaign, and creative — the top of the Demand Radar → Production Ledger loop.

NO PII in the URL (no contact name/email/phone). Only opaque slugs + campaign/
account ids + UTM tags — same posture as the Demand Radar tracked links.

Default landing host is go.florencern.com (override via FLORENCE_LINK_BASE).
QR images are not generated here: the renderer/Lob produce the QR from `qr_url`
(the booklet build page uses qrcode-generator; Lob can place a native trackable QR).
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlencode

LINK_BASE = os.environ.get("FLORENCE_LINK_BASE", "https://go.florencern.com").rstrip("/")


def slugify(value: str) -> str:
    """Opaque, URL-safe slug from a system name / id (no PII)."""
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "system"


def build_capacity_url(
    *,
    account_slug: str,
    segment: str = "health_system",          # health_system | home_health | snf | dialysis | hospice | asc
    path: str = "sprint",                     # landing route, e.g. sprint | capacity | claim
    campaign_id: str = "",
    account_id: str = "",
    medium: str = "booklet",                  # booklet | mailer | postcard | email
    campaign: str = "",                       # human campaign label, e.g. health_system_capacity_q3
    content: str = "",                        # creative variant, e.g. hca_teal_8pp
    base: str | None = None,
) -> str:
    """A per-system tracked URL: <base>/<segment-path>/<slug>?utm…&frn_campaign_id…&frn_account_id…"""
    root = (base or LINK_BASE).rstrip("/")
    seg = segment.replace("_", "-")
    url = f"{root}/{seg}/{slugify(account_slug)}/{path}".rstrip("/")
    params = {
        "utm_source": "direct_mail",
        "utm_medium": medium,
        "utm_campaign": campaign or f"{segment}_capacity",
        "utm_content": content or f"{slugify(account_slug)}_{medium}",
    }
    if campaign_id:
        params["frn_campaign_id"] = campaign_id
    if account_id:
        params["frn_account_id"] = account_id
    return f"{url}?{urlencode(params)}"


def links_for_system(
    system: dict,
    *,
    segment: str = "health_system",
    campaign_id: str = "",
    campaign: str = "",
    theme: str = "teal",
) -> dict:
    """Return {landing_url, qr_url} for one system row. qr_url == landing_url
    (the QR encodes the tracked landing page)."""
    slug = slugify(system.get("id") or system.get("name") or "system")
    url = build_capacity_url(
        account_slug=slug, segment=segment, campaign_id=campaign_id,
        account_id=system.get("id", slug), campaign=campaign,
        content=f"{slug}_{theme}_8pp",
    )
    return {"landing_url": url, "qr_url": url}


if __name__ == "__main__":
    print(build_capacity_url(account_slug="HCA Healthcare", campaign_id="cmp_123",
                             account_id="acct_hca", campaign="health_system_capacity_q3",
                             content="hca_teal_8pp"))
    print(build_capacity_url(account_slug="Valley Home Health, LA", segment="home_health",
                             path="capacity", campaign="home_health_california_q3"))
