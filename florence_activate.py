"""
Florence — customer activation portal (scaffold).

The flow the direct-mail engine sets up: a customer receives a postcard with a
retrieval code → enters it here → sees their quote → signs up → (pays via
Stripe — placeholder) → reviews candidates available to hire.

SCAFFOLD ONLY:
  - No card handling. Payment is a placeholder Stripe link you wire via the
    STRIPE_CHECKOUT_URL env var (configure Stripe yourself).
  - The candidate roster is an illustrative preview; wire it to the live cohort
    pipeline when ready.
  - Activating with a valid code marks that org's mailpiece "responded" — the
    loop the AI SDR tracks.

Run:  streamlit run florence_activate.py --server.port 8503
Deploy this as its own (customer-facing) app, separate from the internal tool.
"""
import csv
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from florence_theme import inject_theme, section_head
import lob_mailer

DATA_DIR = Path(__file__).parent / "data"
ACTIVATIONS = DATA_DIR / "activations.csv"
STRIPE_URL = os.environ.get("STRIPE_CHECKOUT_URL", "")

st.set_page_config(page_title="Florence — Activate", page_icon="🩺", layout="centered")
inject_theme(st)


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.0f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return f"${v:,.0f}"


# Illustrative roster — replace with the live cohort pipeline.
SAMPLE_CANDIDATES = [
    {"id": "RN-2041", "specialty": "Med-Surg / Telemetry", "years": 6, "status": "NCLEX-passed · ready"},
    {"id": "RN-1888", "specialty": "Critical Care (ICU)", "years": 9, "status": "NCLEX-passed · ready"},
    {"id": "RN-2107", "specialty": "Emergency", "years": 4, "status": "In final review"},
    {"id": "RN-1952", "specialty": "Labor & Delivery", "years": 7, "status": "NCLEX-passed · ready"},
    {"id": "RN-2210", "specialty": "Peri-operative / OR", "years": 5, "status": "NCLEX-passed · ready"},
    {"id": "RN-2066", "specialty": "Dialysis", "years": 8, "status": "Credentialing"},
]


def _log_signup(code: str, org: str, name: str, email: str) -> None:
    is_new = not ACTIVATIONS.exists()
    ACTIVATIONS.parent.mkdir(parents=True, exist_ok=True)
    with open(ACTIVATIONS, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["code", "org", "name", "email", "signed_up_at"])
        w.writerow([code, org, name, email, datetime.utcnow().isoformat(timespec="seconds")])


def main() -> None:
    section_head(st, "Florence Capital", "Activate your nursing pipeline",
                 "Permanent, internationally educated RNs — the same shifts, a lower number.",
                 purple=True)

    try:
        prefill = st.query_params.get("code", "")
    except Exception:
        prefill = ""
    code = st.text_input("Retrieval code", value=prefill or "",
                         placeholder="FLOR-XXXXX").strip().upper()

    if not code:
        st.info("Enter the code from your Florence mailer to see your quote and the "
                "candidates available to hire.")
        return

    rec = lob_mailer.find_by_code(code)
    if not rec:
        st.warning("We couldn't match that code. Double-check it, or contact your "
                   "Florence representative.")
        return

    org = rec.get("org_name") or "your organization"
    st.markdown(f"### Welcome, {org}")
    c1, c2 = st.columns(2)
    c1.metric("Florence monthly", _money(rec.get("monthly_fee")))
    c2.metric("24-month impact", _money(rec.get("term_impact")))

    if not st.session_state.get("activated"):
        with st.form("activate"):
            name = st.text_input("Your name")
            email = st.text_input("Work email")
            agree = st.checkbox("I'm authorized to evaluate staffing for this organization.")
            submitted = st.form_submit_button("Continue →", type="primary")
        if submitted:
            if name and email and agree:
                _log_signup(code, org, name, email)
                lob_mailer.record_response(
                    rec.get("entity_type", "system"), rec.get("entity_id", ""),
                    note=f"activated by {email}")
                st.session_state["activated"] = True
                st.rerun()
            else:
                st.error("Please add your name, work email, and confirm authorization.")
        return

    # ── Activated ────────────────────────────────────────────────────
    st.success("You're in. Add a payment method to start hiring.")
    if STRIPE_URL:
        st.link_button("Add payment method · secure checkout →", STRIPE_URL,
                       type="primary")
    else:
        st.caption("Secure checkout (Stripe) appears here once STRIPE_CHECKOUT_URL is configured. "
                   "No card details are handled by this app.")

    section_head(st, "Available now", "Candidates ready to hire", purple=False)
    for i in range(0, len(SAMPLE_CANDIDATES), 2):
        cols = st.columns(2)
        for col, cand in zip(cols, SAMPLE_CANDIDATES[i:i + 2]):
            with col:
                st.markdown(
                    f"<div style='border:1px solid var(--line,#E4E7EC);border-radius:13px;"
                    f"padding:14px 16px;margin-bottom:8px;'>"
                    f"<div style='font-family:var(--f-mono,monospace);font-size:.7rem;"
                    f"letter-spacing:.08em;color:#98A2B3;'>{cand['id']}</div>"
                    f"<div style='font-weight:600;color:#101828;margin-top:2px;'>{cand['specialty']}</div>"
                    f"<div style='font-size:.85rem;color:#475467;'>{cand['years']} yrs · {cand['status']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
    st.caption("Illustrative roster — live candidate availability connects to the Florence "
               "cohort pipeline.")


main()
