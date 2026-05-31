"""
FlorenceRN Growth Automation — the AI SDR / acquisition engine.

This operationalizes §7 and §9 of the Infrastructure Investment Memo: the
"Growth Automation" distribution layer that acquires BOTH sides of the
nurse-production network.

    Demand side  →  long-tail outpatient / post-acute EMPLOYERS
    Supply side  →  global nursing UNIVERSITIES / programs

The Workforce Economist already *discovers and prices* the 47,113 long-tail
outpatient facilities (SNF / HHA / Dialysis / Hospice / ASC). Growth
Automation is the layer on top that turns each priced target into a tracked
outreach motion:

    DISCOVER → ENRICH → PERSONALIZE (deck/video/landing) → SEND →
    ENGAGE → CONVERT (TOS / payment / reserve capacity) → ACTIVE ACCOUNT

This module is the founder-led MVP described in the memo: it generates the
personalized assets and tracks each target through a Streak-style pipeline.
It does NOT send email, store cards, or call external APIs — those are wired
later behind human review. Everything here is local CSV + content generation.

═══════════════════════════════════════════════════════════════════════════
PUBLIC-SAFE GUARANTEE
═══════════════════════════════════════════════════════════════════════════
Generated outreach copy is the single most PUBLIC-FACING artifact in the whole
platform — it is literally meant to be emailed to employers and hosted on
landing pages. It must NEVER contain FICA / IRS / F-1 / payroll-tax / visa-
status language. `_assert_public_safe()` scans every generated string and
raises if a banned term slips in. The internal pricing economics (which DO use
FICA) stay on the internal pricing surfaces only.

═══════════════════════════════════════════════════════════════════════════
DATA FILES
═══════════════════════════════════════════════════════════════════════════
data/growth_employer_pipeline.csv
data/growth_university_pipeline.csv
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# Optional contact enrichment (CMS public data → named decision-makers + the
# management-company rollup). Imported defensively so the Growth engine still
# runs if the module or its parquet outputs are absent (graceful degradation).
try:
    import contact_enrichment as _ce
except Exception:  # pragma: no cover - module is best-effort
    _ce = None

DATA_DIR = Path(__file__).parent / "data"
EMPLOYER_FILE = DATA_DIR / "growth_employer_pipeline.csv"
UNIVERSITY_FILE = DATA_DIR / "growth_university_pipeline.csv"

# ─────────────────────────────────────────────────────────────────────
# Pipeline definitions (verbatim stage order from memo §7.2)
# ─────────────────────────────────────────────────────────────────────
EMPLOYER_STAGES = [
    "discovered", "enriched", "assets_created", "sent", "clicked",
    "positive_reply", "qualified", "tos_sent", "payment_added",
    "slots_reserved", "human_review", "active_account",
]
EMPLOYER_STAGE_LABEL = {
    "discovered": "Discovered",
    "enriched": "Enriched",
    "assets_created": "Assets created",
    "sent": "Sent",
    "clicked": "Clicked",
    "positive_reply": "Positive reply",
    "qualified": "Qualified",
    "tos_sent": "TOS sent",
    "payment_added": "Payment added",
    "slots_reserved": "RN slots reserved",
    "human_review": "Human review",
    "active_account": "Active account",
}

UNIVERSITY_STAGES = [
    "discovered", "enriched", "assets_created", "sent", "positive_reply",
    "faculty_call", "affiliation_review", "mou_sent", "signed",
    "cohort_onboarding", "students_activated",
]
UNIVERSITY_STAGE_LABEL = {
    "discovered": "Discovered",
    "enriched": "Enriched",
    "assets_created": "Assets created",
    "sent": "Sent",
    "positive_reply": "Positive reply",
    "faculty_call": "Faculty call",
    "affiliation_review": "Affiliation review",
    "mou_sent": "MOU/TOS sent",
    "signed": "Signed",
    "cohort_onboarding": "Cohort onboarding",
    "students_activated": "Students activated",
}

STAGE_COLOR = {
    0: "#5B6675", 1: "#5B6675", 2: "#F4A261", 3: "#F4A261",
    4: "#089478", 5: "#0BC5A0", 6: "#0BC5A0", 7: "#0BC5A0",
    8: "#0BC5A0", 9: "#0F1B2D", 10: "#0F1B2D", 11: "#0F1B2D",
}

EMPLOYER_FIELDS = [
    "target_id", "rep_email", "ccn", "name", "city", "state",
    "facility_type", "ownership_type", "rn_estimate",
    "monthly_fee_per_rn", "account_monthly_fee",
    # ── Contact enrichment (CMS public data; populated at add time) ──
    "primary_contact_name", "primary_contact_title", "primary_contact_role",
    "facility_phone", "controlling_org", "controlling_org_facility_count",
    "is_mgmt_company_run", "pe_or_mgmt_backed", "decision_maker_level",
    "rn_turnover_pct", "needs_nppes",
    "stage", "created_at", "last_touched_at",
    "assets_generated_at", "notes",
]
UNIVERSITY_FIELDS = [
    "target_id", "rep_email", "name", "country", "city",
    "program_size", "contact_name", "contact_title",
    "stage", "created_at", "last_touched_at",
    "assets_generated_at", "notes",
]

FACILITY_LABEL = {
    "SNF": "skilled-nursing facility",
    "HHA": "home-health agency",
    "DIALYSIS": "dialysis center",
    "HOSPICE": "hospice",
    "ASC": "ambulatory surgery center",
}
# What each setting is forced to turn away when RN-capacity-constrained.
FACILITY_CAPACITY_PHRASE = {
    "SNF": "admissions and held beds",
    "HHA": "home-care episodes and referrals",
    "DIALYSIS": "treatment chairs and shifts",
    "HOSPICE": "census and visits",
    "ASC": "case volume and block time",
}


# ═════════════════════════════════════════════════════════════════════
# PUBLIC-SAFE GUARD
# ═════════════════════════════════════════════════════════════════════
_BANNED = [
    "fica", "f-1", "f1 visa", "irs", "payroll tax", "payroll-tax",
    "social security tax", "medicare tax", "tax offset", "tax savings",
    "tax-exempt", "tax exempt", "withholding", "visa",
]


def _assert_public_safe(text: str, where: str = "") -> str:
    """Raise if generated outreach copy contains any banned (tax/visa) term.

    This is a hard guardrail: outreach copy is emailed to employers and hosted
    publicly, and FICA / IRS / F-1 / tax / visa language there can bring
    unwanted scrutiny and jeopardize our nurses.

    Matching is word-boundary based so legitimate words and place names don't
    false-trigger (e.g. 'speci-fica-lly', the city 'Visalia') while standalone
    banned terms still do.
    """
    low = text.lower()
    for term in _BANNED:
        if re.search(r"\b" + re.escape(term) + r"\b", low):
            raise ValueError(
                f"PUBLIC-SAFE violation in {where or 'generated copy'}: "
                f"banned term '{term}' found. Outreach copy must never "
                f"reference tax, FICA, IRS, or visa status."
            )
    return text


# ═════════════════════════════════════════════════════════════════════
# STORAGE
# ═════════════════════════════════════════════════════════════════════
def _ensure(path: Path, fields: list[str]) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(fields)


def _read(path: Path, fields: list[str]) -> pd.DataFrame:
    _ensure(path, fields)
    df = pd.read_csv(path, dtype=str).fillna("")
    for c in fields:
        if c not in df.columns:
            df[c] = ""
    return df


def _rewrite(path: Path, df: pd.DataFrame, fields: list[str]) -> None:
    df.to_csv(path, index=False, columns=fields)


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


# ═════════════════════════════════════════════════════════════════════
# CONTACT ENRICHMENT BRIDGE
# ═════════════════════════════════════════════════════════════════════
# Contact columns carried on each employer target. Sourced from CMS public
# data (NH_Ownership named owners/managers, Care Compare phones, the PECOS
# management-company signal) via contact_enrichment.lookup_contact().
_CONTACT_FIELDS = [
    "primary_contact_name", "primary_contact_title", "primary_contact_role",
    "facility_phone", "controlling_org", "controlling_org_facility_count",
    "is_mgmt_company_run", "pe_or_mgmt_backed", "decision_maker_level",
    "rn_turnover_pct", "needs_nppes",
]


def _contact_fields(ccn: str) -> dict:
    """CMS-derived contact fields for one CCN, as strings ready for the CSV.

    Returns empty strings for every field when enrichment is unavailable (no
    module, no parquet, or CCN not found) so the pipeline still works headless.
    """
    blank = {k: "" for k in _CONTACT_FIELDS}
    if _ce is None or not str(ccn).strip():
        return blank
    try:
        info = _ce.lookup_contact(str(ccn).strip())
    except Exception:
        return blank
    if not info:
        return blank
    out = {}
    for k in _CONTACT_FIELDS:
        v = info.get(k, "")
        out[k] = "" if v is None else str(v)
    return out


def _truthy(v) -> bool:
    """Interpret a stringified flag ('True'/'1'/'yes') as boolean."""
    return str(v).strip().lower() in ("true", "1", "yes", "y")


# ═════════════════════════════════════════════════════════════════════
# EMPLOYER PIPELINE — CRUD
# ═════════════════════════════════════════════════════════════════════
def add_employer_target(rep_email: str, row: dict) -> Optional[str]:
    """Add an outpatient facility to the employer demand pipeline.

    Returns target_id, or None if this CCN is already in the pipeline.
    """
    df = _read(EMPLOYER_FILE, EMPLOYER_FIELDS)
    ccn = str(row.get("ccn", "")).strip()
    if ccn and (df["ccn"] == ccn).any():
        return None  # already tracked
    target_id = f"E{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:-3]}"
    new = {
        "target_id": target_id,
        "rep_email": rep_email.strip().lower(),
        "ccn": ccn,
        "name": str(row.get("name", "")),
        "city": str(row.get("city", "")),
        "state": str(row.get("state", "")),
        "facility_type": str(row.get("facility_type", "")),
        "ownership_type": str(row.get("ownership_type", "")),
        "rn_estimate": str(row.get("rn_estimate", "")),
        "monthly_fee_per_rn": str(row.get("monthly_fee_per_rn", "")),
        "account_monthly_fee": str(row.get("account_monthly_fee", "")),
        **_contact_fields(ccn),
        "stage": "discovered",
        "created_at": _now(),
        "last_touched_at": _now(),
        "assets_generated_at": "",
        "notes": "",
    }
    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    _rewrite(EMPLOYER_FILE, df, EMPLOYER_FIELDS)
    return target_id


def add_employer_targets_bulk(rep_email: str, rows: list[dict]) -> int:
    """Add many outpatient facilities at once. Returns count newly added."""
    df = _read(EMPLOYER_FILE, EMPLOYER_FIELDS)
    existing = set(df["ccn"])
    added = []
    for row in rows:
        ccn = str(row.get("ccn", "")).strip()
        if ccn and ccn in existing:
            continue
        existing.add(ccn)
        added.append({
            "target_id": f"E{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:-3]}{len(added)}",
            "rep_email": rep_email.strip().lower(),
            "ccn": ccn,
            "name": str(row.get("name", "")),
            "city": str(row.get("city", "")),
            "state": str(row.get("state", "")),
            "facility_type": str(row.get("facility_type", "")),
            "ownership_type": str(row.get("ownership_type", "")),
            "rn_estimate": str(row.get("rn_estimate", "")),
            "monthly_fee_per_rn": str(row.get("monthly_fee_per_rn", "")),
            "account_monthly_fee": str(row.get("account_monthly_fee", "")),
            **_contact_fields(ccn),
            "stage": "discovered",
            "created_at": _now(),
            "last_touched_at": _now(),
            "assets_generated_at": "",
            "notes": "",
        })
    if added:
        df = pd.concat([df, pd.DataFrame(added)], ignore_index=True)
        _rewrite(EMPLOYER_FILE, df, EMPLOYER_FIELDS)
    return len(added)


def list_employer_targets(rep_email: Optional[str] = None) -> pd.DataFrame:
    df = _read(EMPLOYER_FILE, EMPLOYER_FIELDS)
    if rep_email:
        df = df[df["rep_email"].str.lower() == rep_email.strip().lower()]
    return df.sort_values("last_touched_at", ascending=False)


def advance_employer(target_id: str, new_stage: str) -> bool:
    if new_stage not in EMPLOYER_STAGES:
        raise ValueError(f"Invalid employer stage '{new_stage}'")
    return _update(EMPLOYER_FILE, EMPLOYER_FIELDS, target_id,
                   stage=new_stage)


def _update(path: Path, fields: list[str], target_id: str, **changes) -> bool:
    df = _read(path, fields)
    mask = df["target_id"] == target_id
    if not mask.any():
        return False
    for k, v in changes.items():
        if k in fields:
            df.loc[mask, k] = v
    df.loc[mask, "last_touched_at"] = _now()
    _rewrite(path, df, fields)
    return True


def update_employer(target_id: str, **changes) -> bool:
    return _update(EMPLOYER_FILE, EMPLOYER_FIELDS, target_id, **changes)


def remove_employer(target_id: str) -> bool:
    df = _read(EMPLOYER_FILE, EMPLOYER_FIELDS)
    new = df[df["target_id"] != target_id]
    if len(new) == len(df):
        return False
    _rewrite(EMPLOYER_FILE, new, EMPLOYER_FIELDS)
    return True


# ═════════════════════════════════════════════════════════════════════
# UNIVERSITY PIPELINE — CRUD
# ═════════════════════════════════════════════════════════════════════
def add_university_target(rep_email: str, name: str, country: str = "",
                          city: str = "", program_size: str = "",
                          contact_name: str = "",
                          contact_title: str = "") -> str:
    df = _read(UNIVERSITY_FILE, UNIVERSITY_FIELDS)
    target_id = f"U{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:-3]}"
    new = {
        "target_id": target_id,
        "rep_email": rep_email.strip().lower(),
        "name": name.strip(),
        "country": country.strip(),
        "city": city.strip(),
        "program_size": program_size.strip(),
        "contact_name": contact_name.strip(),
        "contact_title": contact_title.strip(),
        "stage": "discovered",
        "created_at": _now(),
        "last_touched_at": _now(),
        "assets_generated_at": "",
        "notes": "",
    }
    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    _rewrite(UNIVERSITY_FILE, df, UNIVERSITY_FIELDS)
    return target_id


def list_university_targets(rep_email: Optional[str] = None) -> pd.DataFrame:
    df = _read(UNIVERSITY_FILE, UNIVERSITY_FIELDS)
    if rep_email:
        df = df[df["rep_email"].str.lower() == rep_email.strip().lower()]
    return df.sort_values("last_touched_at", ascending=False)


def advance_university(target_id: str, new_stage: str) -> bool:
    if new_stage not in UNIVERSITY_STAGES:
        raise ValueError(f"Invalid university stage '{new_stage}'")
    return _update(UNIVERSITY_FILE, UNIVERSITY_FIELDS, target_id,
                   stage=new_stage)


def update_university(target_id: str, **changes) -> bool:
    return _update(UNIVERSITY_FILE, UNIVERSITY_FIELDS, target_id, **changes)


def remove_university(target_id: str) -> bool:
    df = _read(UNIVERSITY_FILE, UNIVERSITY_FIELDS)
    new = df[df["target_id"] != target_id]
    if len(new) == len(df):
        return False
    _rewrite(UNIVERSITY_FILE, new, UNIVERSITY_FIELDS)
    return True


# ═════════════════════════════════════════════════════════════════════
# TARGET DISCOVERY (employers) — pulls from the priced outpatient universe
# ═════════════════════════════════════════════════════════════════════
def discover_employer_targets(
    priced_df: pd.DataFrame,
    states: Optional[list[str]] = None,
    facility_types: Optional[list[str]] = None,
    min_rn: int = 1,
    independent_only: bool = True,
    limit: int = 50,
) -> pd.DataFrame:
    """Rank long-tail outpatient/post-acute employers for AI-SDR outreach.

    The memo's thesis: these are capacity-constrained, fragmented, and have
    "no agency incumbent in many settings" — so independent ownership is the
    sweet spot. We rank by RN capacity opportunity (rn_estimate) so reps work
    the biggest reservations first.
    """
    df = priced_df.copy()
    if states:
        df = df[df["state"].isin(states)]
    if facility_types:
        df = df[df["facility_type"].isin(facility_types)]
    if "rn_estimate" in df.columns:
        df = df[pd.to_numeric(df["rn_estimate"], errors="coerce").fillna(0) >= min_rn]
    if independent_only and "health_system_id" in df.columns:
        # Fragmented/independent = no parent system (the AI-SDR sweet spot).
        indep = df["health_system_id"].fillna("").isin(["", "independent"])
        if indep.any():
            df = df[indep]
    sort_col = "rn_estimate" if "rn_estimate" in df.columns else None
    if sort_col:
        df = df.sort_values(sort_col, ascending=False, key=lambda s: pd.to_numeric(s, errors="coerce").fillna(0))
    df = df.head(limit)
    # Attach CMS-derived decision-maker / phone / operator columns for display.
    if _ce is not None:
        try:
            df = _ce.enrich(df)
        except Exception:
            pass
    return df


# ═════════════════════════════════════════════════════════════════════
# OUTREACH ASSET GENERATION  (PUBLIC-SAFE — no tax/visa language)
# ═════════════════════════════════════════════════════════════════════
def _fmt_money(x) -> str:
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return "—"


def generate_employer_assets(row: dict) -> dict:
    """Generate the personalized outreach bundle for one employer target.

    Returns keys: subject, email_note, text_cta, video_script,
    landing_headline, landing_body, landing_cta.

    Framing is strictly operational: permanent, fully-credentialed RNs;
    relief from travel/agency reliance; predictable flat monthly cost;
    multi-year tenure. NO tax / FICA / visa language (enforced).
    """
    name = str(row.get("name", "this facility")).strip().title() or "this facility"
    city = str(row.get("city", "")).strip().title()
    state = str(row.get("state", "")).strip().upper()
    ftype = str(row.get("facility_type", "")).strip().upper()
    setting = FACILITY_LABEL.get(ftype, "care setting")
    setting_title = setting.capitalize()
    capacity_phrase = FACILITY_CAPACITY_PHRASE.get(ftype, "patients and shifts")
    try:
        n_rn = int(float(row.get("rn_estimate", 0) or 0))
    except (TypeError, ValueError):
        n_rn = 0
    rn_word = "registered nurse" if n_rn == 1 else "registered nurses"
    loc = f"{city}, {state}".strip(", ") if (city or state) else "your area"
    fee = row.get("monthly_fee_per_rn", "")
    fee_str = _fmt_money(fee) if fee not in ("", None) else ""

    cap_line = (
        f"roughly {n_rn} permanent {rn_word} of added capacity"
        if n_rn else "permanent RN capacity sized to your site"
    )

    subject = f"Permanent RN capacity for {name}"

    email_note = (
        f"Hi {name} team,\n\n"
        f"You run a {setting} in {loc}. Most {setting_title.lower()} leaders we "
        f"talk to aren't short on demand — they're turning away "
        f"{capacity_phrase} because they can't hire enough permanent RNs, and "
        f"travel/agency coverage is expensive and temporary.\n\n"
        f"Florence places permanent, fully-credentialed registered nurses on "
        f"multi-year commitments at a predictable flat monthly cost per nurse — "
        f"no agency markups, no churn. For a site your size that's about "
        f"{cap_line}. We handle sourcing, screening, credentialing, and "
        f"onboarding end to end.\n\n"
        f"Worth a short call to size the capacity you could add?"
    )

    text_cta = (
        "Book a 20-minute workforce call — or reserve RN capacity directly "
        "and we'll confirm a start window."
    )

    video_script = (
        f"[0:00] Hi — this is Florence, and this note is specifically for "
        f"{name}.\n"
        f"[0:08] You run a {setting} in {loc}. We work with {setting_title.lower()} "
        f"teams that have the demand but not enough permanent RNs to staff it.\n"
        f"[0:25] Florence builds permanent RN capacity. Fully-credentialed "
        f"registered nurses, placed on multi-year commitments, at one "
        f"predictable monthly cost per nurse — no agency markups.\n"
        f"[0:45] For a site your size, that's about {cap_line}: more "
        f"{capacity_phrase} you can actually say yes to.\n"
        f"[1:00] If that's useful, book a 20-minute call or reserve capacity on "
        f"the page below. Thanks for watching."
    )

    landing_headline = f"Permanent RN capacity for {name}"
    landing_body = (
        f"Stop turning away {capacity_phrase}. Florence places permanent, "
        f"fully-credentialed registered nurses on multi-year commitments at a "
        f"predictable flat monthly cost per nurse — sourcing, screening, "
        f"credentialing, and onboarding handled for you."
    )
    if fee_str:
        landing_body += (
            f" For a {setting} like yours, that's about {fee_str} per nurse "
            f"per month — billing starts only when your nurse starts."
        )
    landing_cta = "Reserve RN capacity  ·  Book a 20-minute call"

    out = {
        "subject": subject,
        "email_note": email_note,
        "text_cta": text_cta,
        "video_script": video_script,
        "landing_headline": landing_headline,
        "landing_body": landing_body,
        "landing_cta": landing_cta,
    }
    for k, v in out.items():
        _assert_public_safe(v, where=f"employer.{k}")
    return out


def generate_university_assets(row: dict) -> dict:
    """Generate the personalized outreach bundle for a university/program.

    Positioning (memo §8): public benefit + free affiliation. We do NOT ask
    universities to send nurses away — we offer free clinical-judgment
    education, readiness analytics, and benchmarking, plus an opt-in U.S.
    pathway for students who want it. No tax / visa language.
    """
    name = str(row.get("name", "your program")).strip() or "your program"
    country = str(row.get("country", "")).strip()
    contact = str(row.get("contact_name", "")).strip()
    title = str(row.get("contact_title", "")).strip()
    greeting = (
        f"Dear {('Dean ' + contact) if (title.lower().startswith('dean') and contact) else (contact or 'faculty leadership')}"
    )
    where = f" in {country}" if country else ""

    subject = f"Free clinical-judgment education affiliation for {name}"

    email_note = (
        f"{greeting},\n\n"
        f"{name}{where} is exactly the kind of nursing program we built "
        f"Florence's global education network for. We give partner programs — "
        f"at no cost — AI-native clinical-judgment teaching tools, readiness "
        f"analytics, and international benchmarking your faculty can use "
        f"directly with students.\n\n"
        f"Affiliation strengthens outcomes for every student, including those "
        f"who go on to practice locally. For students who want it, we also open "
        f"an optional pathway to U.S. clinical opportunities and financing — but "
        f"the affiliation stands on its own as an educational partnership.\n\n"
        f"Could we set up a short faculty call to walk through it?"
    )

    text_cta = (
        "Book a 30-minute faculty call to review the affiliation pathway and "
        "activate a pilot cohort."
    )

    video_script = (
        f"[0:00] Hello — this is Florence, and this message is for the faculty "
        f"at {name}.\n"
        f"[0:10] We partner with nursing programs around the world to share "
        f"AI-native clinical-judgment education, readiness analytics, and "
        f"international benchmarking — free for affiliated programs.\n"
        f"[0:30] The goal is better-prepared nurses everywhere. Students who "
        f"stay local graduate stronger; students who want international clinical "
        f"opportunities get an optional, supported pathway.\n"
        f"[0:50] If your faculty are open to it, book a short call below and "
        f"we'll set up a pilot cohort. Thank you."
    )

    landing_headline = f"A free clinical-judgment education affiliation for {name}"
    landing_body = (
        "Affiliate with Florence's global nursing-education network: AI-native "
        "clinical-judgment teaching tools, readiness analytics, and "
        "international benchmarking at no cost — plus an optional U.S. clinical "
        "pathway for students who want it."
    )
    landing_cta = "Book a faculty call  ·  Review the affiliation"

    out = {
        "subject": subject,
        "email_note": email_note,
        "text_cta": text_cta,
        "video_script": video_script,
        "landing_headline": landing_headline,
        "landing_body": landing_body,
        "landing_cta": landing_cta,
    }
    for k, v in out.items():
        _assert_public_safe(v, where=f"university.{k}")
    return out


# ═════════════════════════════════════════════════════════════════════
# BOARD KPI PACKAGE — Growth Automation row (memo §15)
# ═════════════════════════════════════════════════════════════════════
def _reached(df: pd.DataFrame, stages: list[str], stage_key: str) -> int:
    """Count rows whose stage index >= the index of stage_key."""
    if df.empty:
        return 0
    idx = stages.index(stage_key)
    pos = df["stage"].map(lambda s: stages.index(s) if s in stages else -1)
    return int((pos >= idx).sum())


def growth_kpis(rep_email: Optional[str] = None) -> dict:
    """Compute the Growth Automation board KPIs from current pipeline state.

    Metrics that require live email infrastructure (deliverability, open/click
    rates) are returned as None — we show them as 'wires up at send time'
    rather than fabricating numbers.
    """
    emp = list_employer_targets(rep_email)
    uni = list_university_targets(rep_email)

    return {
        # both sides
        "targets_discovered": len(emp) + len(uni),
        "employers_in_pipeline": len(emp),
        "universities_in_pipeline": len(uni),
        # assets / sending
        "assets_generated": int((emp["assets_generated_at"] != "").sum())
                            + int((uni["assets_generated_at"] != "").sum()),
        "emails_sent": _reached(emp, EMPLOYER_STAGES, "sent")
                       + _reached(uni, UNIVERSITY_STAGES, "sent"),
        # engagement
        "positive_replies": _reached(emp, EMPLOYER_STAGES, "positive_reply")
                            + _reached(uni, UNIVERSITY_STAGES, "positive_reply"),
        "meetings_booked": _reached(emp, EMPLOYER_STAGES, "qualified")
                           + _reached(uni, UNIVERSITY_STAGES, "faculty_call"),
        # employer conversion
        "tos_payment_setups": _reached(emp, EMPLOYER_STAGES, "tos_sent"),
        "rn_slots_reserved": _reached(emp, EMPLOYER_STAGES, "slots_reserved"),
        "active_accounts": _reached(emp, EMPLOYER_STAGES, "active_account"),
        # university supply
        "university_affiliations": _reached(uni, UNIVERSITY_STAGES, "signed"),
        "students_activated": _reached(uni, UNIVERSITY_STAGES, "students_activated"),
        # not measurable until sending is wired
        "deliverability": None,
        "open_click_rate": None,
    }


# ═════════════════════════════════════════════════════════════════════
# STREAMLIT VIEW
# ═════════════════════════════════════════════════════════════════════
def _stat_html(icon: str, value, label: str) -> str:
    return (
        f"<div class='fl-stat'><span class='icon'>{icon}</span>"
        f"<div><div class='value'>{value}</div>"
        f"<div class='label'>{label}</div></div></div>"
    )


def _stage_chip(stage: str, stages: list[str], labels: dict) -> str:
    idx = stages.index(stage) if stage in stages else 0
    color = STAGE_COLOR.get(idx, "#5B6675")
    return (
        f"<span style='display:inline-block; padding:2px 10px; "
        f"border-radius:12px; background:{color}1A; color:{color}; "
        f"font-family:Inter,sans-serif; font-size:0.7rem; font-weight:600; "
        f"letter-spacing:0.06em; text-transform:uppercase;'>"
        f"{labels.get(stage, stage)}</span>"
    )


def _render_kpis(st, kpis: dict) -> None:
    rows = [
        ("hub", kpis["targets_discovered"], "Targets discovered"),
        ("draw", kpis["assets_generated"], "Asset bundles generated"),
        ("send", kpis["emails_sent"], "Marked sent"),
        ("forum", kpis["positive_replies"], "Positive replies"),
        ("event", kpis["meetings_booked"], "Meetings / calls booked"),
        ("event_seat", kpis["rn_slots_reserved"], "RN slots reserved"),
        ("verified", kpis["active_accounts"], "Active employer accounts"),
        ("school", kpis["university_affiliations"], "University affiliations"),
    ]
    cols = st.columns(4)
    for i, (icon, val, label) in enumerate(rows):
        with cols[i % 4]:
            st.markdown(
                f"<div class='fl-stat'><span class='icon' "
                f"style=\"font-family:'Material Symbols Rounded'\">{icon}</span>"
                f"<div><div class='value'>{val}</div>"
                f"<div class='label'>{label}</div></div></div>",
                unsafe_allow_html=True,
            )


def _render_selfserve_funnel(st) -> None:
    """The employer self-serve control-point funnel (memo §9) as a 5-stage flow."""
    steps = [
        ("event_seat", "Reserve capacity", "RN count, setting, state, start window"),
        ("description", "Agree to TOS", "Start, cancellation, deposit, billing timing"),
        ("credit_card", "Add card / ACH", "Stored by processor — not by Florence"),
        ("verified_user", "Human review", "Facility, role, wage & readiness checked"),
        ("payments", "Start billing", "Billing begins only at the start milestone"),
    ]
    nodes = "".join(
        f"<div class='fl-flow-stage'>"
        f"<div class='icon'>{icon}</div>"
        f"<div class='stage-name'>{name}</div>"
        f"<div class='gate'>{gate}</div></div>"
        for icon, name, gate in steps
    )
    st.markdown(f"<div class='fl-flow'>{nodes}</div>", unsafe_allow_html=True)


def _render_asset_bundle(st, assets: dict, key_prefix: str) -> None:
    """Show a generated outreach bundle in copy-friendly blocks."""
    st.markdown("**Email — subject line**")
    st.code(assets["subject"], language=None)
    st.markdown("**Email — personalized note**")
    st.code(assets["email_note"], language=None)
    st.markdown("**Text CTA (above the video thumbnail)**")
    st.code(assets["text_cta"], language=None)
    st.markdown("**60–120s video script**")
    st.code(assets["video_script"], language=None)
    st.markdown("**Landing page**")
    st.code(
        f"{assets['landing_headline']}\n\n{assets['landing_body']}\n\n"
        f"[ {assets['landing_cta']} ]",
        language=None,
    )
    st.caption(
        ":material/verified_user: Public-safe: this copy is screened to never "
        "mention tax, FICA, or visa status. Disclose AI-generated video where "
        "appropriate; human review before any binding placement."
    )


def streamlit_growth_view(st, priced_df: pd.DataFrame, rep_email: str,
                          territory_states: Optional[list[str]] = None) -> None:
    """Render the Growth Automation engine: overview + two acquisition pipelines."""
    rep_email = (rep_email or "demo@florence.dev").strip().lower()

    tab_overview, tab_emp, tab_uni = st.tabs(
        ["Overview", "Employer demand", "University supply"]
    )

    # ─── OVERVIEW ────────────────────────────────────────────────────
    with tab_overview:
        st.markdown(
            "Growth Automation acquires **both sides** of the network with low "
            "incremental headcount: long-tail outpatient **employers** on the "
            "demand side, global nursing **universities** on the supply side. "
            "The platform already prices the employer universe — this turns each "
            "priced target into a tracked, personalized outreach motion."
        )
        st.markdown("#### Board KPI snapshot")
        _render_kpis(st, growth_kpis(rep_email))
        st.caption(
            "Deliverability and open/click rates wire up when sending goes live "
            "through Gmail/Streak — shown here so the board view is ready."
        )

        st.markdown("#### Employer self-serve funnel — with control points")
        st.caption(
            "Self-serve but not unsupervised: human review gates live nurses, "
            "immigration-sensitive representations, and binding commitments."
        )
        _render_selfserve_funnel(st)

    # ─── EMPLOYER DEMAND ─────────────────────────────────────────────
    with tab_emp:
        _streamlit_employer_tab(st, priced_df, rep_email, territory_states)

    # ─── UNIVERSITY SUPPLY ───────────────────────────────────────────
    with tab_uni:
        _streamlit_university_tab(st, rep_email)


def _contact_line_html(t) -> str:
    """Internal contact line for an employer card — named decision-maker, phone,
    operator, and management-company / PE-REIT badges. '' when nothing is known.

    Contact facts (names, titles, phones, operator) never carry tax/visa
    language, so this is safe for the internal pipeline view.
    """
    name = str(t.get("primary_contact_name", "")).strip()
    title = str(t.get("primary_contact_title", "")).strip()
    phone = str(t.get("facility_phone", "")).strip()
    org = str(t.get("controlling_org", "")).strip()
    n_sites = str(t.get("controlling_org_facility_count", "")).strip()
    is_mgmt = _truthy(t.get("is_mgmt_company_run", ""))
    pe = _truthy(t.get("pe_or_mgmt_backed", ""))
    needs_nppes = _truthy(t.get("needs_nppes", ""))

    parts = []
    person = ""
    if name:
        person = f"<b style='color:#0F1B2D'>{name}</b>"
        if title:
            person += f" <span style='color:#5B6675'>· {title}</span>"
    if phone:
        person += f"{' · ' if person else ''}<span style='color:#0F1B2D'>{phone}</span>"
    if person:
        parts.append(f"<div style='font-size:0.85rem; margin-top:6px;'>{person}</div>")
    elif needs_nppes:
        parts.append(
            "<div style='font-size:0.78rem; color:#9AA4B2; margin-top:6px;'>"
            "No CMS phone/name on file — NPPES lookup needed</div>"
        )

    op = ""
    if org:
        sites = f" · {n_sites} sites" if n_sites and n_sites not in ("0", "") else ""
        op = f"<span style='color:#5B6675'>Operator: {org}{sites}</span>"
    badges = ""
    if is_mgmt:
        badges += ("<span style='background:#0F1B2D;color:#fff;border-radius:4px;"
                   "padding:1px 7px;font-size:0.68rem;margin-left:6px;'>MANAGEMENT CO</span>")
    if pe:
        badges += ("<span style='background:#8A6D3B;color:#fff;border-radius:4px;"
                   "padding:1px 7px;font-size:0.68rem;margin-left:6px;'>PE / REIT-BACKED</span>")
    if op or badges:
        parts.append(f"<div style='font-size:0.8rem; margin-top:3px;'>{op}{badges}</div>")
    return "".join(parts)


def _render_operator_rollup(st, priced_df, rep_email) -> bool:
    """Land-once-unlock-N view: rank multi-site operators and let a rep add an
    operator's whole portfolio in one click. Returns True if it rendered."""
    if _ce is None:
        return False
    try:
        rollup = _ce.load_rollup()
    except Exception:
        return False
    if rollup is None or rollup.empty or "n_facilities" not in rollup.columns:
        return False

    st.markdown("#### 2 · Target operators, not just sites")
    st.caption(
        "The wedge into the long tail is the management company, not the "
        "100-bed site. Land one operator and you unlock its whole portfolio. "
        "Ranked by facilities controlled."
    )
    top = rollup.sort_values("n_facilities", ascending=False).head(40)
    show_cols = [c for c in
                 ["controlling_org", "n_facilities", "total_rn_capacity",
                  "n_states", "pe_or_mgmt_backed", "sample_facilities"]
                 if c in top.columns]
    st.dataframe(
        top[show_cols].rename(columns={
            "controlling_org": "Operator", "n_facilities": "Sites",
            "total_rn_capacity": "RN capacity", "n_states": "States",
            "pe_or_mgmt_backed": "PE/REIT", "sample_facilities": "Example sites",
        }),
        use_container_width=True, hide_index=True, height=280,
    )

    has_ccn = priced_df is not None and not priced_df.empty and "ccn" in priced_df.columns
    op_names = top["controlling_org"].dropna().tolist()
    pick = st.selectbox(
        "Add an operator's entire portfolio to your pipeline",
        options=["—"] + op_names, key="ga_emp_operator_pick",
    )
    if pick and pick != "—" and has_ccn:
        try:
            ccns = {str(c) for c in _ce.ccns_for_operator(pick)}
        except Exception:
            ccns = set()
        sites = priced_df[priced_df["ccn"].astype(str).isin(ccns)]
        st.markdown(
            f"**{pick}** — {len(ccns)} sites in CMS data, "
            f"{len(sites)} matched in the priced universe."
        )
        if not sites.empty and st.button(
            f":material/domain_add: Add all {len(sites)} {pick} sites to my pipeline",
            type="primary", key="ga_emp_addoperator",
        ):
            rows = [{
                "ccn": r.get("ccn", ""), "name": r.get("name", ""),
                "city": r.get("city", ""), "state": r.get("state", ""),
                "facility_type": r.get("facility_type", ""),
                "ownership_type": r.get("ownership_type", ""),
                "rn_estimate": r.get("rn_estimate", ""),
                "monthly_fee_per_rn": r.get("florence_fee_per_rn_month", ""),
                "account_monthly_fee": r.get("account_monthly_florence_fee", ""),
            } for _, r in sites.iterrows()]
            n = add_employer_targets_bulk(rep_email, rows)
            st.success(f"Added {n} new {pick} sites ({len(rows) - n} already tracked).")
            st.rerun()
    return True


def _streamlit_employer_tab(st, priced_df, rep_email, territory_states) -> None:
    st.markdown("#### 1 · Discover long-tail employers")
    st.caption(
        "Fragmented outpatient & post-acute sites — numerous, capacity-"
        "constrained, often with no agency incumbent. Ranked by RN capacity "
        "opportunity so you work the biggest reservations first."
    )

    if priced_df is None or priced_df.empty:
        st.warning("Outpatient pricing data unavailable.")
        return

    all_states = sorted(priced_df["state"].dropna().unique().tolist())
    default_states = (
        [s for s in (territory_states or []) if s in all_states] or []
    )
    fc1, fc2 = st.columns(2)
    with fc1:
        states = st.multiselect(
            "States", options=all_states, default=default_states,
            key="ga_emp_states",
            help="Defaults to your territory when access control is on.",
        )
        ftypes = st.multiselect(
            "Facility types",
            options=["SNF", "HHA", "DIALYSIS", "HOSPICE", "ASC"],
            default=["SNF", "HHA"],
            key="ga_emp_ftypes",
        )
    with fc2:
        min_rn = st.slider("Minimum RN capacity", 1, 20, 3, key="ga_emp_minrn")
        independent_only = st.toggle(
            "Independent sites only (no parent system)", value=True,
            key="ga_emp_indep",
            help="The AI-SDR sweet spot: fragmented buyers with no incumbent.",
        )
        limit = st.slider("How many to show", 10, 200, 50, step=10,
                          key="ga_emp_limit")

    results = discover_employer_targets(
        priced_df, states=states or None, facility_types=ftypes or None,
        min_rn=min_rn, independent_only=independent_only, limit=limit,
    )
    st.markdown(
        f"**{len(results):,}** targets match "
        f"(showing top {min(len(results), limit):,} by RN capacity)."
    )

    if not results.empty:
        show_cols = [c for c in
                     ["name", "city", "state", "facility_type",
                      "ownership_type", "rn_estimate", "florence_fee_per_rn_month",
                      "account_monthly_florence_fee",
                      "primary_contact_name", "primary_contact_title",
                      "facility_phone", "controlling_org"]
                     if c in results.columns]
        st.dataframe(
            results[show_cols].rename(columns={
                "name": "Facility", "city": "City", "state": "ST",
                "facility_type": "Type", "ownership_type": "Ownership",
                "rn_estimate": "RNs", "florence_fee_per_rn_month": "$/RN/mo",
                "account_monthly_florence_fee": "Account $/mo",
                "primary_contact_name": "Decision-maker",
                "primary_contact_title": "Title",
                "facility_phone": "Phone",
                "controlling_org": "Operator",
            }),
            use_container_width=True, hide_index=True, height=280,
        )
        if st.button(
            f":material/playlist_add: Add these {len(results)} to my pipeline",
            type="primary", key="ga_emp_addall",
        ):
            rows = []
            for _, r in results.iterrows():
                rows.append({
                    "ccn": r.get("ccn", ""), "name": r.get("name", ""),
                    "city": r.get("city", ""), "state": r.get("state", ""),
                    "facility_type": r.get("facility_type", ""),
                    "ownership_type": r.get("ownership_type", ""),
                    "rn_estimate": r.get("rn_estimate", ""),
                    "monthly_fee_per_rn": r.get("florence_fee_per_rn_month", ""),
                    "account_monthly_fee": r.get("account_monthly_florence_fee", ""),
                })
            n = add_employer_targets_bulk(rep_email, rows)
            st.success(f"Added {n} new targets ({len(rows) - n} already tracked).")
            st.rerun()

    # ── Target operators (land once, unlock N) ──
    st.markdown("---")
    shown = _render_operator_rollup(st, priced_df, rep_email)

    # ── Active employer pipeline ──
    st.markdown("---")
    st.markdown(f"#### {'3' if shown else '2'} · Work your employer pipeline")
    emp = list_employer_targets(rep_email)
    if emp.empty:
        st.info("No employer targets yet. Discover and add some above.",
                icon=":material/info:")
        return

    for _, t in emp.iterrows():
        tid = t["target_id"]
        with st.container(border=True):
            head_l, head_r = st.columns([4, 1])
            with head_l:
                st.markdown(
                    _stage_chip(t["stage"], EMPLOYER_STAGES, EMPLOYER_STAGE_LABEL)
                    + f"<div style='font-family:Newsreader,serif; font-size:1.2rem; "
                    f"color:#0F1B2D; margin-top:4px;'>{str(t['name']).title()}</div>"
                    f"<div style='color:#5B6675; font-size:0.83rem;'>"
                    f"{t['facility_type']} · {str(t['city']).title()}, {t['state']} · "
                    f"{t['rn_estimate']} RN capacity</div>"
                    + _contact_line_html(t),
                    unsafe_allow_html=True,
                )
            with head_r:
                if st.button("Remove", key=f"ga_emp_rm_{tid}",
                             use_container_width=True):
                    remove_employer(tid)
                    st.rerun()

            adv_l, adv_r = st.columns([3, 1])
            with adv_l:
                new_stage = st.selectbox(
                    "Stage", options=EMPLOYER_STAGES,
                    index=EMPLOYER_STAGES.index(t["stage"])
                    if t["stage"] in EMPLOYER_STAGES else 0,
                    format_func=lambda s: EMPLOYER_STAGE_LABEL[s],
                    key=f"ga_emp_stage_{tid}", label_visibility="collapsed",
                )
            with adv_r:
                if st.button("Update", key=f"ga_emp_upd_{tid}",
                             use_container_width=True):
                    advance_employer(tid, new_stage)
                    st.rerun()

            with st.expander(":material/auto_awesome: Generate outreach assets"):
                assets = generate_employer_assets(t.to_dict())
                _render_asset_bundle(st, assets, key_prefix=f"emp_{tid}")
                if st.button("Mark assets created → advance stage",
                             key=f"ga_emp_assets_{tid}"):
                    update_employer(tid, assets_generated_at=_now())
                    if EMPLOYER_STAGES.index(t["stage"]) < EMPLOYER_STAGES.index("assets_created"):
                        advance_employer(tid, "assets_created")
                    st.rerun()


def _streamlit_university_tab(st, rep_email) -> None:
    st.markdown("#### Add a university / nursing program")
    st.caption(
        "Positioning is public benefit + free affiliation — we never ask "
        "programs to send nurses away. Add programs as you discover them; "
        "the outreach copy is generated per program."
    )
    with st.form("ga_uni_add"):
        c1, c2 = st.columns(2)
        with c1:
            uname = st.text_input("Program / university name",
                                  placeholder="e.g. St. Paul University College of Nursing")
            ucountry = st.text_input("Country", placeholder="e.g. Philippines")
            ucity = st.text_input("City (optional)")
        with c2:
            usize = st.text_input("Program size (optional)",
                                  placeholder="e.g. ~400 BSN students")
            ucontact = st.text_input("Contact name (optional)")
            utitle = st.text_input("Contact title (optional)",
                                   placeholder="e.g. Dean, Faculty lead")
        submitted = st.form_submit_button(
            ":material/add: Add program", type="primary",
            use_container_width=True,
        )
    if submitted and uname.strip():
        add_university_target(rep_email, uname, ucountry, ucity, usize,
                              ucontact, utitle)
        st.success(f"Added {uname.strip()}.")
        st.rerun()

    st.markdown("---")
    st.markdown("#### Your university pipeline")
    uni = list_university_targets(rep_email)
    if uni.empty:
        st.info("No programs yet. Add one above.", icon=":material/info:")
        return

    for _, t in uni.iterrows():
        tid = t["target_id"]
        with st.container(border=True):
            head_l, head_r = st.columns([4, 1])
            with head_l:
                meta = " · ".join(
                    x for x in [t["country"], t["program_size"]] if x
                )
                st.markdown(
                    _stage_chip(t["stage"], UNIVERSITY_STAGES, UNIVERSITY_STAGE_LABEL)
                    + f"<div style='font-family:Newsreader,serif; font-size:1.2rem; "
                    f"color:#0F1B2D; margin-top:4px;'>{t['name']}</div>"
                    + (f"<div style='color:#5B6675; font-size:0.83rem;'>{meta}</div>"
                       if meta else ""),
                    unsafe_allow_html=True,
                )
            with head_r:
                if st.button("Remove", key=f"ga_uni_rm_{tid}",
                             use_container_width=True):
                    remove_university(tid)
                    st.rerun()

            adv_l, adv_r = st.columns([3, 1])
            with adv_l:
                new_stage = st.selectbox(
                    "Stage", options=UNIVERSITY_STAGES,
                    index=UNIVERSITY_STAGES.index(t["stage"])
                    if t["stage"] in UNIVERSITY_STAGES else 0,
                    format_func=lambda s: UNIVERSITY_STAGE_LABEL[s],
                    key=f"ga_uni_stage_{tid}", label_visibility="collapsed",
                )
            with adv_r:
                if st.button("Update", key=f"ga_uni_upd_{tid}",
                             use_container_width=True):
                    advance_university(tid, new_stage)
                    st.rerun()

            with st.expander(":material/auto_awesome: Generate outreach assets"):
                assets = generate_university_assets(t.to_dict())
                _render_asset_bundle(st, assets, key_prefix=f"uni_{tid}")
                if st.button("Mark assets created → advance stage",
                             key=f"ga_uni_assets_{tid}"):
                    update_university(tid, assets_generated_at=_now())
                    if UNIVERSITY_STAGES.index(t["stage"]) < UNIVERSITY_STAGES.index("assets_created"):
                        advance_university(tid, "assets_created")
                    st.rerun()


# ─── CLI smoke test ──────────────────────────────────────────────────
def _main() -> None:
    print("--- Growth Automation smoke test ---")
    row = {
        "ccn": "999999", "name": "SUNRISE SKILLED NURSING",
        "city": "Fresno", "state": "CA", "facility_type": "SNF",
        "ownership_type": "For-profit", "rn_estimate": 8,
        "monthly_fee_per_rn": 3200, "account_monthly_fee": 25600,
    }
    assets = generate_employer_assets(row)
    print("EMPLOYER subject:", assets["subject"])
    print(assets["email_note"][:160], "...")
    uni = generate_university_assets({
        "name": "University of Santo Tomas College of Nursing",
        "country": "Philippines", "contact_name": "Reyes",
        "contact_title": "Dean",
    })
    print("\nUNIVERSITY subject:", uni["subject"])
    print(uni["email_note"][:160], "...")
    print("\nKPIs:", growth_kpis())
    print("All generated copy passed the public-safe guard. OK")


if __name__ == "__main__":
    _main()
