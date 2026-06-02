"""
Call center — outbound queue over the outpatient phone universe.

CMS gives us a phone for ~41k outpatient/post-acute facilities. This hands a
decentralized back-office team the next facility to dial, with CLAIM-LOCKING
(TTL) so two agents never double-dial the same place. Dispositions log to the
activity timeline, callbacks set a reminder (the facility drops off the queue
until its date), and assignment reuses ownership.

Click-to-dial works now (tel: / RingCentral app); RingOut upgrades it when
RingCentral creds are set (ringcentral.py). data/call_claims.csv (gitignored).
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
CONTACTS = DATA_DIR / "facility_contacts.parquet"
RECS = DATA_DIR / "recommendations.parquet"
CLAIMS = DATA_DIR / "call_claims.csv"
CLAIM_TTL_MIN = 45
CLAIM_FIELDS = ["ccn", "agent", "claimed_at"]

_fac_cache: pd.DataFrame | None = None
_price_cache: dict | None = None

_QCOLS = ["ccn", "name", "city", "state", "facility_type", "facility_phone",
          "chain_name", "chain_facility_count", "primary_contact_name",
          "primary_contact_title", "decision_maker_level"]


def _facilities() -> pd.DataFrame:
    global _fac_cache
    if _fac_cache is None:
        try:
            _fac_cache = pd.read_parquet(CONTACTS) if CONTACTS.exists() else pd.DataFrame()
        except Exception:
            _fac_cache = pd.DataFrame()
    return _fac_cache


def states_with_phones() -> list:
    df = _facilities()
    if df.empty or "facility_phone" not in df.columns:
        return []
    d = df[df["facility_phone"].astype(str).str.strip().ne("")]
    return sorted(x for x in d["state"].dropna().astype(str).unique() if x.strip())


def queue(states=None, facility_types=None, chain_query: str = "", limit: int = 300) -> pd.DataFrame:
    """Callable facilities (phone present), big chains first. Filters optional."""
    df = _facilities()
    if df.empty or "facility_phone" not in df.columns:
        return pd.DataFrame(columns=_QCOLS)
    df = df[df["facility_phone"].astype(str).str.strip().ne("")]
    if states:
        df = df[df["state"].isin(states)]
    if facility_types:
        df = df[df["facility_type"].isin(facility_types)]
    if chain_query.strip():
        q = chain_query.strip().lower()
        df = df[df["chain_name"].astype(str).str.lower().str.contains(q, na=False)
                | df["name"].astype(str).str.lower().str.contains(q, na=False)]
    if "chain_facility_count" in df.columns:
        df = df.assign(_p=pd.to_numeric(df["chain_facility_count"], errors="coerce").fillna(0)) \
               .sort_values(["_p", "name"], ascending=[False, True])
    cols = [c for c in _QCOLS if c in df.columns]
    return df[cols].head(limit).reset_index(drop=True)


def facility_pricing(ccn: str) -> dict:
    """Per-facility pricing from recommendations.parquet, if present (for the
    call script's numbers). Empty dict when unavailable."""
    global _price_cache
    if _price_cache is None:
        _price_cache = {}
        try:
            if RECS.exists():
                r = pd.read_parquet(RECS)
                fee = "target_monthly_florence_fee_account"
                sav = "target_term_net_savings_account"
                for _, row in r.iterrows():
                    _price_cache[str(row.get("ccn", ""))] = {
                        "monthly_fee": float(row.get(fee, 0) or 0),
                        "term_impact": float(row.get(sav, 0) or 0),
                        "rn_need": int(float(row.get("rn_need", 0) or 0)),
                    }
        except Exception:
            _price_cache = {}
    return _price_cache.get(str(ccn), {})


# ─── Claims (TTL lock) ──────────────────────────────────────────────
def _ensure() -> None:
    if not CLAIMS.exists():
        CLAIMS.parent.mkdir(parents=True, exist_ok=True)
        with open(CLAIMS, "w", newline="") as f:
            csv.writer(f).writerow(CLAIM_FIELDS)


def _read_claims() -> pd.DataFrame:
    _ensure()
    try:
        return pd.read_csv(CLAIMS, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=CLAIM_FIELDS)


def active_claims(now: datetime | None = None) -> dict:
    """ccn -> agent for claims still within the TTL window."""
    now = now or datetime.utcnow()
    df = _read_claims()
    if df.empty:
        return {}
    out = {}
    for _, r in df.sort_values("claimed_at").iterrows():
        try:
            ts = datetime.fromisoformat(str(r["claimed_at"]))
        except Exception:
            continue
        if now - ts <= timedelta(minutes=CLAIM_TTL_MIN):
            out[str(r["ccn"])] = str(r["agent"])
        else:
            out.pop(str(r["ccn"]), None)
    return out


def claimed_by(ccn: str) -> str:
    return active_claims().get(str(ccn), "")


def claim(ccn: str, agent: str) -> bool:
    """Claim a facility for an agent (refreshes the TTL). Latest claim wins."""
    _ensure()
    df = _read_claims()
    if not df.empty:
        df = df[df["ccn"].astype(str) != str(ccn)]
    row = {"ccn": str(ccn), "agent": (agent or "").strip(),
           "claimed_at": datetime.utcnow().isoformat(timespec="seconds")}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(CLAIMS, index=False, columns=CLAIM_FIELDS)
    return True


def release(ccn: str) -> bool:
    df = _read_claims()
    if df.empty:
        return False
    keep = df[df["ccn"].astype(str) != str(ccn)]
    keep.to_csv(CLAIMS, index=False, columns=CLAIM_FIELDS)
    return len(keep) != len(df)


# ─── Disposition ────────────────────────────────────────────────────
DISPOSITIONS = ["Connected", "No answer", "Left voicemail", "Callback",
                "Not interested", "Interested → handoff"]


def disposition(ccn: str, agent: str, outcome: str, note: str = "",
                callback_days: int | None = None, org_name: str = "") -> bool:
    """Log a call outcome to the activity timeline; optionally schedule a callback
    (snooze) so the facility leaves the queue until then; release the claim."""
    import activity
    detail = outcome + (f" — {note}" if note else "")
    activity.log("facility", ccn, "call", detail, org_name=org_name, by=agent)
    if callback_days:
        try:
            import reminders
            reminders.snooze("facility", ccn, int(callback_days),
                             note=f"Callback: {note or outcome}", by=agent)
        except Exception:
            pass
    release(ccn)
    return True
