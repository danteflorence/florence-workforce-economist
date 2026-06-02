"""
Compliance guard: customer-facing composers never emit prohibited terms.

Standing rule — no FICA / IRS / visa / tax / immigration / F-1 / green-card
language on any customer surface (mailpiece, email, call script). Word-boundary
matching so legitimate words like "verification" (contains 'fica') don't trip it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BAD = [r"\bfica\b", r"\birs\b", r"\bvisa\b", r"\bvisas\b", r"\bimmigration\b",
       r"\btax\b", r"\btaxes\b", r"\bf-1\b", r"\bgreen card\b"]


def _scan(text: str, label: str) -> None:
    low = text.lower()
    hits = [p.strip("\\b") for p in BAD if re.search(p, low)]
    assert not hits, f"{label}: prohibited term(s) {hits}"


def test_outreach_email_clean():
    import outreach_email as oe
    e = oe.compose_email(system_name="Banner Health", annual_savings=18.4e6,
                         term_impact=36.8e6, rn_need=420, monthly_fee=2.94e6,
                         contact_name="Dana Reyes", code="FLOR-7QK4M",
                         activation_url="https://app.florence.health/activate")
    _scan(e["subject"] + " " + " ".join(e["subjects"]) + " " + e["body"] + " " + oe.as_txt(e),
          "outreach_email")


def test_mailpiece_clean():
    import lob_mailer as L
    ltr = L.render_letter_html(org_name="Sutter Health", contact_name="Dana Reyes",
                               title="Chief Nursing Officer", monthly_fee=2.94e6,
                               term_impact=36.8e6, rn_need=420, code="FLOR-7QK4M")
    pc = L.render_postcard_html(org_name="Sutter Health", monthly_fee=2.94e6,
                                term_impact=36.8e6, rn_need=420, code="FLOR-7QK4M")
    _scan(ltr + " " + pc["front"] + " " + pc["back"], "mailpiece")


def test_call_script_clean():
    import call_script as C
    s = C.build_script(system_name="Banner Health", annual_savings=18.4e6, term_impact=36.8e6,
                       rn_need=420, monthly_fee=2.94e6, contact_name="Dana Reyes")
    blob = s["opening"] + " " + " ".join(s["beats"]) + " " + s["ask"] + " " + \
        " ".join(q + " " + a for q, a in s["objections"]) + " " + C.as_text(s)
    _scan(blob, "call_script")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((n, f) for n, f in globals().items()
                           if n.startswith("test_") and callable(f)):
        try:
            fn(); print(f"PASS  {name}")
        except Exception as e:
            failed += 1; print(f"FAIL  {name}: {e}")
    print(f"\n{'COMPLIANCE CLEAN' if not failed else 'COMPLIANCE FAILED'}")
    sys.exit(1 if failed else 0)
