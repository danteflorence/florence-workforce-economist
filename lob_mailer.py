"""
Direct-mail composer + tracker for the AI SDR (Lob).

PRINCIPLE: the SDR *drafts and queues*; a human *sends*. Physical mail costs
money per piece and reaches real organizations, so `draft_and_send` only calls
the Lob API when LOB_API_KEY is set AND `live=True` is explicitly passed;
otherwise it returns a dry-run preview and logs the piece as 'drafted'. Every
action is tracked by org in data/mail_log.csv.

YOU PROVISION (the agent can't): a Lob account + the LOB_API_KEY env var.
Real sending also needs a deliverable street address (enrich via NPPES by NPI,
or rep-entered) — see contacts.py `address1` / `zip`.

Copy is purely the value + activation path. No FICA / IRS / visa / tax language
ever goes on a mailpiece (standing compliance rule).
"""
from __future__ import annotations

import csv
import os
import secrets
import string
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
MAIL_LOG = DATA_DIR / "mail_log.csv"
SIGNUP_BASE = os.environ.get("FLORENCE_SIGNUP_URL", "https://app.florence.health/activate")

FIELDS = [
    "entity_type", "entity_id", "org_name", "piece_type", "retrieval_code",
    "to_name", "address1", "city", "state", "zip", "status", "lob_id",
    "monthly_fee", "term_impact", "drafted_at", "sent_at", "responded_at",
    "by", "notes",
]
# status: drafted | sent | responded | failed


def retrieval_code() -> str:
    """Human-friendly activation code, e.g. FLOR-7QК… (ambiguous chars removed)."""
    alphabet = "".join(c for c in (string.ascii_uppercase + string.digits)
                       if c not in "O0I1")
    return "FLOR-" + "".join(secrets.choice(alphabet) for _ in range(5))


def is_configured() -> bool:
    return bool(os.environ.get("LOB_API_KEY"))


def _ensure() -> None:
    if not MAIL_LOG.exists():
        MAIL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(MAIL_LOG, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure()
    try:
        df = pd.read_csv(MAIL_LOG, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=FIELDS)
    for c in FIELDS:
        if c not in df.columns:
            df[c] = ""
    return df


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return f"${v:,.0f}"


def compose(*, org_name: str, contact_name: str, monthly_fee, term_impact,
            code: str, piece_type: str = "postcard") -> dict:
    """On-brand, compliance-clean mail copy. The SDR drafts this."""
    url = f"{SIGNUP_BASE}?code={code}"
    body = (
        f"{org_name}: at your current premium-agency spend, Florence projects about "
        f"{_money(term_impact)} of impact over 24 months — the same hours, staffed by "
        f"permanent, internationally educated RNs at {_money(monthly_fee)}/mo. Activate "
        f"your quote and review available candidates with code {code}."
    )
    return {
        "piece_type": piece_type,
        "to": contact_name or "Nursing leadership",
        "headline": "Same shifts. Permanent nurses. A lower number.",
        "body": body,
        "cta": f"Activate at {url}",
        "url": url,
        "code": code,
    }


# ════════════════════════════════════════════════════════════════════
# Mailpiece visual design — on-brand HTML Lob renders to PDF.
# Florence editorial palette: teal #0ABAB5 (text #067F7B), royal purple
# #7340C4 (text #5B2DA8), ink #101828, ink-2 #475467. Playfair Display is the
# zero-setup stand-in for GT Sectra Display; Inter body; JetBrains Mono numerics.
# Copy stays value + activation only — never FICA/visa/tax/immigration.
# ════════════════════════════════════════════════════════════════════
_FONTS = (
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Playfair+Display:wght@500;700&family=Inter:wght@400;600;700&"
    'family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">'
)


def _first(name: str) -> str:
    parts = (name or "").strip().split()
    return parts[0] if parts else ""


def _from_address() -> dict:
    """Florence return address for live Lob sends, from env (else empty → the
    rep/Lob default applies). Lob requires a `from` on real postcards + letters."""
    keys = {
        "from[name]": "FLORENCE_RETURN_NAME", "from[address_line1]": "FLORENCE_RETURN_LINE1",
        "from[address_city]": "FLORENCE_RETURN_CITY", "from[address_state]": "FLORENCE_RETURN_STATE",
        "from[address_zip]": "FLORENCE_RETURN_ZIP",
    }
    out = {k: os.environ.get(env, "") for k, env in keys.items()}
    return {k: v for k, v in out.items() if v}


_LETTER_CSS = """
@page { size: 8.5in 11in; margin: 0; }
* { box-sizing: border-box; }
body { margin:0; font-family:'Inter',Helvetica,Arial,sans-serif; color:#101828; font-size:11.5pt; line-height:1.5; }
.sheet { width:8.5in; height:11in; padding:0.8in 0.9in; position:relative; }
.wm { font-family:'Playfair Display',Georgia,serif; font-weight:700; font-size:23pt; color:#067F7B; letter-spacing:.01em; }
.rule { height:3px; background:#0ABAB5; width:100%; margin:9px 0 30px; }
.recipient { font-size:11pt; color:#101828; margin:6px 0 26px; line-height:1.45; }
.greeting { margin:0 0 14px; }
p { margin:0 0 13px; }
.signoff { margin-top:22px; }
.muted { color:#475467; }
.callout { margin-top:26px; border-left:4px solid #7340C4; background:#F4F0FB; padding:12px 16px; border-radius:0 8px 8px 0; font-size:10.5pt; }
.callout .ek { font-family:'Inter'; font-weight:700; text-transform:uppercase; letter-spacing:.10em; font-size:8pt; color:#5B2DA8; }
.mono { font-family:'JetBrains Mono',monospace; }
.ps { margin-top:22px; color:#475467; font-size:10pt; }
"""

_POSTCARD_CSS = """
@page { size: 11in 6in; margin: 0; }
* { box-sizing: border-box; }
body { margin:0; font-family:'Inter',Helvetica,Arial,sans-serif; color:#101828; }
.pc { width:11in; height:6in; position:relative; overflow:hidden; }
.front { background:#E6F8F7; padding:0.6in 0.7in; }
.front .wm { font-family:'Playfair Display',Georgia,serif; font-weight:700; font-size:20pt; color:#067F7B; }
.front .accent { position:absolute; right:-1.4in; top:-1.4in; width:4in; height:4in; border-radius:50%; background:rgba(115,64,196,.12); }
.front .hero { font-family:'Playfair Display',Georgia,serif; font-weight:500; font-size:30pt; line-height:1.15; color:#101828; margin-top:0.6in; max-width:8.3in; }
.front .hero .big { color:#067F7B; font-weight:700; white-space:nowrap; }
.front .sub { font-size:13pt; color:#475467; margin-top:0.28in; max-width:7.2in; }
.back { display:flex; }
.back .msg { width:6.1in; padding:0.55in 0.5in 0.5in 0.6in; }
.back .ek { font-family:'Inter'; font-weight:700; text-transform:uppercase; letter-spacing:.12em; font-size:8.5pt; color:#5B2DA8; }
.back .msg h2 { font-family:'Playfair Display',Georgia,serif; font-weight:500; font-size:18pt; color:#101828; margin:5px 0 10px; }
.back .msg p { font-size:11pt; color:#101828; margin:0 0 10px; line-height:1.45; }
.back .cta { color:#067F7B; }
.back .mono { font-family:'JetBrains Mono',monospace; }
.back .q { color:#475467; font-size:10pt; }
.back .addr { width:4.9in; border-left:1px dashed #C9D2D1; padding:1.7in 0.5in 0.5in 0.5in; font-size:11pt; color:#101828; }
.back .addr .note { font-size:7.5pt; color:#98A2B3; }
"""


def render_letter_html(*, org_name, contact_name="", title="", address1="", city="",
                       state="", zip="", monthly_fee=0, term_impact=0, annual_savings=None,
                       rn_need=0, code="", url="", rep_name="", rep_phone="", rep_email="") -> str:
    """Full-page 8.5×11 branded letter HTML (Lob renders to PDF)."""
    hero = _money(annual_savings if annual_savings is not None else (term_impact or 0) / 2)
    greet = _first(contact_name) or "Chief Nursing Officer"
    title_line = f", {title}" if title else ""
    if rn_need:
        per = (monthly_fee or 0) / rn_need
        price = f"{_money(per)} per nurse / month"
        rn_clause = f" across an estimated {rn_need:,}-RN need"
    else:
        price = f"{_money(monthly_fee)} per month"
        rn_clause = ""
    rep_line = rep_name or "Florence Partnerships"
    contact_bits = " · ".join(x for x in (rep_phone, rep_email) if x)
    rep_contact = f" · {contact_bits}" if contact_bits else ""
    link = (url or SIGNUP_BASE) + (f"?code={code}" if code and "?" not in (url or SIGNUP_BASE) else "")
    body = (
        f"<!doctype html><html><head><meta charset='utf-8'>{_FONTS}"
        f"<style>{_LETTER_CSS}</style></head><body><div class='sheet'>"
        f"<div class='wm'>Florence</div><div class='rule'></div>"
        f"<div class='recipient'>{contact_name}{title_line}<br>{org_name}<br>"
        f"{address1}<br>{city}, {state} {zip}</div>"
        f"<p class='greeting'>Dear {greet},</p>"
        f"<p>Based on {org_name}'s current nurse-staffing footprint, we estimate your "
        f"system is spending about <b>{hero} a year more than necessary</b> on "
        f"registered-nurse labor — most of it agency and travel premium.</p>"
        f"<p>Florence places <b>permanent, U.S.-licensed registered nurses</b> directly "
        f"on your payroll. No agency markup, no per-diem premium, no rotating travelers. "
        f"For {org_name} that pencils out to about <b>{price}</b>{rn_clause}.</p>"
        f"<p>I'd welcome 20 minutes to walk your team through the specific numbers for "
        f"your facilities. Are you open to a short call? I'll gladly share a couple of "
        f"windows — or, if it's easier, tell me who manages your calendar and I'll "
        f"coordinate with them directly.</p>"
        f"<div class='signoff'>{rep_line}<br><span class='muted'>Florence{rep_contact}</span></div>"
        f"<div class='callout'><span class='ek'>See your system's full pricing</span><br>"
        f"<span class='mono'>{link}</span>{(' &nbsp;·&nbsp; Code <b>' + code + '</b>') if code else ''}</div>"
        f"<p class='ps'><i>P.S. Your code pulls up the complete, system-specific "
        f"breakdown — savings by facility, cohort size, and onboarding timeline — no "
        f"call required.</i></p>"
        f"</div></body></html>"
    )
    return body


def render_postcard_html(*, org_name, contact_name="", address1="", city="", state="",
                         zip="", monthly_fee=0, term_impact=0, annual_savings=None,
                         rn_need=0, code="", url="", rep_name="", rep_phone="") -> dict:
    """6×11 postcard front + back HTML (returns {'front','back'})."""
    hero = _money(annual_savings if annual_savings is not None else (term_impact or 0) / 2)
    if rn_need:
        fee_phrase = f"About {_money((monthly_fee or 0) / rn_need)}/nurse/month."
    else:
        fee_phrase = f"About {_money(monthly_fee)}/month."
    link = (url or SIGNUP_BASE) + (f"?code={code}" if code and "?" not in (url or SIGNUP_BASE) else "")
    rep_line = " · ".join(x for x in (rep_name, rep_phone) if x) or "Florence Partnerships"
    front = (
        f"<!doctype html><html><head><meta charset='utf-8'>{_FONTS}"
        f"<style>{_POSTCARD_CSS}</style></head><body><div class='pc front'>"
        f"<div class='accent'></div><div class='wm'>Florence</div>"
        f"<div class='hero'>{org_name} could save an estimated "
        f"<span class='big'>{hero}</span> a year on RN staffing.</div>"
        f"<div class='sub'>Permanent, U.S.-licensed nurses. Direct hire — no agency markup.</div>"
        f"</div></body></html>"
    )
    back = (
        f"<!doctype html><html><head><meta charset='utf-8'>{_FONTS}"
        f"<style>{_POSTCARD_CSS}</style></head><body><div class='pc back'>"
        f"<div class='msg'><div class='ek'>Prepared for</div><h2>{org_name}</h2>"
        f"<p>{fee_phrase} Permanent RNs, placed direct — no agency markup, no travelers.</p>"
        f"<p class='cta'>See your full pricing →<br><span class='mono'><b>{link}</b></span>"
        f"{('<br>Code <b>' + code + '</b>') if code else ''}</p>"
        f"<p class='q'>Questions? {rep_line}</p></div>"
        f"<div class='addr'><div class='note'>↓ Lob places the delivery address + postage here ↓</div>"
        f"<br>{contact_name}<br>{org_name}<br>{address1}<br>{city}, {state} {zip}</div>"
        f"</div></body></html>"
    )
    return {"front": front, "back": back}


def mailpiece_html(piece_type: str = "postcard", **kw) -> dict:
    """Dispatcher → {'kind','letter'} or {'kind','front','back'}."""
    if piece_type == "letter":
        return {"kind": "letter", "letter": render_letter_html(**kw)}
    kw.pop("title", None); kw.pop("rep_email", None)  # postcard ignores these
    pc = render_postcard_html(**kw)
    return {"kind": "postcard", **pc}


def preview_html(piece_type: str = "postcard", scale: float = 0.62, **kw) -> str:
    """Self-contained HTML that renders the mailpiece scaled to fit on screen
    (for the in-app preview via st.components.v1.html)."""
    mp = mailpiece_html(piece_type, **kw)
    if mp["kind"] == "letter":
        w, h, frames = 8.5, 11.0, [("Letter", mp["letter"])]
    else:
        w, h, frames = 11.0, 6.0, [("Front", mp["front"]), ("Back", mp["back"])]
    blocks = ""
    for label, doc in frames:
        srcdoc = doc.replace('"', "&quot;")
        blocks += (
            f"<div style='margin:0 0 18px;'>"
            f"<div style='font:600 11px Inter,sans-serif;letter-spacing:.08em;"
            f"text-transform:uppercase;color:#5B2DA8;margin-bottom:6px;'>{label}</div>"
            f"<div style='width:{w*96*scale}px;height:{h*96*scale}px;border:1px solid #E4E7EC;"
            f"border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(16,24,40,.08);'>"
            f"<iframe srcdoc=\"{srcdoc}\" style='width:{w*96}px;height:{h*96}px;border:0;"
            f"transform:scale({scale});transform-origin:top left;'></iframe></div></div>"
        )
    return f"<div style='font-family:Inter,sans-serif;'>{blocks}</div>"


def _log(**row) -> None:
    _ensure()
    df = _read()
    rec = {c: "" for c in FIELDS}
    rec.update({k: ("" if v is None else str(v)) for k, v in row.items()})
    df = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)
    df.to_csv(MAIL_LOG, index=False, columns=FIELDS)


def draft_and_send(entity_type: str, entity_id: str, *, org_name: str, to_name: str,
                   address1: str, city: str, state: str, zip: str,
                   monthly_fee, term_impact, piece_type: str = "postcard",
                   rn_need: int = 0, title: str = "", rep_name: str = "",
                   rep_phone: str = "", rep_email: str = "",
                   by: str = "", live: bool = False) -> dict:
    """Draft a mailpiece (always) and send it (only if live + key + address).

    Returns a dict with `ok`, `mode` ('dry_run'|'sent'|'failed'), the retrieval
    `code`, the composed `preview`, and a human `detail`.
    """
    code = retrieval_code()
    preview = compose(org_name=org_name, contact_name=to_name, monthly_fee=monthly_fee,
                      term_impact=term_impact, code=code, piece_type=piece_type)
    now = datetime.utcnow().isoformat(timespec="seconds")
    common = dict(
        entity_type=entity_type, entity_id=str(entity_id), org_name=org_name,
        piece_type=piece_type, retrieval_code=code, to_name=to_name,
        address1=address1, city=city, state=state, zip=zip,
        monthly_fee=monthly_fee, term_impact=term_impact, drafted_at=now, by=by,
    )

    if not (str(address1).strip() and str(zip).strip()):
        return {"ok": False, "reason": "missing_address", "code": code, "preview": preview,
                "detail": "Needs a street address + ZIP (enrich via NPPES, or enter it on the contact)."}

    if not (live and is_configured()):
        _log(status="drafted", **common)
        return {"ok": True, "mode": "dry_run", "code": code, "preview": preview,
                "detail": ("Drafted (dry run). Set LOB_API_KEY and confirm a live send to mail."
                           if not is_configured() else "Drafted — confirm a live send to mail.")}

    # ── live send (human-confirmed) ──────────────────────────────────
    try:
        import requests
        endpoint = "postcards" if piece_type == "postcard" else "letters"
        pieces = mailpiece_html(
            piece_type, org_name=org_name, contact_name=to_name, title=title,
            address1=address1, city=city, state=state, zip=zip,
            monthly_fee=monthly_fee, term_impact=term_impact, rn_need=rn_need,
            code=code, url=SIGNUP_BASE, rep_name=rep_name, rep_phone=rep_phone,
            rep_email=rep_email,
        )
        data = {
            "description": f"Florence — {org_name}",
            "to[name]": to_name or org_name,
            "to[address_line1]": address1,
            "to[address_city]": city,
            "to[address_state]": state,
            "to[address_zip]": zip,
            "merge_variables[code]": code,
        }
        data.update(_from_address())
        if piece_type == "postcard":
            data.update({"front": pieces["front"], "back": pieces["back"], "size": "6x11"})
        else:
            data.update({"file": pieces["letter"], "color": "true",
                         "address_placement": "top_first_page"})
        r = requests.post(
            f"https://api.lob.com/v1/{endpoint}",
            auth=(os.environ["LOB_API_KEY"], ""),
            data=data,
            timeout=30,
        )
        ok = r.status_code in (200, 201)
        lob_id = r.json().get("id", "") if ok else ""
        _log(status=("sent" if ok else "failed"), sent_at=now, lob_id=lob_id, **common)
        return {"ok": ok, "mode": "sent" if ok else "failed", "code": code,
                "lob_id": lob_id, "preview": preview,
                "detail": None if ok else f"Lob {r.status_code}: {r.text[:200]}"}
    except Exception as e:  # network / missing requests / API error
        _log(status="failed", **common)
        return {"ok": False, "reason": str(e), "code": code, "preview": preview,
                "detail": f"Send failed: {e}"}


def record_response(entity_type: str, entity_id: str, note: str = "") -> bool:
    """Mark the latest mailpiece for an org as responded (they used the code)."""
    df = _read()
    mask = (df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))
    if not mask.any():
        return False
    idx = df[mask].index[-1]
    df.loc[idx, "status"] = "responded"
    df.loc[idx, "responded_at"] = datetime.utcnow().isoformat(timespec="seconds")
    if note:
        df.loc[idx, "notes"] = note
    df.to_csv(MAIL_LOG, index=False, columns=FIELDS)
    return True


def status_for(entity_type: str, entity_id: str) -> dict | None:
    df = _read()
    mask = (df["entity_type"] == entity_type) & (df["entity_id"].astype(str) == str(entity_id))
    if not mask.any():
        return None
    return df[mask].iloc[-1].to_dict()


def find_by_code(code: str) -> dict | None:
    """Look up the mailpiece for a retrieval code (used by the activation portal)."""
    df = _read()
    if df.empty:
        return None
    m = df[df["retrieval_code"].astype(str).str.upper() == str(code).strip().upper()]
    return m.iloc[-1].to_dict() if not m.empty else None


def summary() -> dict:
    df = _read()
    if df.empty:
        return {"total": 0, "drafted": 0, "sent": 0, "responded": 0}
    vc = df["status"].value_counts().to_dict()
    return {"total": int(len(df)), "drafted": int(vc.get("drafted", 0)),
            "sent": int(vc.get("sent", 0)), "responded": int(vc.get("responded", 0))}
