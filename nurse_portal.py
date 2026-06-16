"""
Florence Nurse Portal — login-gated career intelligence for placed nurses.

Run with:
    streamlit run nurse_portal.py --server.port 8504

Auth:
    Email-OTP via auth.py (local-friendly, swaps to SMTP in production).
    See auth.py for production swap points.

    Nurses have a parallel profile (nurse_name, state, facility, cohort,
    specialty) keyed by email and stored in data/nurse_access_codes.csv.
    First-time login auto-creates the user record; staff can pre-populate
    the profile so the portal personalizes immediately on sign-in.

Features (logged-in view):
  - Wage benchmark — "you're in [state], here's your prevailing wage vs others"
  - Mobility map — "if you moved to X, you'd earn $Y more / year"
  - Career path content — RN → Charge Nurse → CNS / NP / CRNA timelines
  - Specialty wage premiums — ICU vs Med/Surg vs OR
  - Florence community + your cohort
  - Education credit tracker
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import auth as flo_auth

DATA_DIR = Path(__file__).parent / "data"
NURSE_CODES_FILE = DATA_DIR / "nurse_access_codes.csv"

st.set_page_config(
    page_title="Florence Nurse Portal",
    page_icon="🩺",
    layout="wide",
)

# Bootstrap demo nurse profiles if missing. Profiles are keyed by email
# (matches auth.py's user table). Staff can edit this file to pre-populate
# new nurses; the portal will pick up their state / specialty on first login.
if not NURSE_CODES_FILE.exists():
    NURSE_CODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NURSE_CODES_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["email", "nurse_name", "current_state", "current_facility",
                    "cohort_year", "specialty"])
        # Demo accounts — sign in with these emails in local dev
        w.writerow(["maria@florence.dev", "Maria S.", "CA",
                    "Kaiser Foundation - Oakland", "2024", "Med/Surg"])
        w.writerow(["james@florence.dev", "James K.", "TX",
                    "Memorial Hermann - Houston", "2025", "ICU"])
        w.writerow(["priya@florence.dev", "Priya R.", "FL",
                    "Cleveland Clinic - Florida", "2024", "OR Circulating"])


def _lookup_nurse_profile(email: str) -> dict:
    """Map an authenticated email to the nurse's profile attributes."""
    try:
        df = pd.read_csv(NURSE_CODES_FILE)
    except Exception:
        return {}
    hit = df[df["email"].str.lower() == email.strip().lower()]
    if hit.empty:
        # Auth'd user with no profile — return blanks so the UI still renders
        return {
            "email": email, "nurse_name": email.split("@")[0],
            "current_state": "", "current_facility": "",
            "cohort_year": "", "specialty": "",
        }
    return hit.iloc[0].to_dict()

# ─── Florence brand styles ──────────────────────────────────────────
FLORENCE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800;900&family=Inter:wght@300;400;500;600;700&display=swap');
:root {
    --f-teal: #0ABAB5;
    --f-teal-dark: #067F7B;
    --f-navy: #101828;
    --f-gray: #FAFBFB;
    --f-border: #E4E7EC;
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
}
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
.greeting-card {
    background: linear-gradient(135deg, var(--f-teal) 0%, var(--f-teal-dark) 100%);
    color: white;
    border-radius: 14px;
    padding: 32px 36px;
    margin: 18px 0 24px 0;
}
.greeting-card h2 { color: white !important; margin: 0 0 8px 0; font-size: 2rem;}
.greeting-card .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: rgba(255,255,255,0.85);
}
.metric-card {
    background: var(--f-gray);
    border: 1px solid var(--f-border);
    border-radius: 10px;
    padding: 18px 22px;
    height: 100%;
}
.metric-card .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--f-muted);
}
.metric-card .value {
    font-family: 'Playfair Display', serif;
    font-size: 2.1rem; font-weight: 600;
    line-height: 1.0;
    color: var(--f-navy);
    margin: 6px 0;
}
.metric-card .sub {
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    color: var(--f-muted);
    line-height: 1.5;
}
.path-card {
    background: white;
    border: 1px solid var(--f-border);
    border-left: 4px solid var(--f-teal);
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 12px;
}
.path-card .stage {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--f-teal-dark);
}
.path-card h4 {
    font-size: 1.1rem; margin: 6px 0;
}
.path-card .body {
    font-family: 'Inter', sans-serif;
    font-size: 0.92rem;
    color: var(--f-muted);
    line-height: 1.55;
}
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

# State RN wage data for personalization (from internal calculator)
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
# Specialty premium (% above baseline RN wage)
SPECIALTY_PREMIUM = {
    "Med/Surg": 0.0, "ICU": 0.18, "OR Circulating": 0.22, "ER": 0.15,
    "Labor & Delivery": 0.12, "PACU": 0.14, "Telemetry": 0.06,
    "Cardiac Cath Lab": 0.20, "Oncology": 0.08, "NICU": 0.20,
}


# ─── Auth gate (email-OTP) ──────────────────────────────────────────
# Check for an existing valid session first (no form render).
_tok = st.session_state.get("florence_session_token")
auth_user = flo_auth.get_session(_tok) if _tok else None
if _tok and auth_user is None:
    st.session_state["florence_session_token"] = None

if auth_user is None:
    # Login screen — branded hero + auth form inside the centered column.
    hdr_l, hdr_r = st.columns([3, 1])
    with hdr_l:
        st.markdown(
            """
            <div class="florence-mark">
              <span class="f-box">F</span>
              <span>Florence Nurse Portal</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hdr_r:
        st.markdown(
            "<div style='text-align:right; font-family:Inter,sans-serif; font-size:0.8rem; "
            "letter-spacing:0.18em; text-transform:uppercase; color:#475467; padding-top:6px;'>"
            "FOR FLORENCE-PLACED NURSES"
            "</div>",
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='border-color:#E4E7EC; margin:14px 0 32px 0;'>", unsafe_allow_html=True)

    spacer_l, login_col, spacer_r = st.columns([1, 2, 1])
    with login_col:
        st.markdown('<div class="florence-eyebrow">Welcome</div>', unsafe_allow_html=True)
        st.markdown('<h1 style="font-size:2.6rem;">Your career, your data.</h1>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-family:Inter,sans-serif; color:#475467; line-height:1.6; '
            'font-size:1.05rem; margin-bottom:24px;">'
            "This is your personal Florence dashboard — wage benchmarking, "
            "career-path planning, and continuous market intelligence. "
            "Enter your email and we'll send you a 6-digit sign-in code."
            "</div>",
            unsafe_allow_html=True,
        )
        auth_user = flo_auth.streamlit_login(
            st, default_role="nurse", title="", blurb="",
        )
        st.caption(
            "Demo accounts (local dev): maria@florence.dev · james@florence.dev · priya@florence.dev"
        )
    if auth_user is None:
        st.stop()


# ─── Logged-in view ─────────────────────────────────────────────────
nurse = _lookup_nurse_profile(auth_user["email"])
# Carry through canonical name from the auth record if the profile is blank
if not nurse.get("nurse_name"):
    nurse["nurse_name"] = auth_user.get("name") or auth_user["email"].split("@")[0]

hdr_l, hdr_r = st.columns([3, 1])
with hdr_l:
    st.markdown(
        """
        <div class="florence-mark">
          <span class="f-box">F</span>
          <span>Florence Nurse Portal</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_r:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.markdown(
            f"<div style='text-align:right; font-family:Inter,sans-serif; "
            f"font-size:0.85rem; color:#475467; padding-top:10px;'>"
            f"Signed in as <b>{nurse['nurse_name']}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_b:
        if st.button("Sign out", type="secondary", use_container_width=True):
            flo_auth.streamlit_logout(st)
            st.rerun()

st.markdown("<hr style='border-color:#E4E7EC; margin:14px 0 8px 0;'>", unsafe_allow_html=True)


# ─── Personalized greeting / hero ───────────────────────────────────
current_state = nurse["current_state"]
specialty = nurse["specialty"]
base_wage = STATE_RN_WAGES.get(current_state, 90.0)
premium = SPECIALTY_PREMIUM.get(specialty, 0.0)
estimated_wage = base_wage * (1 + premium)
annual = estimated_wage * 2080

st.markdown(
    f"""
    <div class="greeting-card">
      <div class="label">Welcome back</div>
      <h2>Hi, {nurse['nurse_name'].split()[0]}.</h2>
      <div style="font-family:Inter,sans-serif; font-size:1.05rem; max-width:680px;
                  margin-top:14px;">
        You're a <b>{specialty}</b> RN at <b>{nurse['current_facility']}</b> in <b>{current_state}</b>,
        cohort {nurse['cohort_year']}. Based on BLS prevailing wages for your specialty in your state,
        your estimated market rate is <b>${estimated_wage:,.2f}/hour</b>
        (~<b>${annual:,.0f}/year</b>). Here's how your market is moving.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─── Section: Your wage benchmark ───────────────────────────────────
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Your wage benchmark</div>', unsafe_allow_html=True)
st.markdown(f"<h2>How {current_state} compares.</h2>", unsafe_allow_html=True)

# Compute rank
sorted_states = sorted(STATE_RN_WAGES.items(), key=lambda x: -x[1])
state_rank = next(i for i, (s, _) in enumerate(sorted_states, 1) if s == current_state)
median_wage = sorted_states[len(sorted_states)//2][1]

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.markdown(
    f"""
    <div class="metric-card">
      <div class="label">Your state rank</div>
      <div class="value">#{state_rank}</div>
      <div class="sub">of {len(STATE_RN_WAGES)} U.S. states by RN wage</div>
    </div>
    """,
    unsafe_allow_html=True,
)
mc2.markdown(
    f"""
    <div class="metric-card">
      <div class="label">{current_state} baseline</div>
      <div class="value">${base_wage:,.2f}</div>
      <div class="sub">prevailing RN hourly</div>
    </div>
    """,
    unsafe_allow_html=True,
)
mc3.markdown(
    f"""
    <div class="metric-card">
      <div class="label">{specialty} premium</div>
      <div class="value">+{premium*100:.0f}%</div>
      <div class="sub">specialty differential above baseline</div>
    </div>
    """,
    unsafe_allow_html=True,
)
mc4.markdown(
    f"""
    <div class="metric-card">
      <div class="label">National median state</div>
      <div class="value">${median_wage:,.2f}</div>
      <div class="sub">for context</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─── Section: Mobility map — where could I earn more? ───────────────
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Career mobility</div>', unsafe_allow_html=True)
st.markdown("<h2>Where could you earn more?</h2>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-family:Inter,sans-serif; color:#475467; max-width:640px; "
    f"margin-bottom:14px;'>"
    f"Your estimated wage in {current_state} is <b>${estimated_wage:,.2f}/hour</b>. "
    f"Here are the top 5 states where the same {specialty} role pays meaningfully more."
    f"</div>",
    unsafe_allow_html=True,
)

higher_states = [
    (s, w * (1 + premium))
    for s, w in sorted_states
    if w > base_wage * 1.05
]
mobility_rows = []
for s, projected in higher_states[:5]:
    annual_gain = (projected - estimated_wage) * 2080
    mobility_rows.append({
        "Target state": s,
        "Projected hourly": projected,
        "Annual gain": annual_gain,
    })
mobility_df = pd.DataFrame(mobility_rows)
if not mobility_df.empty:
    st.dataframe(
        mobility_df,
        column_config={
            "Target state": st.column_config.TextColumn(width="small"),
            "Projected hourly": st.column_config.NumberColumn(format="$%.2f"),
            "Annual gain": st.column_config.NumberColumn(format="$%.0f"),
        },
        hide_index=True, use_container_width=True,
    )
else:
    st.info(
        "You're already in a top-paying state for your specialty. "
        "The next move is typically a specialty step-up (see Career path below).",
        icon=":material/info:",
    )


# ─── Section: Specialty wage map ───────────────────────────────────
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Specialty premiums</div>', unsafe_allow_html=True)
st.markdown("<h2>RN specialty differential map.</h2>", unsafe_allow_html=True)
st.markdown(
    "<div style='font-family:Inter,sans-serif; color:#475467; max-width:640px; "
    "margin-bottom:14px;'>"
    "Each specialty carries a differential above the baseline RN wage. "
    "Differentials reflect skill premium, demand, and certification requirements."
    "</div>",
    unsafe_allow_html=True,
)
spec_df = pd.DataFrame([
    {"Specialty": s, "Premium": p, "Your state ($/hr)": base_wage * (1 + p)}
    for s, p in sorted(SPECIALTY_PREMIUM.items(), key=lambda x: -x[1])
])
st.dataframe(
    spec_df,
    column_config={
        "Specialty": st.column_config.TextColumn(),
        "Premium": st.column_config.NumberColumn(format="+%.0f%%"),
        "Your state ($/hr)": st.column_config.NumberColumn(format="$%.2f"),
    },
    hide_index=True, use_container_width=True,
)


# ─── Section: Career path ───────────────────────────────────────────
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="florence-eyebrow">Your career path</div>', unsafe_allow_html=True)
st.markdown("<h2>From RN to clinical leadership.</h2>", unsafe_allow_html=True)
st.markdown(
    "<div style='font-family:Inter,sans-serif; color:#475467; max-width:640px; "
    "margin-bottom:14px;'>"
    "Florence supports your continuing education and advancement. Typical career "
    "progressions from staff RN — each step adds credential time + earning power."
    "</div>",
    unsafe_allow_html=True,
)
paths = [
    ("0–2 years", "Staff RN / Specialty", "Build core clinical experience. Float to your specialty interest. Pursue specialty certs (CCRN, CEN, CNOR)."),
    ("2–4 years", "Charge Nurse / Preceptor", "Unit leadership, scheduling, new-hire mentoring. ~5-10% wage step. Establishes you on the leadership track."),
    ("3–5 years", "Clinical Nurse Specialist (CNS)", "Master's degree required. Hospital-system role focused on quality improvement and clinical education. ~25-40% wage step."),
    ("4–6 years", "Nurse Practitioner (NP)", "Master's or DNP required. Independent / collaborative clinical practice. ~50-100% wage step. Many specialty tracks."),
    ("5–8 years", "Certified Registered Nurse Anesthetist (CRNA)", "DNP + intensive program. Average $200K+/year. Highest-earning RN-derived role."),
    ("8+ years", "Director of Nursing / CNO", "Management track. MSN preferred. Hospital-level operational leadership. Six-figure base + bonus."),
]
for years, stage, body in paths:
    st.markdown(
        f"""
        <div class="path-card">
          <div class="stage">{years} · {stage}</div>
          <div class="body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── Footer / disclosure ───────────────────────────────────────────
st.markdown(
    """
    <div class="disclosure">
      <b>Methodology.</b> Wage data from U.S. Bureau of Labor Statistics
      Occupational Employment and Wage Statistics (OEWS), May 2024 release,
      Registered Nurses (SOC 29-1141). Specialty premium estimates derived from
      hospital compensation surveys and reflect typical national differentials;
      your facility may pay differently. Career path progressions are typical
      and informational only — your personal path depends on your goals,
      educational investments, and clinical interests. Florence does not guarantee
      future earnings or specific career outcomes.
    </div>
    """,
    unsafe_allow_html=True,
)
