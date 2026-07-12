"""
Florence Market Intelligence — public-facing market education + lead capture.

A public, SEO-friendly page that educates operators (and the curious public)
on the state of the U.S. RN labor market. No FICA / IRS / F-1 language —
this is pure market education with branded narrative leading to the calculator.

Run with:
    streamlit run public_market_intel.py --server.port 8503

Funnel:
  Land → educate → "Calculate my savings" CTA → /calculator
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
CALCULATOR_URL = os.environ.get("CALCULATOR_URL", "http://localhost:8502")

# Same schema the calculator's log_lead writes (it schema-migrates on drift).
_LEAD_FIELDS = [
    "timestamp", "email", "state", "facility_type", "n_rns",
    "florence_fee_per_rn_month", "fica_savings_per_rn_month",
    "net_cost_per_rn_month", "annual_revenue_uplift", "term_savings_total",
    "source", "utm_source", "utm_medium", "utm_campaign", "invoice_file",
]


def _log_report_lead(email: str) -> None:
    path = DATA_DIR / "customer_leads.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    try:
        qp = st.query_params
        utm = [(qp.get("utm_source") or "")[:64], (qp.get("utm_medium") or "")[:64],
               (qp.get("utm_campaign") or "")[:64]]
    except Exception:
        utm = ["", "", ""]
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(_LEAD_FIELDS)
        w.writerow([datetime.utcnow().isoformat(timespec="seconds"), email,
                    "", "", "", "", "", "", "", "", "intel_report", *utm, ""])

st.set_page_config(
    page_title="Florence Market Intelligence",
    page_icon="🩺",
    layout="wide",
)

# ─── Florence brand ──────────────────────────────────────────────────
FLORENCE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800;900&family=Inter:wght@300;400;500;600;700&display=swap');
:root {
    --f-teal: #0ABAB5;
    --f-teal-dark: #067F7B;
    --f-navy: #101828;
    --f-gray: #F4F6F8;
    --f-border: #E5E8EE;
    --f-muted: #475467;
}
html, body, .stApp { font-family: 'Inter', -apple-system, sans-serif; }
[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
}
h1, h2, h3, h4 {
    font-family: 'Playfair Display', Georgia, serif !important;
    color: var(--f-navy);
    font-weight: 600;
    letter-spacing: -0.015em;
}
h1 { font-size: 3rem; line-height: 1.08; }
h2 { font-size: 2rem; }
h3 { font-size: 1.4rem; }

.florence-mark {
    display: flex; align-items: center; gap: 10px;
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.4rem; font-weight: 600; color: var(--f-navy);
}
.florence-mark .f-box {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; background: var(--f-teal);
    border-radius: 7px; color: white; font-weight: 700;
    font-family: 'Inter', sans-serif; font-size: 1.05rem;
}
.florence-eyebrow {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--f-teal-dark);
    margin: 6px 0 10px 0;
}
.florence-headline {
    font-family: 'Playfair Display', serif;
    font-size: 3rem; font-weight: 600;
    line-height: 1.08; letter-spacing: -0.02em;
    color: var(--f-navy);
    margin: 8px 0 14px 0;
}
.florence-subhead {
    font-family: 'Inter', sans-serif;
    font-size: 1.05rem; line-height: 1.55;
    color: var(--f-muted);
    margin: 0 0 22px 0;
    max-width: 720px;
}
.callout-card {
    background: var(--f-gray);
    border: 1px solid var(--f-border);
    border-radius: 12px;
    padding: 28px 32px;
    margin: 14px 0;
}
.callout-card.dark {
    background: var(--f-navy);
    color: white;
}
.callout-card.dark h3 { color: white !important; }
.callout-card.dark p { color: rgba(255,255,255,0.85); }
.callout-card .number {
    font-family: 'Playfair Display', serif;
    font-size: 3.2rem; font-weight: 600;
    line-height: 1.0;
    color: var(--f-teal-dark);
    margin: 4px 0 8px 0;
}
.callout-card.dark .number { color: var(--f-teal); }
.callout-card .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--f-muted);
}
.callout-card.dark .label { color: rgba(255,255,255,0.7); }
.cta-button {
    display: inline-block;
    background: var(--f-teal);
    color: white !important;
    text-decoration: none !important;
    font-weight: 600;
    padding: 14px 30px;
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    margin: 6px;
    font-size: 1.05rem;
}
.cta-button:hover { background: var(--f-teal-dark); }
.disclosure {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: var(--f-muted);
    line-height: 1.55;
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid var(--f-border);
}
#MainMenu, footer { visibility: hidden; }
</style>
"""
st.markdown(FLORENCE_CSS, unsafe_allow_html=True)


# ─── Header brand strip ──────────────────────────────────────────────
hdr_l, hdr_r = st.columns([3, 2])
with hdr_l:
    st.markdown(
        """
        <div class="florence-mark">
          <span class="f-box">F</span>
          <span>Florence Market Intelligence</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_r:
    st.markdown(
        f"<div style='text-align:right; font-family:Inter,sans-serif; "
        f"font-size:0.8rem; letter-spacing:0.18em; text-transform:uppercase; "
        f"color:#475467; padding-top:6px;'>"
        f"PUBLIC EDITION · UPDATED {date.today().strftime('%B %Y')}"
        f"</div>",
        unsafe_allow_html=True,
    )
st.markdown("<hr style='border-color:#E5E8EE; margin:14px 0 24px 0;'>", unsafe_allow_html=True)


# ─── Hero ────────────────────────────────────────────────────────────
hero_l, hero_r = st.columns([5, 4])
with hero_l:
    st.markdown('<div class="florence-eyebrow">U.S. RN Labor Market</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="florence-headline">'
        'The state of the U.S.<br>nursing workforce.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="florence-subhead">'
        "Open data, updated monthly. We track every signal that shapes how healthcare "
        "operators hire, retain, and pay their RNs — from job openings to state-level "
        "prevailing wages — so you can plan with confidence."
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<a class="cta-button" href="http://localhost:8502" target="_blank">'
        'See what permanent RNs cost your business →</a>',
        unsafe_allow_html=True,
    )

with hero_r:
    st.markdown(
        """
        <div class="callout-card dark">
          <div class="label">As of today</div>
          <div class="number">1.51</div>
          <div style='font-family:Inter,sans-serif; font-size:0.92rem;
                      color:rgba(255,255,255,0.85);'>
            Healthcare job openings per quit — a ratio above 1.3 indicates a
            tight labor market with operator competition for staff.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── Section 1: Live JOLTS chart ────────────────────────────────────
st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Labor Market Pulse</div>', unsafe_allow_html=True)
st.markdown("<h2>Healthcare hiring intensity.</h2>", unsafe_allow_html=True)
st.markdown(
    '<div class="florence-subhead">'
    "The Bureau of Labor Statistics JOLTS series tracks healthcare job "
    "openings, hires, and worker quits each month. Sustained periods where "
    "openings exceed hires push wages and agency costs upward."
    '</div>',
    unsafe_allow_html=True,
)

# Load JOLTS history
try:
    jolts = pd.read_csv(DATA_DIR / "surveillance" / "jolts_healthcare" / "long_history.csv")
    jolts["period_num"] = jolts["period"].str.replace("M", "").astype(int)
    jolts["yearmonth"] = jolts["year"].astype(str) + "-" + jolts["period_num"].astype(str).str.zfill(2)
    label_map = {"job_openings_level": "Job openings", "hires_level": "Hires",
                 "quits_level": "Quits", "layoffs_level": "Layoffs"}
    jolts["metric_label"] = jolts["metric"].map(label_map)
    jolts_plot = jolts.dropna(subset=["value"]).sort_values(["metric_label", "year", "period_num"])
    jolts_plot = jolts_plot[jolts_plot["metric_label"].notna()].tail(96)

    from viz.charts import time_series
    fig = time_series(
        jolts_plot, x_col="yearmonth", y_col="value", color_col="metric_label",
        title="Healthcare sector: openings, hires, quits (thousands)",
        y_label="Thousands of workers", height=420,
    )
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Chart load: {e}")

st.caption(
    "Source: U.S. Bureau of Labor Statistics, Job Openings and Labor Turnover Survey "
    "(JOLTS), Healthcare and Social Assistance sector (NAICS 62). "
    "Florence Market Intelligence refreshes monthly."
)


# ─── Section 2: State wage choropleth ───────────────────────────────
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Geographic Wage Map</div>', unsafe_allow_html=True)
st.markdown("<h2>Prevailing RN wages by state.</h2>", unsafe_allow_html=True)
st.markdown(
    '<div class="florence-subhead">'
    "RN compensation varies more than 3× across U.S. states — driven by cost "
    "of living, union density, and state-level nurse-staffing regulations. "
    "Hover any state to see its current wage."
    '</div>',
    unsafe_allow_html=True,
)

try:
    state_bench = pd.read_csv(DATA_DIR / "state_benchmarks.csv")
    state_bench = state_bench[~state_bench["state"].isin(["GU","PR","VI","MP","AS"])]
    from viz.charts import state_choropleth
    state_dict = dict(zip(state_bench["state"], state_bench["rn_wage"]))
    fig = state_choropleth(
        state_dict,
        title="Prevailing RN hourly wage by state (BLS OEWS, May 2025)",
        colorbar_title="$/hr", value_format="$,.2f", height=480,
    )
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Map: {e}")


# ─── Section 3: Educational explainer ───────────────────────────────
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Why the RN shortage persists</div>', unsafe_allow_html=True)
st.markdown("<h2>The math of the U.S. nursing gap.</h2>", unsafe_allow_html=True)

ex_l, ex_m, ex_r = st.columns(3)
with ex_l:
    st.markdown(
        """
        <div class="callout-card">
          <div class="label">Demand side</div>
          <h3>Aging population</h3>
          <p style='font-family:Inter,sans-serif; color:#475467; line-height:1.55;'>
            By 2030, all baby boomers will be over 65. Medicare enrollment is
            growing 3% annually. Care complexity rises with age — driving
            demand for RNs at every site of care from acute hospitals to home health.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with ex_m:
    st.markdown(
        """
        <div class="callout-card">
          <div class="label">Supply side</div>
          <h3>Domestic pipeline constraints</h3>
          <p style='font-family:Inter,sans-serif; color:#475467; line-height:1.55;'>
            U.S. nursing schools turn away ~80,000 qualified applicants
            annually due to faculty shortages and clinical placement caps.
            ~200,000 RNs reach retirement age each year. The math doesn't close.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with ex_r:
    st.markdown(
        """
        <div class="callout-card">
          <div class="label">Cost side</div>
          <h3>Agency labor premium</h3>
          <p style='font-family:Inter,sans-serif; color:#475467; line-height:1.55;'>
            Operators paying $85-150/hour for contract RNs versus $40-60/hour
            for staff RNs. The premium funds turnover, recruitment, training,
            and margin — and recurs every cycle. Hospitals spent $24B on agency
            labor in 2023.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── Section 4: Florence's value prop ───────────────────────────────
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">The Florence solution</div>', unsafe_allow_html=True)
st.markdown("<h2>Permanent international RN supply.</h2>", unsafe_allow_html=True)

flow_cols = st.columns(4)
steps = [
    ("01", "Florence produces qualified international RNs", "Exam preparation · higher education · bedside practice"),
    ("02", "We place them as permanent employees", "Standard hiring · benefits · 3-year minimum tenure"),
    ("03", "Customer pays a flat $50K per RN", "Payable on successful employment start"),
    ("04", "Capacity unlocks incremental revenue", "$200K-$400K per RN per year by setting"),
]
for col, (num, title, body) in zip(flow_cols, steps):
    col.markdown(
        f"""
        <div style='background:#F4F6F8; border:1px solid #E5E8EE;
                    border-radius:12px; padding:24px 22px; height:280px;'>
          <div style='font-family:Playfair Display,serif; font-size:1.8rem;
                      color:#0ABAB5; margin-bottom:8px;'>{num}</div>
          <h3 style='font-size:1.15rem; margin-bottom:10px;'>{title}</h3>
          <p style='font-family:Inter,sans-serif; font-size:0.92rem;
                    color:#475467; line-height:1.55;'>{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── Lead magnet: the annual industry report ─────────────────────────
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Free report</div>', unsafe_allow_html=True)
st.markdown(f"<h2>The State of the U.S. Nursing Workforce — {date.today().year}.</h2>",
            unsafe_allow_html=True)
st.markdown(
    '<p style="font-family:Inter,sans-serif; color:#475467; max-width:680px;">'
    "Market structure, openings-to-quits dynamics, wage geography, and where "
    "permanent international RN supply fits — assembled from the same BLS and "
    "CMS data that powers this page. Enter your email and the report is yours."
    "</p>",
    unsafe_allow_html=True,
)
with st.form("report_form", clear_on_submit=False):
    rpt_email = st.text_input("Work email", placeholder="you@company.com",
                              key="rpt_email")
    rpt_submit = st.form_submit_button("Get the report →", type="primary")
if rpt_submit:
    if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
                    rpt_email or ""):
        st.error("Please enter a valid work email address.")
    else:
        _log_report_lead(rpt_email)
        try:
            import industry_report as _ir
            st.session_state["intel_report_md"] = _ir.build_markdown()
        except Exception:
            st.session_state["intel_report_md"] = None
        if st.session_state.get("intel_report_md"):
            st.success("Here's your report — the download button below is live.")
        else:
            st.success(f"Thanks — we'll email the report to **{rpt_email}** "
                       "within one business day.")
if st.session_state.get("intel_report_md"):
    st.download_button(
        ":material/download: Download the report (Markdown)",
        st.session_state["intel_report_md"].encode("utf-8"),
        file_name=f"florence_state_of_nursing_workforce_{date.today().year}.md",
        mime="text/markdown",
        type="primary",
    )

# ─── Closing CTA ────────────────────────────────────────────────────
st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="callout-card dark" style='text-align:center;'>
      <div class="label">Ready to do the math?</div>
      <h2 style='color:white;'>See what permanent international RNs<br>
      would do for your business.</h2>
      <p style='max-width:580px; margin:14px auto 22px; font-size:1.05rem;'>
        Our calculator runs your state's prevailing wage against your facility
        type and shows the incremental revenue every additional RN unlocks.
      </p>
      <a class="cta-button" href="{CALCULATOR_URL}" target="_blank">
        Open the calculator →
      </a>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─── Methodology / sources ──────────────────────────────────────────
st.markdown(
    """
    <div class="disclosure">
      <b>Data sources.</b> JOLTS healthcare data: U.S. Bureau of Labor Statistics,
      Job Openings and Labor Turnover Survey, Healthcare and Social Assistance
      sector (NAICS 62), monthly publication. State RN wages: BLS Occupational
      Employment and Wage Statistics (OEWS), May 2025 release, Registered Nurses
      (SOC 29-1141). Florence Market Intelligence refreshes monthly with public
      BLS releases. This page is illustrative and educational; engage your own
      legal, tax, and operations counsel before contracting any workforce program.
    </div>
    """,
    unsafe_allow_html=True,
)
