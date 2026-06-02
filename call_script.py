"""
Per-system call script + objection battlecard.

The phone is the channel with real coverage today — CMS gives us a phone and
(often) a named contact for the universe, but almost no emails. So a rep can
dial straight from the system popup with the hero number, pricing, an opening
line, and objection handlers in front of them.

Compliance: value + meeting ask only. No FICA / IRS / visa / tax / immigration
language — "permanent, U.S.-licensed RNs", direct-hire, savings vs. agency.
"""
from __future__ import annotations


def _money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return f"${v:,.0f}"


def _first(name: str) -> str:
    parts = (name or "").strip().split()
    return parts[0] if parts else ""


# Built-in objection battlecard — compliance-clean, Florence-specific.
OBJECTIONS = [
    ("We already use agencies / an MSP.",
     "That's exactly the spend we replace. Agencies bill a premium for temporary "
     "coverage; we place permanent, U.S.-licensed RNs on your payroll — no markup, "
     "no 13-week churn — at a fraction of the agency rate."),
    ("We're under a hiring freeze.",
     "This isn't incremental headcount budget — it's a lower-cost substitute for the "
     "agency and travel dollars you're already spending. Most systems fund it straight "
     "from the contract-labor line."),
    ("Onboarding and credentialing sound heavy.",
     "We handle sourcing, screening, and license verification; your team receives "
     "pre-vetted, U.S.-licensed RNs ready to orient on your normal schedule."),
    ("How do we know they'll stay?",
     "Permanent placement is the whole point — these are direct hires committed to "
     "your system, not travelers rotating out. Retention is structurally better than "
     "agency coverage."),
    ("I need to involve other stakeholders.",
     "Happy to — would a 20-minute overview for your CNO and CFO work? Or point me to "
     "whoever owns their calendar and I'll coordinate directly."),
]


def build_script(*, system_name: str, annual_savings, term_impact, rn_need,
                 monthly_fee, contact_name: str = "", contact_phone: str = "",
                 rep_name: str = "") -> dict:
    """Assemble a structured call script + numbers for one system."""
    try:
        rn = int(rn_need or 0)
    except (TypeError, ValueError):
        rn = 0
    per_nurse = (float(monthly_fee or 0) / rn) if rn else float(monthly_fee or 0)
    hero, per, term = _money(annual_savings), _money(per_nurse), _money(term_impact)
    greet = _first(contact_name) or "there"
    rn_phrase = f"an estimated {rn:,} RNs" if rn else "your projected RN need"

    opening = (
        f"Hi {greet}, this is {rep_name or '[your name]'} with Florence — I'll keep it "
        f"to 30 seconds. Looking at {system_name}'s nurse-staffing footprint, we estimate "
        f"about {hero} a year in avoidable RN labor cost, most of it agency and travel "
        f"premium. We place permanent, U.S.-licensed RNs directly on your payroll — about "
        f"{per} per nurse a month, no agency markup. Worth 20 minutes to walk your team "
        f"through the specific numbers?"
    )
    beats = [
        "Mechanism — permanent, U.S.-licensed RNs, direct-hire. Replaces agency/travel "
        "premium, not incremental headcount.",
        f"Pricing — about {per} per nurse / month across {rn_phrase}; roughly {term} of "
        "impact over the first 24 months.",
        "Proof — the pricing is built from your own facilities' cost data; I can send the "
        "system-specific breakdown today.",
    ]
    # No per-facility figure on hand (e.g. an outpatient cold call) — drop the
    # dollar claims and lead with the value prop + an offer to price it.
    if not (float(annual_savings or 0) or float(monthly_fee or 0)):
        opening = (
            f"Hi {greet}, this is {rep_name or '[your name]'} with Florence — I'll keep it to "
            f"30 seconds. We place permanent, U.S.-licensed RNs directly on your payroll — direct "
            f"hire, no agency markup, no rotating travelers. Worth 20 minutes to see what that "
            f"could look like for {system_name}?"
        )
        beats = [
            "Mechanism — permanent, U.S.-licensed RNs, direct-hire; replaces agency/travel premium.",
            "We'll build a cost estimate specific to your facility before the call.",
            "No agency markup and no 13-week churn — nurses who stay.",
        ]
    ask = (
        "The ask — 20 minutes with whoever owns nurse staffing (CNO or CFO). I'll send a "
        "couple of windows, or coordinate with whoever runs their calendar."
    )
    return {
        "system": system_name,
        "phone": contact_phone,
        "numbers": {"hero_annual": hero, "per_nurse_mo": per, "term_24mo": term, "rn_need": rn},
        "opening": opening,
        "beats": beats,
        "objections": OBJECTIONS,
        "ask": ask,
    }


def as_text(script: dict) -> str:
    n = script["numbers"]
    lines = [
        "FLORENCE — CALL SCRIPT",
        "=" * 22,
        f"{script['system']}" + (f"   ·   Call: {script['phone']}" if script.get("phone") else ""),
        f"Hero {n['hero_annual']}/yr  ·  ~{n['per_nurse_mo']}/nurse/mo  ·  "
        f"{n['term_24mo']} over 24 mo  ·  {n['rn_need']:,} RNs",
        "",
        "OPENING", "-------", script["opening"], "",
        "KEY BEATS", "---------",
    ]
    lines += [f"  • {b}" for b in script["beats"]]
    lines += ["", "OBJECTIONS", "----------"]
    for q, a in script["objections"]:
        lines += [f"  Q: {q}", f"  A: {a}", ""]
    lines += ["THE ASK", "-------", script["ask"]]
    return "\n".join(lines)
