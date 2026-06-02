"""
Customer-contact store — what we can actually use to reach each account.

Merges two layers:
  1. CMS-derived baseline (data/facility_contacts.parquet) — facility phone +
     named owner/manager + city/state for the 47K outpatient/post-acute universe
     (keyed by CCN). Honest gaps: CMS carries NO email and NO street address.
  2. Rep-maintained overrides (data/contact_overrides.csv) — anyone can add or
     correct email / phone / name / street address / notes as they make contact.
     Overrides win.

Nothing here fabricates contact data. Email + street address are rep-entered (or
a future approved enrichment: NPPES by NPI for the mailing address, a vendor for
email). The street address is what unlocks Lob direct mail (see lob_mailer.py).

Keyed by:
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
    "email", "phone", "address1", "city", "state", "zip",
    "notes", "updated_at", "updated_by",
]

# Fields the rep can edit (and that overrides may carry).
_OVERRIDE_FIELDS = [
    "org_name", "contact_name", "title", "email", "phone",
    "address1", "city", "state", "zip", "notes", "updated_at", "updated_by",
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
        df = pd.read_csv(OVERRIDES, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)
    # tolerate older files missing the newer columns
    for c in FIELDS:
        if c not in df.columns:
            df[c] = ""
    return df


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
    `mailable` is True when a street address + zip are present (Lob-ready).
    """
    base = {
        "entity_type": entity_type, "entity_id": str(entity_id),
        "org_name": "", "contact_name": "", "title": "",
        "email": "", "phone": "", "address1": "", "city": "", "state": "", "zip": "",
        "notes": "", "updated_at": "", "updated_by": "", "source": "none",
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
            base["city"] = str(r.get("city", "") or "")
            base["state"] = str(r.get("state", "") or "")
            base["source"] = "cms"

    # NPPES-enriched street address (batch or on-demand), keyed by CCN.
    if entity_type in ("facility", "hospital"):
        try:
            import nppes_enrich
            na = nppes_enrich.address_for_ccn(entity_id)
            if na and str(na.get("address1", "")).strip():
                base["address1"] = base["address1"] or na.get("address1", "")
                base["city"] = base["city"] or na.get("city", "")
                base["state"] = base["state"] or na.get("state", "")
                base["zip"] = base["zip"] or na.get("zip", "")
                base["source"] = "cms+nppes" if base["source"] == "cms" else "nppes"
        except Exception:
            pass

    ov = _read_overrides()
    if not ov.empty:
        m = ov[(ov["entity_type"] == entity_type)
               & (ov["entity_id"].astype(str) == str(entity_id))]
        if not m.empty:
            r = m.iloc[-1]  # most recent wins
            for c in _OVERRIDE_FIELDS:
                v = str(r.get(c, "") or "").strip()
                if v:
                    base[c] = v
            base["source"] = "rep+cms" if base["source"] == "cms" else "rep"

    base["mailable"] = bool(base["address1"].strip() and base["zip"].strip())
    return base


def save_contact(entity_type: str, entity_id: str, *, org_name: str = "",
                 contact_name: str = "", title: str = "", email: str = "",
                 phone: str = "", address1: str = "", city: str = "",
                 state: str = "", zip: str = "", notes: str = "", by: str = "") -> None:
    """Upsert a rep override (one row per entity; latest replaces prior)."""
    _ensure_header()
    df = _read_overrides()
    if not df.empty:
        mask = (df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))
        df = df[~mask]
    row = {
        "entity_type": entity_type, "entity_id": str(entity_id), "org_name": org_name,
        "contact_name": contact_name, "title": title, "email": email, "phone": phone,
        "address1": address1, "city": city, "state": state, "zip": zip, "notes": notes,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"), "updated_by": by,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(OVERRIDES, index=False, columns=FIELDS)


def export_overrides_csv() -> str:
    """The rep-maintained contact overrides as CSV text (round-trips with import)."""
    df = _read_overrides()
    if df.empty:
        df = pd.DataFrame(columns=FIELDS)
    return df.to_csv(index=False)


def _system_name_index() -> dict:
    """Map lowercased system display-name / id → florence_system_id, so an import
    CSV that only has org names can still resolve to system entities."""
    idx: dict = {}
    p = DATA_DIR / "system_directory.csv"
    if p.exists():
        try:
            d = pd.read_csv(p, dtype=str).fillna("")
            for _, r in d.iterrows():
                sid = str(r.get("florence_system_id", "")).strip()
                if not sid:
                    continue
                idx[sid.lower()] = sid
                dn = str(r.get("display_name", "")).strip().lower()
                if dn:
                    idx[dn] = sid
        except Exception:
            pass
    return idx


def bulk_import(df: "pd.DataFrame", by: str = "", derive_emails: bool = False) -> dict:
    """Upsert many contacts from a CSV the rep already has. Forgiving:
      • uses entity_type/entity_id when present (round-trips an export);
      • else resolves a system by org_name/system_name against the directory;
      • MERGES — blank cells never wipe existing values;
      • optionally derives a missing email from name + the system's domain.
    Returns {imported, skipped, derived}."""
    if df is None or len(df) == 0:
        return {"imported": 0, "skipped": 0, "derived": 0}
    df = df.copy().fillna("")
    df.columns = [str(c).strip().lower() for c in df.columns]
    name_idx = _system_name_index()
    imported = skipped = derived = 0

    def g(r, *keys):
        for k in keys:
            v = r.get(k, "")
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                pass
            v = str(v).strip()
            if v and v.lower() != "nan":
                return v
        return ""

    for _, r in df.iterrows():
        et = g(r, "entity_type").lower()
        eid = g(r, "entity_id")
        org = g(r, "org_name", "system_name", "health_system")
        if not eid and org and org.lower() in name_idx:
            eid, et = name_idx[org.lower()], (et or "system")
        if not eid:
            skipped += 1
            continue
        et = et or "system"
        existing = get_contact(et, eid)
        contact_name = g(r, "contact_name", "contact") or existing.get("contact_name", "")
        email = g(r, "email")
        if derive_emails and not email and contact_name:
            try:
                import email_discovery as _ed
                dom = _ed.system_domain(eid) if et == "system" else ""
                cands = _ed.candidate_emails(contact_name, dom) if dom else []
                if cands:
                    email, _ = cands[0]["email"], None
                    derived += 1
            except Exception:
                pass
        save_contact(
            et, eid, by=by,
            org_name=org or existing.get("org_name", ""),
            contact_name=contact_name,
            title=g(r, "title") or existing.get("title", ""),
            email=email or existing.get("email", ""),
            phone=g(r, "phone") or existing.get("phone", ""),
            address1=g(r, "address1", "address") or existing.get("address1", ""),
            city=g(r, "city") or existing.get("city", ""),
            state=g(r, "state") or existing.get("state", ""),
            zip=g(r, "zip", "zipcode", "postal_code") or existing.get("zip", ""),
            notes=g(r, "notes") or existing.get("notes", ""),
        )
        imported += 1
    return {"imported": imported, "skipped": skipped, "derived": derived}


def coverage_note() -> str:
    en = _enriched()
    if en.empty:
        return "No baseline contact file — add contacts as you reach accounts."
    n = len(en)
    phone = int(en["facility_phone"].astype(str).str.strip().ne("").sum()) if "facility_phone" in en.columns else 0
    named = int(en["primary_contact_name"].astype(str).str.strip().ne("").sum()) if "primary_contact_name" in en.columns else 0
    return (f"Baseline: {phone:,}/{n:,} outpatient sites have a phone, {named:,} a named "
            f"contact. CMS carries no email or street address — add those to enable mail.")
