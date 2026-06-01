"""
Customer-contact store — what we can actually use to reach each account.

Merges two layers:
  1. CMS-derived baseline (data/facility_contacts.parquet) — facility phone +
     named owner/manager for the 47K outpatient/post-acute universe (keyed by
     CCN). Honest gap: CMS carries NO email, so email starts blank.
  2. Rep-maintained overrides (data/contact_overrides.csv) — anyone can add or
     correct email/phone/name/notes as they make contact. Overrides win.

Nothing here fabricates contact data. Email is rep-entered (or a future
approved vendor enrichment). Keyed by:
  - entity_type "system"   → Florence health_system_id (override-only)
  - entity_type "hospital" → CCN (CMS baseline + overrides)
  - entity_type "facility" → CCN (outpatient; CMS baseline + overrides)
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OVERRIDES = DATA_DIR / "contact_overrides.csv"
ENRICHED = DATA_DIR / "facility_contacts.parquet"

FIELDS = [
    "entity_type", "entity_id", "org_name", "contact_name", "title",
    "email", "phone", "notes", "updated_at", "updated_by",
]

_enriched_cache: pd.DataFrame | None = None


def _ensure_header() -> None:
    if not OVERRIDES.exists():
        OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
        with open(OVERRIDES, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read_overrides() -> pd.DataFrame:
    _ensure_header()
    try:
        return pd.read_csv(OVERRIDES, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)


def _enriched() -> pd.DataFrame:
    global _enriched_cache
    if _enriched_cache is None:
        try:
            _enriched_cache = pd.read_parquet(ENRICHED) if ENRICHED.exists() else pd.DataFrame()
        except Exception:
            _enriched_cache = pd.DataFrame()
    return _enriched_cache


def get_contact(entity_type: str, entity_id: str) -> dict:
    """Merged contact for one account. Override fields win over the CMS baseline.

    `source` reports provenance: 'none' | 'cms' | 'rep' | 'rep+cms'.
    """
    base = {
        "entity_type": entity_type, "entity_id": str(entity_id),
        "org_name": "", "contact_name": "", "title": "",
        "email": "", "phone": "", "notes": "",
        "updated_at": "", "updated_by": "", "source": "none",
    }

    en = _enriched()
    if not en.empty and entity_type in ("facility", "hospital") and "ccn" in en.columns:
        m = en[en["ccn"].astype(str) == str(entity_id)]
        if not m.empty:
            r = m.iloc[0]
            base["org_name"] = str(r.get("name", "") or "")
            base["contact_name"] = str(r.get("primary_contact_name", "") or "")
            base["title"] = str(r.get("primary_contact_title", "") or "")
            base["phone"] = str(r.get("facility_phone", "") or "")
            base["source"] = "cms"

    ov = _read_overrides()
    if not ov.empty:
        m = ov[(ov["entity_type"] == entity_type)
               & (ov["entity_id"].astype(str) == str(entity_id))]
        if not m.empty:
            r = m.iloc[-1]  # most recent wins
            for c in ("org_name", "contact_name", "title", "email", "phone",
                      "notes", "updated_at", "updated_by"):
                v = str(r.get(c, "") or "").strip()
                if v:
                    base[c] = v
            base["source"] = "rep+cms" if base["source"] == "cms" else "rep"

    return base


def save_contact(entity_type: str, entity_id: str, *, org_name: str = "",
                 contact_name: str = "", title: str = "", email: str = "",
                 phone: str = "", notes: str = "", by: str = "") -> None:
    """Upsert a rep override (one row per entity; latest replaces prior)."""
    _ensure_header()
    df = _read_overrides()
    if not df.empty:
        mask = (df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))
        df = df[~mask]
    row = {
        "entity_type": entity_type, "entity_id": str(entity_id), "org_name": org_name,
        "contact_name": contact_name, "title": title, "email": email, "phone": phone,
        "notes": notes, "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "updated_by": by,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(OVERRIDES, index=False, columns=FIELDS)


def coverage_note() -> str:
    """One-line honesty about what the baseline carries (for UI captions)."""
    en = _enriched()
    if en.empty:
        return "No baseline contact file — add contacts as you reach accounts."
    n = len(en)
    phone = int(en["facility_phone"].astype(str).str.strip().ne("").sum()) if "facility_phone" in en.columns else 0
    named = int(en["primary_contact_name"].astype(str).str.strip().ne("").sum()) if "primary_contact_name" in en.columns else 0
    return (f"Baseline: {phone:,}/{n:,} outpatient sites have a phone, "
            f"{named:,} a named contact. CMS carries no email — add it as you make contact.")
