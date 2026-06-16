"""
hospital_audience.py
====================
Build the Lob audience CSV for the Florence Hospital Booklet campaign.

Each row carries the recipient address PLUS every merge variable the booklet
template expects. All number formatting + the short-name logic happen HERE
(Lob can't run JS), so the template just slots strings in.

Merge variables (must match build_hospital_booklet.html):
    {{system_name}}    full system name, e.g. "Cleveland Clinic"
    {{short_name}}     shortened for body copy, e.g. "Cleveland"
    {{effective_cost}} "$542"   (effective monthly cost / RN, modeled for the market)
    {{list_rate}}      "$1,079" (list monthly rate / RN)
    {{rn_need}}        "41,294" (estimated total RN need)
    {{n_facilities}}   "158"

Input `systems`: iterable of dicts with at least:
    id, name, nFacilities, totalRnNeed, medianFee, effectiveLow,
    contact_name, address_line1, address_city, address_state, address_zip
(address_line2 optional). Pull economics from your hospital_universe; pull
addresses from your CRM / facility HQ list.

Usage:
    from hospital_audience import build_audience_csv
    build_audience_csv(rows, "hospital_run.csv")
"""
from __future__ import annotations

import csv
import re

from campaign_links import links_for_system


def short_name(name: str) -> str:
    """Mirror of SH()/shortName() in hospital-booklet.js."""
    s = re.sub(r"\s+(Health System|Healthcare|Health Care|Health|System|Corporation)$", "", name).strip()
    if len(s) > 26:
        s = " ".join(name.split()[:2])
    return s or name


def _usd(v) -> str:
    return "$" + format(int(round(float(v or 0))), ",d")


def _num(v) -> str:
    return format(int(round(float(v or 0))), ",d")


# Per-system merge variables (MUST equal lob_booklet.upload_payload mergeVariableColumnMapping
# keys + the {{vars}} in the booklet template). landing_url/qr_url are per-system tracked links.
MERGE_COLS = ["system_name", "short_name", "effective_cost", "list_rate", "rn_need", "n_facilities",
              "landing_url", "qr_url"]
ADDR_COLS = ["contact_name", "address_line1", "address_line2",
             "address_city", "address_state", "address_zip"]


def build_audience_csv(systems, out_path="hospital_run.csv", *,
                       segment="health_system", campaign_id="", campaign="", theme="teal"):
    """Write the Lob audience CSV. Each row carries the address, the six economics
    merge vars (pre-formatted), and a per-system tracked landing_url/qr_url (UTM, no PII)."""
    cols = ADDR_COLS + MERGE_COLS
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in systems:
            links = links_for_system(s, segment=segment, campaign_id=campaign_id, campaign=campaign, theme=theme)
            w.writerow({
                "contact_name": s.get("contact_name", "Chief Nursing Officer"),
                "address_line1": s.get("address_line1", ""),
                "address_line2": s.get("address_line2", ""),
                "address_city": s.get("address_city", ""),
                "address_state": s.get("address_state", ""),
                "address_zip": str(s.get("address_zip", "")),
                "system_name": s["name"],
                "short_name": short_name(s["name"]),
                "effective_cost": _usd(s["effectiveLow"]),
                "list_rate": _usd(s["medianFee"]),
                "rn_need": _num(s["totalRnNeed"]),
                "n_facilities": str(s["nFacilities"]),
                "landing_url": links["landing_url"],
                "qr_url": links["qr_url"],
            })
    return out_path


if __name__ == "__main__":
    demo = [{
        "id": "cleveland_clinic", "name": "Cleveland Clinic", "nFacilities": 23,
        "totalRnNeed": 9800, "medianFee": 1180, "effectiveLow": 588,
        "contact_name": "Chief Nursing Officer", "address_line1": "9500 Euclid Ave",
        "address_city": "Cleveland", "address_state": "OH", "address_zip": "44195",
    }]
    print("Wrote", build_audience_csv(demo))
