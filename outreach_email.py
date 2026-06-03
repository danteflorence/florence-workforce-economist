"""
Per-system outreach email composer.

When a rep downloads a system's proposal package, the bundle ships with a
*ready-to-send* email pre-filled with that system's real numbers — hero annual
savings, 24-month impact, cohort size, and the per-nurse monthly fee — plus a
meeting ask that EITHER offers availability OR offers to coordinate with whoever
owns the recipient's calendar. The rep fills [First name] / their own sign-off
and sends from their own inbox (deliverability + reply threading stay with them).

The same composer feeds the docs popup (copyable text + a mailto: link) and,
later, the optional Gmail-draft path (crm_sync.py).

Compliance: value + meeting ask only. No FICA / IRS / visa / tax / immigration
language ever (standing rule) — identical posture to the mailpiece.
"""
from __future__ import annotations

import os
import urllib.parse

# Optional self-scheduling link (Calendly / Google Appointment / etc). The rep
# or admin sets it; absent → the email just offers to send an invite.
CALENDAR_URL = os.environ.get("FLORENCE_CALENDAR_URL", "")


def _money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:,.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.2f}K"
    return f"${v:,.2f}"


def _dollars(v) -> str:
    """Exact dollars to the cent — for per-nurse / per-month figures."""
    return f"${float(v or 0):,.2f}"


def _first_name(contact_name: str) -> str:
    parts = (contact_name or "").strip().split()
    return parts[0] if parts else ""


def compose_email(
    *,
    system_name: str,
    annual_savings,
    term_impact,
    rn_need,
    monthly_fee,
    per_nurse_fee=None,
    code: str = "",
    activation_url: str = "",
    contact_name: str = "",
    rep_name: str = "",
    rep_phone: str = "",
    rep_email: str = "",
    availability: str = "",
    opener: str = "",
) -> dict:
    """Compose the outreach email for one health system.

    Returns {subjects: [3], subject, body, mailto}. All numbers are pre-filled;
    only [First name] (when no contact) and the rep sign-off are placeholders.
    """
    try:
        rn = int(rn_need or 0)
    except (TypeError, ValueError):
        rn = 0
    if per_nurse_fee is None:
        try:
            per_nurse_fee = float(monthly_fee or 0) / rn if rn else float(monthly_fee or 0)
        except (TypeError, ValueError):
            per_nurse_fee = 0.0

    hero = _money(annual_savings)
    subjects = [
        f"{system_name} — about {hero}/yr in nurse-staffing savings",
        f"Permanent RNs for {system_name}",
        f"A quick idea on {system_name}'s nurse-staffing spend",
    ]

    greet = _first_name(contact_name) or "[First name]"

    # Link / breakdown line — only show a live link when we have an access code
    # that the activation portal can resolve; otherwise offer to share it.
    if code and activation_url:
        link_line = (
            "I put together a breakdown specific to your facilities — savings by "
            "site, cohort size, and onboarding timeline. You can pull it up here:\n\n"
            f"  {activation_url}  (access code {code})\n\n"
        )
    else:
        link_line = (
            "I put together a breakdown specific to your facilities — savings by "
            "site, cohort size, and onboarding timeline. Happy to send it over or "
            "walk you through it live.\n\n"
        )

    avail = availability.strip() or "I have a couple of windows open next week"
    book_line = f"\n\nPrefer to self-schedule? {CALENDAR_URL}" if CALENDAR_URL else ""

    rn_phrase = f"an estimated {rn:,}-RN need" if rn else "your projected RN need"
    sign_phone = f" · {rep_phone}" if rep_phone else ""
    sign_email = f" · {rep_email}" if rep_email else ""

    lead = opener.strip() or (
        f"I lead health-system partnerships at Florence. Looking at {system_name}'s "
        f"nurse-staffing footprint, we estimate roughly {hero} a year in avoidable RN "
        f"labor cost — most of it agency and travel premium."
    )
    body = (
        f"Hi {greet},\n\n"
        f"{lead}\n\n"
        f"Florence places permanent, U.S.-licensed registered nurses directly on your "
        f"payroll — no agency markup, no rotating travelers. For {system_name} that's "
        f"about {_dollars(per_nurse_fee)} per nurse / month across {rn_phrase}, and about "
        f"{_money(term_impact)} of impact over the first 24 months.\n\n"
        f"{link_line}"
        f"Worth 20 minutes to walk your team through it? {avail} — happy to send an "
        f"invite. Or, if someone manages your calendar, just point me to them and I'll "
        f"coordinate directly.{book_line}\n\n"
        f"Best,\n"
        f"{rep_name or '[Your name]'}\n"
        f"Florence{sign_phone}{sign_email}"
    )

    mailto = "mailto:?" + urllib.parse.urlencode(
        {"subject": subjects[0], "body": body}, quote_via=urllib.parse.quote
    )
    return {"subjects": subjects, "subject": subjects[0], "body": body, "mailto": mailto}


def compose_sequence(*, system_name: str, annual_savings, term_impact, rn_need,
                     monthly_fee, per_nurse_fee=None, code: str = "", activation_url: str = "",
                     contact_name: str = "", rep_name: str = "", rep_phone: str = "",
                     rep_email: str = "", availability: str = "", opener: str = "") -> list[dict]:
    """The full outreach cadence: intro → follow-up → share-availability → breakup.
    Each step is {step, label, subject, body, mailto}, all numbers pre-filled.
    `opener` (optional) personalizes the intro's lead line."""
    intro = compose_email(
        system_name=system_name, annual_savings=annual_savings, term_impact=term_impact,
        rn_need=rn_need, monthly_fee=monthly_fee, per_nurse_fee=per_nurse_fee, code=code,
        activation_url=activation_url, contact_name=contact_name, rep_name=rep_name,
        rep_phone=rep_phone, rep_email=rep_email, availability=availability, opener=opener)
    hero = _money(annual_savings)
    greet = _first_name(contact_name) or "[First name]"
    sign = (f"{rep_name or '[Your name]'}\nFlorence"
            + (f" · {rep_phone}" if rep_phone else "") + (f" · {rep_email}" if rep_email else ""))
    avail = (availability or "I have a couple of windows next week").strip()

    later = [
        {"step": 2, "label": "Follow-up 1",
         "subject": f"Re: {system_name} — about {hero}/yr in nurse-staffing savings",
         "body": (f"Hi {greet},\n\nCircling back on my note about roughly {hero} a year in avoidable "
                  f"RN labor cost at {system_name}. Did it reach the right person?\n\nHappy to send the "
                  f"facility-by-facility breakdown, or take 15 minutes whenever it's convenient.\n\n"
                  f"Best,\n{sign}")},
        {"step": 3, "label": "Follow-up 2 · share availability",
         "subject": f"20 minutes on {system_name}'s RN staffing?",
         "body": (f"Hi {greet},\n\nStill think there's about {hero} a year on the table for {system_name} "
                  f"by moving agency coverage to permanent, U.S.-licensed RNs.\n\n{avail} for a quick "
                  f"20 minutes — I'll send an invite. Or point me to whoever manages your calendar and "
                  f"I'll coordinate directly.\n\nBest,\n{sign}")},
        {"step": 4, "label": "Breakup",
         "subject": f"Closing the loop — {system_name}",
         "body": (f"Hi {greet},\n\nI'll stop here so I'm not cluttering your inbox. If RN agency spend "
                  f"comes up down the road, the ~{hero}/yr estimate and the facility breakdown for "
                  f"{system_name} are ready whenever you want them.\n\nThanks for the time,\n{sign}")},
    ]
    out = [{"step": 1, "label": "Intro", "subject": intro["subject"],
            "body": intro["body"], "mailto": intro["mailto"]}]
    for s in later:
        s["mailto"] = "mailto:?" + urllib.parse.urlencode(
            {"subject": s["subject"], "body": s["body"]}, quote_via=urllib.parse.quote)
        out.append(s)
    return out


def sequence_as_txt(steps: list[dict]) -> str:
    """Render the whole cadence as a single text file for the ZIP bundle."""
    parts = ["FLORENCE — OUTREACH SEQUENCE", "=" * 28, ""]
    for s in steps:
        parts += [f"--- STEP {s['step']}: {s['label']} ---", f"Subject: {s['subject']}", "",
                  s["body"], "", ""]
    parts.append("— Numbers pre-filled. Replace [First name] / your sign-off, then send from your inbox.")
    return "\n".join(parts)


def as_txt(email: dict) -> str:
    """Render the composed email as a plain-text file for the ZIP bundle."""
    lines = ["SUBJECT OPTIONS", "==============="]
    for i, s in enumerate(email.get("subjects", []), 1):
        lines.append(f"  {i}. {s}")
    lines += ["", "BODY", "====", "", email.get("body", "")]
    lines += [
        "",
        "",
        "— Pre-filled with this system's figures. Replace [First name] and your "
        "sign-off, then send from your own inbox.",
    ]
    return "\n".join(lines)
