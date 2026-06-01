"""
NPPES address enrichment — fill deliverable street addresses for Lob mail.

CMS NPPES (the NPI registry) carries each provider's practice + mailing address.
The outpatient universe (facility_contacts.parquet) has NPIs, so we resolve a
street address by NPI — free, public, no API key.

Three modes (max yield):
  - lookup_npi(npi)      single on-demand lookup (used when a mailpiece is drafted)
  - batch_enrich(limit)  resolve many → data/facility_addresses.parquet
  - manual               reps type the address (contacts.py)

API: https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
ADDR_FILE = DATA_DIR / "facility_addresses.parquet"
CONTACTS_FILE = DATA_DIR / "facility_contacts.parquet"
API = "https://npiregistry.cms.hhs.gov/api/"
COLS = ["ccn", "npi", "address1", "city", "state", "zip", "source"]


def lookup_npi(npi: str, timeout: float = 8.0) -> dict | None:
    """Resolve one NPI → {address1, city, state, zip}. None on miss/error."""
    npi = str(npi).strip()
    if not npi.isdigit() or len(npi) != 10:
        return None
    url = API + "?" + urllib.parse.urlencode({"number": npi, "version": "2.1"})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "florence-we/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    addrs = results[0].get("addresses") or []
    loc = (next((a for a in addrs if a.get("address_purpose") == "LOCATION"), None)
           or next((a for a in addrs if a.get("address_purpose") == "MAILING"), None)
           or (addrs[0] if addrs else None))
    if not loc:
        return None
    return {
        "npi": npi,
        "address1": (loc.get("address_1") or "").strip(),
        "city": (loc.get("city") or "").strip(),
        "state": (loc.get("state") or "").strip(),
        "zip": (loc.get("postal_code") or "").strip()[:5],
        "source": "nppes",
    }


def _load_addr() -> pd.DataFrame:
    if ADDR_FILE.exists():
        try:
            return pd.read_parquet(ADDR_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=COLS)


def address_for_ccn(ccn: str) -> dict | None:
    """Enriched address for a facility CCN, if we've resolved one."""
    df = _load_addr()
    if df.empty:
        return None
    m = df[df["ccn"].astype(str) == str(ccn)]
    if m.empty:
        return None
    r = m.iloc[0].to_dict()
    return r if str(r.get("address1", "")).strip() else None


def enrich_ccn(ccn: str) -> dict | None:
    """On-demand: look up a single facility's address by its NPI and persist it."""
    if not CONTACTS_FILE.exists():
        return None
    fc = pd.read_parquet(CONTACTS_FILE)
    m = fc[fc["ccn"].astype(str) == str(ccn)]
    if m.empty:
        return None
    npi = str(m.iloc[0].get("npi", "") or "")
    a = lookup_npi(npi)
    if not a:
        return None
    a["ccn"] = str(ccn)
    existing = _load_addr()
    merged = pd.concat([existing, pd.DataFrame([a])], ignore_index=True).drop_duplicates(
        "ccn", keep="last")
    merged.to_parquet(ADDR_FILE, index=False)
    return a


def batch_enrich(limit: int = 400, sleep: float = 0.12, only_missing: bool = True) -> dict:
    """Resolve addresses for outpatient facilities by NPI, highest-value first
    (by chain footprint). Writes data/facility_addresses.parquet."""
    if not CONTACTS_FILE.exists():
        return {"attempted": 0, "resolved": 0, "total_addresses": 0, "error": "no contacts file"}
    fc = pd.read_parquet(CONTACTS_FILE)
    fc = fc[fc["npi"].astype(str).str.strip().ne("")]
    if "chain_facility_count" in fc.columns:
        fc = fc.assign(
            _p=pd.to_numeric(fc["chain_facility_count"], errors="coerce").fillna(0)
        ).sort_values("_p", ascending=False)
    existing = _load_addr()
    done = set(existing["ccn"].astype(str)) if not existing.empty else set()

    rows, attempted = [], 0
    for _, r in fc.iterrows():
        ccn = str(r["ccn"])
        if only_missing and ccn in done:
            continue
        if attempted >= limit:
            break
        attempted += 1
        a = lookup_npi(str(r["npi"]))
        if a:
            a["ccn"] = ccn
            rows.append(a)
        time.sleep(sleep)

    if rows:
        merged = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True).drop_duplicates(
            "ccn", keep="last")
        merged.to_parquet(ADDR_FILE, index=False)
    return {"attempted": attempted, "resolved": len(rows), "total_addresses": len(_load_addr())}


# CMS facility files that carry CCN + street address (local, authoritative).
_CMS_FILES = [
    ("NH_Provider.csv", "CMS Certification Number (CCN)", "Provider Address", "City/Town", "State", "ZIP Code"),
    ("Dialysis_Facility.csv", "CMS Certification Number (CCN)", "Address Line 1", "City/Town", "State", "ZIP Code"),
    ("HH_Provider.csv", "CMS Certification Number (CCN)", "Address", "City/Town", "State", "ZIP Code"),
    ("Hospice_General.csv", "CMS Certification Number (CCN)", "Address Line 1", "City/Town", "State", "ZIP Code"),
]


def cms_addresses() -> pd.DataFrame:
    """Extract CCN→street address from the raw CMS facility files (no network).
    Covers SNF / dialysis / home-health / hospice — the bulk of the universe."""
    base = DATA_DIR / "raw_cms_non_hospital"
    frames = []
    for fname, ccn_c, a1_c, city_c, state_c, zip_c in _CMS_FILES:
        p = base / fname
        if not p.exists():
            continue
        want = {ccn_c, a1_c, city_c, state_c, zip_c}
        try:
            d = pd.read_csv(p, dtype=str, usecols=lambda c: c in want, encoding_errors="replace")
        except Exception:
            try:
                d = pd.read_csv(p, dtype=str, encoding_errors="replace")
            except Exception:
                continue
        d = d.rename(columns={ccn_c: "ccn", a1_c: "address1", city_c: "city",
                              state_c: "state", zip_c: "zip"})
        for c in ["ccn", "address1", "city", "state", "zip"]:
            if c not in d.columns:
                d[c] = ""
        d["source"] = "cms_file"
        d["npi"] = ""
        frames.append(d[["ccn", "npi", "address1", "city", "state", "zip", "source"]])
    if not frames:
        return pd.DataFrame(columns=COLS)
    out = pd.concat(frames, ignore_index=True)
    out["ccn"] = out["ccn"].astype(str).str.strip()
    out["zip"] = out["zip"].astype(str).str.strip().str[:5]
    out = out[out["ccn"].ne("") & out["address1"].astype(str).str.strip().ne("")]
    return out.drop_duplicates("ccn", keep="first")


def enrich_from_cms() -> dict:
    """Merge local CMS-file addresses into facility_addresses.parquet. Existing
    rows (e.g. NPPES-resolved) win; CMS fills everything else."""
    cms = cms_addresses()
    existing = _load_addr()
    if cms.empty and existing.empty:
        return {"cms_rows": 0, "total_addresses": 0}
    merged = pd.concat([existing, cms], ignore_index=True).drop_duplicates("ccn", keep="first")
    merged.to_parquet(ADDR_FILE, index=False)
    return {"cms_rows": int(len(cms)), "total_addresses": int(len(merged))}


def batch_enrich_parallel(workers: int = 12, limit: int | None = None,
                          only_missing: bool = True, chunk: int = 1000) -> dict:
    """Full-universe enrichment with bounded concurrency (public CMS API — modest
    worker count). Checkpoints data/facility_addresses.parquet after each chunk so
    partial progress survives interruption."""
    from concurrent.futures import ThreadPoolExecutor
    if not CONTACTS_FILE.exists():
        return {"attempted": 0, "resolved": 0, "total_addresses": 0, "error": "no contacts"}
    fc = pd.read_parquet(CONTACTS_FILE)
    fc = fc[fc["npi"].astype(str).str.fullmatch(r"\d{10}")]
    existing = _load_addr()
    done = set(existing["ccn"].astype(str)) if not existing.empty else set()
    todo = [(str(r["ccn"]), str(r["npi"])) for _, r in fc.iterrows()
            if not (only_missing and str(r["ccn"]) in done)]
    if limit:
        todo = todo[:limit]

    acc = {r["ccn"]: r for r in existing.to_dict("records")} if not existing.empty else {}

    def _one(ccn_npi):
        ccn, npi = ccn_npi
        a = lookup_npi(npi)
        if a:
            a["ccn"] = ccn
        return ccn, a

    attempted = resolved = 0
    for i in range(0, len(todo), chunk):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for ccn, a in ex.map(_one, todo[i:i + chunk]):
                attempted += 1
                if a:
                    acc[ccn] = a
                    resolved += 1
        pd.DataFrame(list(acc.values())).to_parquet(ADDR_FILE, index=False)  # checkpoint
    return {"attempted": attempted, "resolved": resolved, "total_addresses": len(acc)}


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print(batch_enrich(limit=n))
