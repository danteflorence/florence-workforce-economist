"""
Contact enrichment — turn CMS public data into named decision-maker contacts
for the long-tail outpatient / post-acute universe.

═══════════════════════════════════════════════════════════════════════════
WHAT THIS DOES
═══════════════════════════════════════════════════════════════════════════
The priced universe (data/non_hospital_priced.parquet, 47,113 facilities) has
no contact information. The raw CMS source files we already downloaded DO carry
named owners/managers, facility phones, and chain rollups. This module joins
them onto the universe by CCN and emits two tables:

    data/facility_contacts.parquet   — one row per facility: a primary
        decision-maker (name + role), the controlling/operating org, facility
        phone, chain, and SNF turnover pain-signals.

    data/mgmt_company_rollup.parquet — operators ranked by how many facilities
        they control ("land once, unlock N"). The real wedge into the long
        tail is the management company, not the individual 100-bed site.

═══════════════════════════════════════════════════════════════════════════
HONEST LIMITATION — NO EMAIL
═══════════════════════════════════════════════════════════════════════════
CMS data never contains email addresses. It gives names, titles/roles, owner
mailing locations, and facility phone numbers. Per the "phone + manager + mail
first" decision, `email` is emitted empty and `has_email=False`. Email is a
later enrichment step (vendor or pattern-inference), gated on approval.

Source coverage by segment:
    SNF      — named owners/managers (NH_Ownership) + phone/turnover (NH_Provider)
    HHA      — facility phone (HH_Provider); named contact needs HHA ownership PUF
    HOSPICE  — facility phone (Hospice_General)
    DIALYSIS — facility phone + chain (Dialysis_Facility); corporate/chain-run
    ASC      — NPI only (ASC_Facility); needs NPPES join for phone + official
"""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
PRICED = DATA_DIR / "non_hospital_priced.parquet"
NH_OWNERSHIP = DATA_DIR / "raw_cms_non_hospital" / "NH_Ownership.csv"
NH_PROVIDER = DATA_DIR / "raw_cms_non_hospital" / "NH_Provider.csv"
HH_PROVIDER = DATA_DIR / "raw_cms_non_hospital" / "HH_Provider.csv"
HOSPICE = DATA_DIR / "raw_cms_non_hospital" / "Hospice_General.csv"
DIALYSIS = DATA_DIR / "raw_cms_non_hospital" / "Dialysis_Facility.csv"
ASC = DATA_DIR / "raw_cms_non_hospital" / "ASC_Facility.csv"
SNF_CHOW = DATA_DIR / "raw_cms_pecos" / "SNF_CHOW_Owners.csv"

CONTACTS_OUT = DATA_DIR / "facility_contacts.parquet"
ROLLUP_OUT = DATA_DIR / "mgmt_company_rollup.parquet"

CONTACT_COLS = [
    "ccn", "name", "city", "state", "facility_type",
    "facility_phone", "npi",
    "chain_name", "chain_facility_count",
    "rn_turnover_pct", "admin_departures",
    "primary_contact_name", "primary_contact_title", "primary_contact_role",
    "controlling_org", "controlling_org_facility_count",
    "is_mgmt_company_run", "pe_or_mgmt_backed",
    "decision_maker_level", "n_named_contacts",
    "email", "has_email", "needs_nppes", "contact_source",
]

# Who to actually call about permanent staffing — ranked best (operator) first.
ROLE_PRIORITY = [
    "OPERATIONAL/MANAGERIAL CONTROL",
    "MANAGING CONTROL - GOVERNING BODY",
    "W-2 MANAGING EMPLOYEE",
    "MANAGING EMPLOYEE",
    "PRESIDENT",
    "CHIEF EXECUTIVE OFFICER",
    "CHIEF OPERATING OFFICER",
    "ADMINISTRATOR",
    "CORPORATE OFFICER",
    "OFFICER",
    "CORPORATE DIRECTOR",
    "DIRECTOR",
    "5% OR GREATER DIRECT OWNERSHIP INTEREST",
    "DIRECT OWNERSHIP INTEREST",
    "PARTNERSHIP INTEREST",
    "5% OR GREATER INDIRECT OWNERSHIP INTEREST",
    "INDIRECT OWNERSHIP INTEREST",
    "ADP OF THE SNF",
]
_ROLE_RANK = {r: i for i, r in enumerate(ROLE_PRIORITY)}
_UNKNOWN_RANK = len(ROLE_PRIORITY) + 1

# Friendly contact titles derived from the CMS role string.
_TITLE_MAP = [
    ("OPERATIONAL/MANAGERIAL", "Operating principal"),
    ("MANAGING CONTROL", "Managing party (governing body)"),
    ("MANAGING EMPLOYEE", "Managing employee"),
    ("PRESIDENT", "President"),
    ("CHIEF EXECUTIVE", "Chief executive officer"),
    ("CHIEF OPERATING", "Chief operating officer"),
    ("ADMINISTRATOR", "Administrator"),
    ("OFFICER", "Corporate officer"),
    ("DIRECTOR", "Corporate director"),
    ("PARTNERSHIP", "Partner"),
    ("OWNERSHIP", "Owner"),
    ("ADP", "Disclosed operating party"),
]


def _role_rank(role: str) -> int:
    return _ROLE_RANK.get(str(role).strip().upper(), _UNKNOWN_RANK)


def _friendly_title(role: str) -> str:
    r = str(role).strip().upper()
    for needle, title in _TITLE_MAP:
        if needle in r:
            return title
    return "Owner / operator"


# Organizations that show up in CMS ownership records for financial / legal
# reasons — lenders, landlords (REITs), auditors, PE vehicles — but are NOT who
# you call about staffing. We scrub them from `controlling_org` and the operator
# rollup so the sales team never sees "Forvis Mazars — 81 sites". A PE/REIT/
# capital match still flips `pe_or_mgmt_backed` (that's a real backing signal).
_NON_OPERATOR_RE = re.compile(
    r"\b(?:forvis|mazars|cpas?|accountanc\w*|accounting|auditors?|"
    r"bank|bancorp|bancshares|"
    r"reit|realty|real estate|"
    r"capital partners|capital management|capital advisors|"
    r"escrow|mortgage)\b",
    re.I,
)
_PE_REIT_RE = re.compile(
    r"\b(?:reit|real estate investment|capital partners|capital management|"
    r"equity partners|private equity)\b",
    re.I,
)


def _is_non_operator_org(name) -> bool:
    """True for lenders / landlords / auditors / PE vehicles — never the org we
    present as the operator to contact."""
    return bool(_NON_OPERATOR_RE.search(str(name)))


def _is_pe_reit_org(name) -> bool:
    """True for PE / REIT / capital entities — a financial-backing signal even
    when they are not the entity you call."""
    return bool(_PE_REIT_RE.search(str(name)))


def _norm_ccn(s: pd.Series) -> pd.Series:
    out = s.fillna("").astype(str).str.strip().str.upper()
    # Kill float artifacts like "015009.0" from mixed-type reads.
    return out.str.replace(r"\.0$", "", regex=True)


def _fmt_phone(v) -> str:
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return str(v).strip() if str(v).strip().lower() not in ("", "nan") else ""


def _title_name(v) -> str:
    v = str(v).strip()
    if not v or v.lower() == "nan":
        return ""
    # CMS owner names arrive as "LAST, FIRST" or "LAST FIRST MIDDLE" in caps.
    if "," in v:
        last, _, first = v.partition(",")
        v = f"{first.strip()} {last.strip()}".strip()
    return " ".join(w.capitalize() for w in v.split())


def _read_csv(path: Path, **kw) -> pd.DataFrame:
    """Robust CSV read — CMS files mix UTF-8 and Latin-1 (PECOS) encodings."""
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, **kw)
        except (UnicodeDecodeError, ValueError):
            continue
    return pd.read_csv(path, dtype=str, encoding="latin-1",
                       engine="python", on_bad_lines="skip", **kw)


# ═════════════════════════════════════════════════════════════════════
# BUILD
# ═════════════════════════════════════════════════════════════════════
def _snf_named_contacts() -> tuple[pd.DataFrame, dict, dict, set]:
    """Per-CCN primary individual + controlling org from NH_Ownership.

    Returns (per_ccn_df, org_facility_count, org_ccns, pe_backed_ccns) where
    org_facility_count maps a controlling org name -> number of distinct
    facilities it controls (operators only — lenders/landlords/auditors are
    scrubbed), and pe_backed_ccns is the set of CCNs with a PE/REIT/capital
    entity anywhere in the ownership stack (a backing signal).
    """
    if not NH_OWNERSHIP.exists():
        return pd.DataFrame(), {}, {}, set()
    own = _read_csv(NH_OWNERSHIP)
    own = own.rename(columns={
        "CMS Certification Number (CCN)": "ccn",
        "Role played by Owner or Manager in Facility": "role",
        "Owner Type": "owner_type",
        "Owner Name": "owner_name",
    })
    own["ccn"] = _norm_ccn(own["ccn"])
    own["rank"] = own["role"].map(_role_rank)
    own["owner_type_l"] = own["owner_type"].fillna("").str.strip().str.lower()

    # Best INDIVIDUAL per facility = the named human to contact.
    ind = (own[own["owner_type_l"] == "individual"]
           .sort_values(["ccn", "rank"]))
    prim = ind.drop_duplicates("ccn").set_index("ccn")
    n_named = ind.groupby("ccn").size()

    # Controlling ORG per facility. Scrub non-operators (lenders / landlords /
    # auditors / PE vehicles) BEFORE picking the org to contact — otherwise an
    # accounting firm with a high-ranking financial role wins the slot.
    org = own[own["owner_type_l"] == "organization"].copy()
    org["is_non_op"] = org["owner_name"].map(_is_non_operator_org)

    # PE / REIT / capital anywhere in the stack = a backing signal we keep even
    # though that entity is never the org we present as the operator to call.
    pe_backed_ccns = set(
        org.loc[org["owner_name"].map(_is_pe_reit_org), "ccn"].unique())

    org_op = org[~org["is_non_op"]]
    org_ctrl = org_op[org_op["rank"] < _ROLE_RANK["ADP OF THE SNF"]]
    org_best_pool = org_ctrl if not org_ctrl.empty else org_op
    ctrl = (org_best_pool.sort_values(["ccn", "rank"])
            .drop_duplicates("ccn").set_index("ccn"))

    # How many facilities each controlling org touches (the rollup engine).
    org_ccns: dict[str, set] = {}
    for org_name, grp in org_ctrl.groupby(org_ctrl["owner_name"].str.strip().str.upper()):
        if org_name:
            org_ccns[org_name] = set(grp["ccn"].unique())
    org_facility_count = {k: len(v) for k, v in org_ccns.items()}

    per = pd.DataFrame(index=sorted(set(prim.index) | set(ctrl.index)))
    per["primary_contact_name"] = prim["owner_name"].map(_title_name)
    per["primary_contact_role"] = prim["role"]
    per["controlling_org"] = ctrl["owner_name"].map(
        lambda x: str(x).strip().title())
    per["controlling_org_key"] = ctrl["owner_name"].str.strip().str.upper()
    per["n_named_contacts"] = n_named
    per["n_named_contacts"] = per["n_named_contacts"].fillna(0).astype(int)
    per["controlling_org_facility_count"] = (
        per["controlling_org_key"].map(org_facility_count))
    return per, org_facility_count, org_ccns, pe_backed_ccns


def _chow_backed_names() -> set:
    """Owner names flagged as PE / management / staffing / holding companies
    in the PECOS SNF change-of-ownership file. Best-effort enrichment."""
    if not SNF_CHOW.exists():
        return set()
    try:
        chow = _read_csv(SNF_CHOW)
    except Exception:
        return set()
    flag_cols = [
        "MANAGEMENT SERVICES COMPANY - OWNER", "MEDICAL STAFFING COMPANY - OWNER",
        "INVESTMENT FIRM - OWNER", "HOLDING COMPANY - OWNER",
    ]
    have = [c for c in flag_cols if c in chow.columns]
    if not have or "ORGANIZATION NAME - OWNER" not in chow.columns:
        return set()
    flagged = chow[have].apply(
        lambda col: col.fillna("").str.strip().str.upper().str.startswith(("Y", "T")))
    mask = flagged.any(axis=1)
    names = chow.loc[mask, "ORGANIZATION NAME - OWNER"].dropna()
    return set(names.str.strip().str.upper())


def _facility_phones() -> pd.DataFrame:
    """CCN -> (phone, chain_name, chain_count, rn_turnover, admin_departures)."""
    frames = []

    if NH_PROVIDER.exists():
        nh = _read_csv(NH_PROVIDER).rename(columns={
            "CMS Certification Number (CCN)": "ccn",
            "Telephone Number": "phone",
            "Chain Name": "chain_name",
            "Number of Facilities in Chain": "chain_facility_count",
            "Registered Nurse turnover": "rn_turnover_pct",
            "Number of administrators who have left the nursing home": "admin_departures",
        })
        cols = ["ccn", "phone", "chain_name", "chain_facility_count",
                "rn_turnover_pct", "admin_departures"]
        frames.append(nh[[c for c in cols if c in nh.columns]])

    for path, phone_col in [
        (HH_PROVIDER, "Telephone Number"),
        (HOSPICE, "Telephone Number"),
        (DIALYSIS, "Telephone Number"),
    ]:
        if path.exists():
            df = _read_csv(path).rename(columns={
                "CMS Certification Number (CCN)": "ccn",
                phone_col: "phone",
                "Chain Organization": "chain_name",
            })
            keep = [c for c in ["ccn", "phone", "chain_name"] if c in df.columns]
            frames.append(df[keep])

    if not frames:
        return pd.DataFrame(columns=["ccn"])
    phones = pd.concat(frames, ignore_index=True)
    phones["ccn"] = _norm_ccn(phones["ccn"])
    phones = phones[phones["ccn"] != ""].drop_duplicates("ccn", keep="first")
    return phones.set_index("ccn")


def _asc_npi() -> pd.DataFrame:
    if not ASC.exists():
        return pd.DataFrame(columns=["npi"])
    asc = _read_csv(ASC).rename(columns={"Facility ID": "ccn", "NPI": "npi"})
    asc["ccn"] = _norm_ccn(asc["ccn"])
    asc = asc[asc["ccn"] != ""].drop_duplicates("ccn")
    return asc[["ccn", "npi"]].set_index("ccn")


def build(verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not PRICED.exists():
        raise FileNotFoundError(f"Priced universe not found: {PRICED}")
    uni = pd.read_parquet(PRICED)
    uni["ccn"] = _norm_ccn(uni["ccn"])

    snf_contacts, org_facility_count, org_ccns, pe_backed_ccns = _snf_named_contacts()
    backed = _chow_backed_names()
    phones = _facility_phones()
    asc = _asc_npi()

    out = uni[["ccn", "name", "city", "state", "facility_type"]].copy()

    # Attach named SNF contacts.
    for col in ["primary_contact_name", "primary_contact_role", "controlling_org",
                "controlling_org_key", "n_named_contacts",
                "controlling_org_facility_count"]:
        out[col] = out["ccn"].map(
            snf_contacts[col] if col in snf_contacts.columns else {})

    # Attach phones / chain / turnover.
    for col in ["phone", "chain_name", "chain_facility_count",
                "rn_turnover_pct", "admin_departures"]:
        out[col] = out["ccn"].map(
            phones[col] if col in phones.columns else {})
    out["npi"] = out["ccn"].map(asc["npi"] if "npi" in asc.columns else {})

    # Normalize / derive.
    out["facility_phone"] = out["phone"].map(_fmt_phone)
    out = out.drop(columns=["phone"])
    out["primary_contact_name"] = out["primary_contact_name"].fillna("")
    out["primary_contact_role"] = out["primary_contact_role"].fillna("")
    out["primary_contact_title"] = out["primary_contact_role"].map(
        lambda r: _friendly_title(r) if str(r).strip() else "")
    out["controlling_org"] = out["controlling_org"].fillna("")
    out["n_named_contacts"] = out["n_named_contacts"].fillna(0).astype(int)
    out["controlling_org_facility_count"] = (
        pd.to_numeric(out["controlling_org_facility_count"], errors="coerce")
        .fillna(0).astype(int))
    out["chain_name"] = out["chain_name"].fillna("")
    out["chain_facility_count"] = out["chain_facility_count"].fillna("")
    out["rn_turnover_pct"] = out["rn_turnover_pct"].fillna("")
    out["admin_departures"] = out["admin_departures"].fillna("")
    out["npi"] = out["npi"].fillna("")

    out["pe_or_mgmt_backed"] = (
        out["controlling_org_key"].fillna("").isin(backed)
        | out["ccn"].isin(pe_backed_ccns))
    out["is_mgmt_company_run"] = (
        (out["controlling_org_facility_count"] >= 2) | out["pe_or_mgmt_backed"])

    def _level(r):
        if r["controlling_org_facility_count"] >= 2 or r["pe_or_mgmt_backed"]:
            return "management_company"
        if r["controlling_org"]:
            return "corporate_entity"
        if r["primary_contact_name"]:
            return "owner_operator"
        return "unknown"
    out["decision_maker_level"] = out.apply(_level, axis=1)

    # If no named individual but there's a controlling org, surface the org.
    no_name = out["primary_contact_name"] == ""
    out.loc[no_name & (out["controlling_org"] != ""), "primary_contact_name"] = \
        out.loc[no_name, "controlling_org"]
    out.loc[no_name & (out["controlling_org"] != "") &
            (out["primary_contact_title"] == ""), "primary_contact_title"] = \
        "Owner / operating organization"

    out["email"] = ""
    out["has_email"] = False
    out["needs_nppes"] = (out["facility_phone"] == "") & (out["primary_contact_name"] == "")

    def _src(r):
        s = []
        if r["primary_contact_name"]:
            s.append("NH_Ownership")
        if r["facility_phone"]:
            s.append("Provider/CareCompare")
        if r["npi"] and not s:
            s.append("ASC/NPI")
        return "+".join(s) if s else "none"
    out["contact_source"] = out.apply(_src, axis=1)

    out = out.drop(columns=["controlling_org_key"])
    out = out.reindex(columns=CONTACT_COLS)
    out.to_parquet(CONTACTS_OUT, index=False)

    # ── Management-company rollup ──
    rows = []
    rn_by_ccn = (pd.to_numeric(uni.set_index("ccn")["rn_estimate"],
                               errors="coerce").fillna(0)
                 if "rn_estimate" in uni.columns else pd.Series(dtype=float))
    name_by_ccn = uni.set_index("ccn")["name"]
    st_by_ccn = uni.set_index("ccn")["state"]
    for org_name, ccns in org_ccns.items():
        if len(ccns) < 2:
            continue
        ccns = [c for c in ccns if c in name_by_ccn.index]
        if not ccns:
            continue
        states = sorted(set(st_by_ccn.reindex(ccns).dropna().tolist()))
        rows.append({
            "controlling_org": org_name.title(),
            "n_facilities": len(ccns),
            "total_rn_capacity": int(rn_by_ccn.reindex(ccns).sum()),
            "states": ", ".join(states[:8]) + (" …" if len(states) > 8 else ""),
            "n_states": len(states),
            "pe_or_mgmt_backed": org_name in backed,
            "sample_facilities": " · ".join(
                name_by_ccn.reindex(ccns).dropna().head(3).str.title().tolist()),
        })
    rollup = pd.DataFrame(rows).sort_values(
        ["n_facilities", "total_rn_capacity"], ascending=False
    ).reset_index(drop=True) if rows else pd.DataFrame(
        columns=["controlling_org", "n_facilities", "total_rn_capacity",
                 "states", "n_states", "pe_or_mgmt_backed", "sample_facilities"])
    rollup.to_parquet(ROLLUP_OUT, index=False)

    if verbose:
        _report(out, rollup)
    return out, rollup


def _report(out: pd.DataFrame, rollup: pd.DataFrame) -> None:
    print(f"facility_contacts.parquet  →  {len(out):,} facilities")
    has_name = (out["primary_contact_name"] != "").sum()
    has_phone = (out["facility_phone"] != "").sum()
    print(f"  with a named decision-maker : {has_name:,} "
          f"({has_name/len(out)*100:.0f}%)")
    print(f"  with a facility phone       : {has_phone:,} "
          f"({has_phone/len(out)*100:.0f}%)")
    print(f"  management-company-run      : {int(out['is_mgmt_company_run'].sum()):,}")
    print(f"  needs NPPES (no phone/name) : {int(out['needs_nppes'].sum()):,}")
    print("  by facility type:")
    for ft, grp in out.groupby("facility_type"):
        print(f"    {ft:9s} n={len(grp):6,d}  named={int((grp['primary_contact_name']!='').sum()):6,d}"
              f"  phone={int((grp['facility_phone']!='').sum()):6,d}")
    print(f"\nmgmt_company_rollup.parquet →  {len(rollup):,} multi-facility operators")
    if not rollup.empty:
        print("  top operators by facility count:")
        for _, r in rollup.head(8).iterrows():
            print(f"    {r['n_facilities']:4d} sites · {r['total_rn_capacity']:5d} RN cap · "
                  f"{r['controlling_org'][:48]}")


# ═════════════════════════════════════════════════════════════════════
# LOOKUP / ENRICH  (used by the Growth engine)
# ═════════════════════════════════════════════════════════════════════
@functools.lru_cache(maxsize=1)
def load_contacts() -> pd.DataFrame:
    if not CONTACTS_OUT.exists():
        return pd.DataFrame(columns=CONTACT_COLS)
    df = pd.read_parquet(CONTACTS_OUT)
    df["ccn"] = _norm_ccn(df["ccn"])
    return df.drop_duplicates("ccn").set_index("ccn")


@functools.lru_cache(maxsize=1)
def load_rollup() -> pd.DataFrame:
    if not ROLLUP_OUT.exists():
        return pd.DataFrame()
    return pd.read_parquet(ROLLUP_OUT)


_LOOKUP_FIELDS = [
    "primary_contact_name", "primary_contact_title", "primary_contact_role",
    "facility_phone", "controlling_org", "controlling_org_facility_count",
    "is_mgmt_company_run", "pe_or_mgmt_backed", "decision_maker_level",
    "rn_turnover_pct", "chain_name", "needs_nppes",
]


def lookup_contact(ccn: str) -> dict:
    """Return the contact dict for one CCN, or empty-string defaults."""
    contacts = load_contacts()
    key = _norm_ccn(pd.Series([ccn])).iloc[0]
    if key in contacts.index:
        row = contacts.loc[key]
        if isinstance(row, pd.DataFrame):  # dup safety
            row = row.iloc[0]
        return {f: row.get(f, "") for f in _LOOKUP_FIELDS}
    return {f: "" for f in _LOOKUP_FIELDS}


def enrich(df: pd.DataFrame, ccn_col: str = "ccn") -> pd.DataFrame:
    """Left-merge contact fields onto any frame that has a CCN column."""
    if df is None or df.empty or ccn_col not in df.columns:
        return df
    contacts = load_contacts()
    if contacts.empty:
        return df
    out = df.copy()
    keys = _norm_ccn(out[ccn_col])
    for f in _LOOKUP_FIELDS:
        if f in contacts.columns:
            out[f] = keys.map(contacts[f]).fillna("")
    return out


def ccns_for_operator(org_name: str) -> list[str]:
    """Every facility CCN controlled by one operator (matched on controlling_org).

    This is the "land once, unlock N" join: pick a management company, get all
    of its sites so a rep can add the whole portfolio to the pipeline at once.
    """
    if not str(org_name).strip():
        return []
    contacts = load_contacts()
    if contacts.empty or "controlling_org" not in contacts.columns:
        return []
    mask = (contacts["controlling_org"].fillna("").str.strip().str.casefold()
            == str(org_name).strip().casefold())
    return contacts.index[mask].tolist()


if __name__ == "__main__":
    print("--- Building facility contacts from CMS public data ---")
    build(verbose=True)
    print("\nOK")
