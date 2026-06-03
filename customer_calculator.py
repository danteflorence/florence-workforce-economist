"""
Florence Workforce Calculator — customer-facing self-serve.

Public Streamlit app at florence.com/calculator (or run locally on port 8502).

Funnel:
  1. Landing: Florence brand + headline + lead capture
  2. Calculator: state + facility type + nurse count
  3. Free instant result: estimated savings + ROI
  4. Email gate: enter email → unlock PDF report + Stripe checkout
  5. Stripe Payment Links:
     - "$99/mo Florence Workforce Intelligence" subscription
     - "Start Florence RN placement ($50K per RN)"

Different from the internal pricing tool — this is the lead-gen + customer-discovery
page. Optimized for credit-card-friendly home health, hospice, ASC, SNF buyers.

Run with:
    streamlit run customer_calculator.py --server.port 8502
"""
from __future__ import annotations

import csv
import os
import re
from datetime import datetime, date
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
LEADS_LOG = DATA_DIR / "customer_leads.csv"

st.set_page_config(
    page_title="Florence Workforce Calculator",
    page_icon="🩺",
    layout="wide",
)

# ─── Florence brand styles (copied from main app for consistency) ────
FLORENCE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --f-teal: #0BC5A0;
    --f-teal-dark: #089478;
    --f-navy: #0F1B2D;
    --f-gray: #F4F6F8;
    --f-border: #E5E8EE;
    --f-ink: #0F1B2D;
    --f-muted: #5B6675;
}
html, body, .stApp { font-family: 'Inter', -apple-system, sans-serif; }
[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
}
h1, h2, h3, h4 {
    font-family: 'Newsreader', Georgia, serif !important;
    color: var(--f-navy);
    font-weight: 600;
    letter-spacing: -0.015em;
}
h1 { font-size: 3.2rem; line-height: 1.05; }
h2 { font-size: 2.2rem; line-height: 1.15; }
h3 { font-size: 1.5rem; }

.florence-mark {
    display: flex; align-items: center; gap: 10px;
    font-family: 'Newsreader', Georgia, serif;
    font-size: 1.4rem; font-weight: 600; color: var(--f-navy);
}
.florence-mark .f-box {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; background: var(--f-teal);
    border-radius: 7px; color: white; font-weight: 700;
    font-family: 'Inter', sans-serif; font-size: 1.05rem;
}
.florence-headline {
    font-family: 'Newsreader', serif;
    font-size: 3.2rem; font-weight: 600;
    line-height: 1.05; letter-spacing: -0.02em;
    color: var(--f-navy);
    margin: 8px 0 18px 0;
}
.florence-subhead {
    font-family: 'Inter', sans-serif;
    font-size: 1.15rem; font-weight: 400;
    color: var(--f-muted); line-height: 1.55;
    margin: 0 0 24px 0;
    max-width: 720px;
}
.florence-eyebrow {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--f-teal-dark);
    margin: 6px 0 10px 0;
}
.result-card {
    background: linear-gradient(135deg, var(--f-teal) 0%, var(--f-teal-dark) 100%);
    color: white;
    border-radius: 14px;
    padding: 36px 40px;
    margin: 18px 0;
}
.result-card .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: rgba(255,255,255,0.85);
}
.result-card .number {
    font-family: 'Newsreader', serif;
    font-size: 4.5rem; font-weight: 600;
    line-height: 1.0;
    color: white;
    margin: 8px 0;
}
.result-card .sub {
    font-family: 'Inter', sans-serif;
    font-size: 1rem; color: rgba(255,255,255,0.92);
    line-height: 1.5; max-width: 580px;
}
.detail-card {
    background: var(--f-gray);
    border: 1px solid var(--f-border);
    border-radius: 12px;
    padding: 24px 28px;
    margin: 14px 0;
}
.detail-card .row {
    display: flex; justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid var(--f-border);
}
.detail-card .row:last-child { border-bottom: none; }
.detail-card .row-label {
    color: var(--f-muted); font-size: 0.95rem;
}
.detail-card .row-value {
    color: var(--f-navy); font-weight: 600;
    font-family: 'Newsreader', serif;
}
.stripe-cta {
    background: var(--f-navy);
    color: white;
    border-radius: 12px;
    padding: 28px 32px;
    margin: 18px 0;
    text-align: center;
}
.stripe-cta h3 { color: white !important; margin-bottom: 8px; }
.stripe-cta p {
    color: rgba(255,255,255,0.85);
    font-size: 0.95rem; line-height: 1.5;
    max-width: 540px; margin: 10px auto 18px;
}
.cta-button {
    display: inline-block;
    background: var(--f-teal);
    color: white !important;
    text-decoration: none !important;
    font-weight: 600;
    padding: 12px 24px;
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    margin: 6px;
}
.cta-button:hover { background: var(--f-teal-dark); }
.cta-button.secondary {
    background: transparent;
    border: 1.5px solid var(--f-teal);
    color: var(--f-teal) !important;
}
.cta-button.secondary:hover { background: rgba(11,197,160,0.1); }
.disclosure {
    font-family: 'Inter', sans-serif;
    font-size: 0.8rem;
    color: var(--f-muted);
    line-height: 1.5;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--f-border);
}
.stButton > button {
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
}
.stButton > button[kind="primary"] {
    background: var(--f-teal) !important;
    border: none !important;
    padding: 12px 24px !important;
}
#MainMenu, footer { visibility: hidden; }
</style>
"""
st.markdown(FLORENCE_CSS, unsafe_allow_html=True)


# ─── Constants & assumptions ────────────────────────────────────────
EMPLOYER_FICA_RATE = 0.0765
HOURS_PER_MONTH = 156
TERM_MONTHS_DEFAULT = 36
FLAT_FEE_DEFAULT = 50_000

# Per-state RN annual mean wage (BLS OEWS May 2024) — for the calculator base
STATE_RN_WAGES = {
    "AK": 113.69, "AL": 75.41, "AR": 76.65, "AZ": 92.79, "CA": 137.69,
    "CO": 91.69, "CT": 105.21, "DC": 116.10, "DE": 92.42, "FL": 84.27,
    "GA": 87.13, "HI": 116.42, "IA": 78.99, "ID": 88.06, "IL": 92.93,
    "IN": 81.86, "KS": 79.12, "KY": 81.18, "LA": 81.21, "MA": 109.81,
    "MD": 95.10, "ME": 86.97, "MI": 89.92, "MN": 99.92, "MO": 80.18,
    "MS": 74.83, "MT": 87.05, "NC": 84.69, "ND": 80.49, "NE": 81.46,
    "NH": 88.40, "NJ": 102.83, "NM": 90.61, "NV": 105.66, "NY": 110.41,
    "OH": 84.45, "OK": 80.55, "OR": 117.31, "PA": 89.69, "RI": 95.91,
    "SC": 83.92, "SD": 73.55, "TN": 81.53, "TX": 88.06, "UT": 84.34,
    "VA": 86.96, "VT": 84.99, "WA": 107.65, "WI": 87.71, "WV": 75.42,
    "WY": 84.43,
}
# RN wage is annual mean / 2080 hrs. Convert to hourly.
STATE_RN_WAGES_HOURLY = {k: v for k, v in STATE_RN_WAGES.items()}

# Setting-specific revenue per RN per year (matches non_hospital_pricing constants)
REVENUE_PER_RN_ANNUAL = {
    "Home Health Agency (HHA)": 300_000,
    "Hospice": 250_000,
    "Skilled Nursing Facility (SNF)": 200_000,
    "Ambulatory Surgery Center (ASC)": 400_000,
    "Hospital": 350_000,
    "Dialysis Center": 280_000,
}

FACILITY_TYPES = list(REVENUE_PER_RN_ANNUAL.keys())

# Stripe Payment Links — set via env/secrets. Payment Link URLs are public (not
# secret), so env is just for config hygiene. Empty → the CTA renders a
# "contact us" mailto instead of a dead link.
STRIPE_SUBSCRIPTION_URL = os.environ.get("STRIPE_SUBSCRIPTION_URL", "")
STRIPE_PLACEMENT_URL = os.environ.get("STRIPE_PLACEMENT_URL", "")
FLORENCE_CONTACT_EMAIL = os.environ.get("FLORENCE_CONTACT_EMAIL", "partnerships@florenceeducation.com")


# ─── Helpers ────────────────────────────────────────────────────────
def log_lead(email: str, state: str, facility_type: str, n_rns: int, results: dict) -> None:
    """Append the lead's data to data/customer_leads.csv."""
    LEADS_LOG.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LEADS_LOG.exists()
    with open(LEADS_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow([
                "timestamp", "email", "state", "facility_type", "n_rns",
                "florence_fee_per_rn_month", "fica_savings_per_rn_month",
                "net_cost_per_rn_month", "annual_revenue_uplift",
                "term_savings_total",
            ])
        writer.writerow([
            datetime.utcnow().isoformat(timespec="seconds"),
            email, state, facility_type, n_rns,
            f"{results.get('florence_fee_per_rn_month', 0):.0f}",
            f"{results.get('fica_savings_per_rn_month', 0):.0f}",
            f"{results.get('net_cost_per_rn_month', 0):.0f}",
            f"{results.get('annual_revenue_uplift', 0):.0f}",
            f"{results.get('term_savings_total', 0):.0f}",
        ])


def compute_economics(state: str, facility_type: str, n_rns: int) -> dict:
    """Run the FICA + capacity-revenue math for the customer."""
    wage = STATE_RN_WAGES_HOURLY.get(state, 90.0)
    monthly_wage = wage * HOURS_PER_MONTH
    fica_savings = monthly_wage * EMPLOYER_FICA_RATE
    # Flat $50K / 36mo
    florence_fee = FLAT_FEE_DEFAULT / TERM_MONTHS_DEFAULT
    net_cost_per_rn_month = florence_fee - fica_savings
    rev_per_rn_year = REVENUE_PER_RN_ANNUAL.get(facility_type, 250_000)
    rev_per_rn_month = rev_per_rn_year / 12
    annual_revenue_uplift = rev_per_rn_year * n_rns
    # Net cost can be NEGATIVE in high-wage states (FICA exceeds Florence fee):
    # the employer effectively pays nothing net. Use the raw (possibly negative)
    # net cost so we can communicate that correctly.
    annual_net_cost_raw = net_cost_per_rn_month * 12 * n_rns
    # Annual Florence gross fee — what they pay before FICA savings
    annual_florence_gross = florence_fee * 12 * n_rns
    annual_net_benefit = annual_revenue_uplift - annual_net_cost_raw
    term_savings_total = annual_net_benefit * (TERM_MONTHS_DEFAULT / 12)
    # ROI: revenue uplift vs Florence gross fee (clean, never blows up)
    roi_vs_gross = annual_revenue_uplift / max(annual_florence_gross, 1)
    return {
        "wage": wage,
        "monthly_wage": monthly_wage,
        "florence_fee_per_rn_month": florence_fee,
        "fica_savings_per_rn_month": fica_savings,
        "net_cost_per_rn_month": net_cost_per_rn_month,
        "rev_per_rn_month": rev_per_rn_month,
        "rev_per_rn_year": rev_per_rn_year,
        "annual_revenue_uplift": annual_revenue_uplift,
        "annual_florence_gross": annual_florence_gross,
        "annual_net_cost": annual_net_cost_raw,
        "annual_net_benefit": annual_net_benefit,
        "term_savings_total": term_savings_total,
        "roi_multiple": roi_vs_gross,
        "fica_covers_fee": fica_savings >= florence_fee,
    }


def fmt_big(v: float) -> str:
    if v >= 1e9: return f"${v/1e9:,.2f}B"
    if v >= 1e6: return f"${v/1e6:,.2f}M"
    if v >= 1e3: return f"${v/1e3:,.2f}K"
    return f"${v:,.2f}"


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email))


# ─── Header brand strip ──────────────────────────────────────────────
hdr_l, hdr_r = st.columns([3, 1])
with hdr_l:
    st.markdown(
        """
        <div class="florence-mark">
          <span class="f-box">F</span>
          <span>Florence Workforce Calculator</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        "<div style='text-align:right; font-family:Inter,sans-serif; font-size:0.8rem; "
        "letter-spacing:0.18em; text-transform:uppercase; color:#5B6675; padding-top:6px;'>"
        "FOR HOMECARE, HOSPICE, SNF, ASC, HOSPITAL OPERATORS"
        "</div>",
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#E5E8EE; margin:14px 0 24px 0;'>", unsafe_allow_html=True)


# ─── Hero ────────────────────────────────────────────────────────────
hero_l, hero_r = st.columns([5, 4])
with hero_l:
    st.markdown('<div class="florence-eyebrow">RN Capacity, Solved</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="florence-headline">'
        'See how much revenue<br>permanent international RNs<br>unlock for your business.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="florence-subhead">'
        "Florence places permanent international RNs into U.S. healthcare operators. "
        "Your business expands capacity, takes on the patients you can't serve today, "
        "and captures the revenue your current labor pool can't reach — all at a flat "
        "$50K placement fee per RN."
        '</div>',
        unsafe_allow_html=True,
    )
with hero_r:
    st.markdown(
        """
        <div style='background:#F4F6F8; border:1px solid #E5E8EE; border-radius:12px;
                    padding:22px 26px; margin-top:6px;'>
          <div style='font-family:Inter,sans-serif; font-size:0.76rem; font-weight:600;
                      letter-spacing:0.22em; text-transform:uppercase; color:#5B6675;
                      margin-bottom:10px;'>What you get</div>
          <ul style='font-family:Inter,sans-serif; font-size:0.95rem; color:#0F1B2D;
                     line-height:1.7; padding-left:20px; margin:0;'>
            <li>An RN your team owns, not a contingent worker</li>
            <li>Three-year minimum tenure built into the program</li>
            <li>Replacement protection for early attrition</li>
            <li>Standard hiring and benefits — your terms</li>
            <li>Onboarding into your existing payroll &amp; HR systems</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── Calculator ──────────────────────────────────────────────────────
st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Your numbers</div>', unsafe_allow_html=True)
st.markdown("<h2>Run your savings analysis.</h2>", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
with c1:
    state = st.selectbox(
        "State",
        sorted(STATE_RN_WAGES_HOURLY.keys()),
        index=sorted(STATE_RN_WAGES_HOURLY.keys()).index("CA"),
    )
with c2:
    facility_type = st.selectbox("Facility type", FACILITY_TYPES, index=0)
with c3:
    n_rns = st.number_input(
        "RNs you need to hire",
        min_value=1, max_value=500, value=10, step=1,
    )

st.caption(
    f"Using prevailing RN wage for **{state}**: "
    f"**${STATE_RN_WAGES_HOURLY[state]:,.2f}/hour** "
    f"(BLS Occupational Employment & Wage Statistics, May 2024)."
)

# ─── Compute + display ──────────────────────────────────────────────
result = compute_economics(state, facility_type, n_rns)

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
florence_fee = result["florence_fee_per_rn_month"]
rev_per_rn_month = result["rev_per_rn_month"]
net_benefit_per_rn_month = rev_per_rn_month - florence_fee
annual_florence_gross = florence_fee * 12 * n_rns
roi_revenue_to_fee = (
    result["annual_revenue_uplift"] / max(annual_florence_gross, 1)
)

sub_text = (
    f"{n_rns} permanent RN{'s' if n_rns != 1 else ''} × "
    f"${result['rev_per_rn_year']:,.0f} incremental revenue per RN per year. "
    f"Net of Florence's flat ${50_000:,.0f}/RN placement fee, your business retains "
    f"<b>{fmt_big(result['annual_revenue_uplift'] - annual_florence_gross)}/year</b> "
    f"in incremental contribution — a <b>{roi_revenue_to_fee:.0f}× revenue : fee</b> ratio."
)

st.markdown(
    f"""
    <div class="result-card">
      <div class="label">Annual revenue you can unlock</div>
      <div class="number">{fmt_big(result["annual_revenue_uplift"])}</div>
      <div class="sub">{sub_text}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Detail breakdown card (FICA-free)
st.markdown(
    f"""
    <div class="detail-card">
      <div style='font-family:Inter,sans-serif; font-size:0.76rem; font-weight:600;
                  letter-spacing:0.22em; text-transform:uppercase; color:#5B6675; margin-bottom:14px;'>
        Per-RN economics
      </div>
      <div class="row">
        <div class="row-label">Florence placement fee (flat $50K ÷ 36 months)</div>
        <div class="row-value">${florence_fee:,.0f}/mo</div>
      </div>
      <div class="row">
        <div class="row-label">Incremental revenue per RN per month ({facility_type})</div>
        <div class="row-value">${rev_per_rn_month:,.0f}/mo</div>
      </div>
      <div class="row">
        <div class="row-label"><b>Net benefit per RN per month</b></div>
        <div class="row-value" style='color:#089478;'>
          <b>${net_benefit_per_rn_month:,.0f}/mo</b>
        </div>
      </div>
      <div class="row">
        <div class="row-label">Total Florence investment ({n_rns} RNs over 36 mo)</div>
        <div class="row-value">${50_000 * n_rns:,.0f}</div>
      </div>
      <div class="row">
        <div class="row-label">Total revenue unlocked over the same 36 months</div>
        <div class="row-value">{fmt_big(result['annual_revenue_uplift'] * 3)}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─── Email gate → full report + Stripe CTAs ──────────────────────────
st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Get the full breakdown</div>', unsafe_allow_html=True)
st.markdown("<h2>Take this analysis with you.</h2>", unsafe_allow_html=True)
st.markdown(
    '<div style="font-family:Inter,sans-serif; color:#5B6675; max-width:680px;">'
    "Enter your email to unlock the printable PDF report with your full per-RN economics, "
    "Florence implementation timeline, and methodology. "
    "We use your email only to send your report and follow up — never sold or shared."
    "</div>",
    unsafe_allow_html=True,
)

with st.form("lead_form", clear_on_submit=False):
    email = st.text_input("Work email", placeholder="you@company.com")
    consent = st.checkbox(
        "I'd like Florence to follow up with my customized savings analysis.",
        value=True,
    )
    submitted = st.form_submit_button(
        "Unlock full report  →", type="primary", use_container_width=False,
    )

if submitted:
    if not valid_email(email):
        st.error("Please enter a valid work email address.")
    elif not consent:
        st.warning("Please tick the consent box to receive your analysis.")
    else:
        log_lead(email, state, facility_type, n_rns, result)
        # Generate the PDF inline for immediate download
        try:
            from customer_pdf_report import build_report
            pdf_buf = build_report(email, state, facility_type, n_rns, result)
            st.session_state["lead_pdf"] = pdf_buf.getvalue()
        except Exception as e:
            st.session_state["lead_pdf"] = None
            st.warning(f"PDF generation hit an issue: {e}. Florence will email it manually.")
        st.success(
            f"Thanks — your analysis has been logged to Florence's queue. "
            f"Download your full PDF report below, or expect a follow-up at **{email}** "
            "within 1 business day. Next steps continue further below."
        )
        if st.session_state.get("lead_pdf"):
            st.download_button(
                ":material/download: Download your Florence savings report (PDF)",
                st.session_state["lead_pdf"],
                file_name=f"florence_savings_analysis_{state}_{facility_type.split()[0]}.pdf",
                mime="application/pdf",
                type="primary",
            )

        # ─── Stripe CTAs (unlocked after email) ───
        st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
        _sub_cta = (
            f'<a href="{STRIPE_SUBSCRIPTION_URL}" target="_blank" class="cta-button">Subscribe now →</a>'
            if STRIPE_SUBSCRIPTION_URL
            else f'<a href="mailto:{FLORENCE_CONTACT_EMAIL}" class="cta-button">Contact us to start →</a>'
        )
        _place_cta = (
            f'<a href="{STRIPE_PLACEMENT_URL}" target="_blank" class="cta-button">Begin placement →</a>'
            if STRIPE_PLACEMENT_URL
            else f'<a href="mailto:{FLORENCE_CONTACT_EMAIL}" class="cta-button">Talk to our team →</a>'
        )
        cta_l, cta_r = st.columns(2)
        with cta_l:
            st.markdown(
                f"""
                <div class="stripe-cta">
                  <h3>Florence Workforce Intelligence</h3>
                  <p>
                    Monthly subscription to ongoing labor-market analysis and
                    pricing updates for your business. Cancel anytime.
                  </p>
                  <div style='font-family:Newsreader,serif; font-size:2.2rem;
                              color:#0BC5A0; margin:8px 0;'>$99<span style='font-size:1.1rem;
                              color:rgba(255,255,255,0.85);'>/month</span></div>
                  {_sub_cta}
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cta_r:
            st.markdown(
                f"""
                <div class="stripe-cta">
                  <h3>Start your first Florence placement</h3>
                  <p>
                    Reserve your first RN cohort. Payment due on
                    successful employment start — replacement protection
                    for early attrition included.
                  </p>
                  <div style='font-family:Newsreader,serif; font-size:2.2rem;
                              color:#0BC5A0; margin:8px 0;'>$50K<span style='font-size:1.1rem;
                              color:rgba(255,255,255,0.85);'>/RN</span></div>
                  {_place_cta}
                </div>
                """,
                unsafe_allow_html=True,
            )

# ─── Methodology disclosure ──────────────────────────────────────────
st.markdown(
    """
    <div class="disclosure">
      <b>Methodology.</b> Wage data from the U.S. Bureau of Labor Statistics
      Occupational Employment and Wage Statistics (OEWS, May 2024), Registered
      Nurses (SOC 29-1141), state-level annual mean ÷ 2,080 hours.
      Florence placement fee: flat $50,000 per RN amortized over a 36-month
      placement term. Incremental revenue per RN per year is a setting-specific
      estimate based on industry benchmarks ($300K Home Health Agency, $250K
      Hospice, $200K Skilled Nursing Facility, $400K Ambulatory Surgery Center,
      $350K Hospital, $280K Dialysis Center). Actual revenue uplift depends on
      your case mix, payor mix, and operational scale.
      <br><br>
      <b>Disclosure.</b> This calculator is illustrative and based on inputs you
      provide. Actual results vary by facility, regulatory environment, and
      Florence onboarding capacity. Florence is not a financial, tax, or legal
      advisor. Engage your own counsel before contracting.
    </div>
    """,
    unsafe_allow_html=True,
)
