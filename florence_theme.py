"""
florence_theme.py  —  drop-in Florence reskin for the Workforce Economist
=========================================================================
Reskins app.py to the "Ledger" design direction (light, editorial × terminal)
from the redesign prototype. Light mode is what Streamlit ships cleanly today;
see NOTES.md for the dark "Terminal" direction and what it costs.

USAGE (top of app.py, right after st.set_page_config):

    from florence_theme import inject_theme, kpi_strip, ticker_bar, section_head
    inject_theme(st)
    ticker_bar(st, openings=700, openings_d=12.0, quits=463, quits_d=8.7,
               ratio=1.51, avg_hr=36.2, as_of="2026-05-29")

Then replace bare st.metric rows with kpi_strip(...) and wrap section titles
with section_head(...). Everything else (sidebar, tabs, dataframe, buttons)
is restyled automatically by the injected CSS.

Fonts: GT Sectra is licensed — drop GT-Sectra-Display-Regular.woff2 +
GT-Sectra-Regular.woff2 into a /static folder you serve, and set FONT_BASE
below. Without them it falls back to Playfair Display (Google), which is close.
"""

FONT_BASE = ""   # e.g. "https://cdn.yourhost.com/fonts" (no trailing slash). Empty → Playfair fallback only.

# ---------------------------------------------------------------------------
# Brand tokens — single source of truth (mirrors colors_and_type.css)
# ---------------------------------------------------------------------------
TEAL        = "#0ABAB5"
TEAL_DEEP   = "#00A4B4"
TEAL_TEXT   = "#067F7B"   # teal that passes contrast on white for small text
TEAL_WASH   = "#E6F8F7"
PURPLE      = "#7340C4"
PURPLE_TEXT = "#5B2DA8"
PURPLE_WASH = "#F1ECFB"
INK         = "#101828"
INK_2       = "#475467"
INK_3       = "#98A2B3"
LINE        = "#E4E7EC"
LINE_STRONG = "#D0D5DD"
SURFACE     = "#FFFFFF"
SURFACE_3   = "#F7FAFA"
SURFACE_SUNK= "#F2F4F7"
POS         = "#0E8C4F"
POS_WASH    = "#E7F6EE"
WARN        = "#B45A09"


def _font_face() -> str:
    if not FONT_BASE:
        return "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');"
    return f"""
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
    @font-face {{ font-family:'GT Sectra Display'; src:url('{FONT_BASE}/GT-Sectra-Display-Regular.woff2') format('woff2'); font-weight:400 800; font-display:swap; }}
    @font-face {{ font-family:'GT Sectra'; src:url('{FONT_BASE}/GT-Sectra-Regular.woff2') format('woff2'); font-weight:400 600; font-display:swap; }}
    """


def inject_theme(st) -> None:
    """Inject the full Florence Ledger CSS. Call once, after set_page_config."""
    disp = "'GT Sectra Display','GT Sectra','Playfair Display',Georgia,serif"
    serif = "'GT Sectra','GT Sectra Display','Playfair Display',Georgia,serif"
    st.markdown(f"""<style>
{_font_face()}
:root {{
  --f-disp:{disp}; --f-serif:{serif};
  --f-sans:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  --f-mono:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,monospace;
  --teal:{TEAL}; --teal-deep:{TEAL_DEEP}; --teal-text:{TEAL_TEXT}; --teal-wash:{TEAL_WASH};
  --pur:{PURPLE}; --pur-text:{PURPLE_TEXT}; --pur-wash:{PURPLE_WASH};
  --ink:{INK}; --ink-2:{INK_2}; --ink-3:{INK_3};
  --line:{LINE}; --line-strong:{LINE_STRONG};
  --surface:{SURFACE}; --surface-3:{SURFACE_3}; --surface-sunk:{SURFACE_SUNK};
  --pos:{POS}; --pos-wash:{POS_WASH}; --warn:{WARN};
}}

/* ---- base ---- */
html, body, .stApp, [data-testid="stAppViewContainer"] {{ font-family:var(--f-sans); color:var(--ink); background:var(--surface); }}
.stApp {{ background:var(--surface); }}
[data-testid="stIconMaterial"], .material-symbols-rounded, .material-symbols-outlined {{ font-family:"Material Symbols Rounded","Material Symbols Outlined" !important; }}
.main .block-container {{ padding-top:1.1rem; max-width:1480px; }}

/* ---- editorial serif headings ---- */
h1,h2,h3,h4,
[data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3 {{
  font-family:var(--f-disp) !important; color:var(--ink); font-weight:700; letter-spacing:-.018em;
}}
h1 {{ font-size:2.5rem; line-height:1.05; }}
h2 {{ font-size:1.9rem; }}
h3 {{ font-size:1.4rem; }}
[data-testid="stCaptionContainer"], .stCaption {{ color:var(--ink-2) !important; font-family:var(--f-serif) !important; font-style:italic; font-size:.92rem; }}

/* ---- metrics → broadsheet stat blocks ---- */
[data-testid="stMetric"] {{
  background:var(--surface); border:1px solid var(--line); border-radius:13px;
  padding:15px 18px;
}}
[data-testid="stMetricLabel"] p {{ font-family:var(--f-mono) !important; font-size:.62rem !important; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3) !important; }}
[data-testid="stMetricValue"] {{ font-family:var(--f-disp) !important; color:var(--ink) !important; font-weight:700 !important; font-size:2.05rem !important; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }}
[data-testid="stMetricDelta"] {{ font-family:var(--f-mono) !important; font-size:.78rem !important; }}

/* ---- buttons ---- */
.stButton > button, .stDownloadButton > button {{
  font-family:var(--f-sans) !important; font-weight:600 !important; border-radius:9px !important;
  border:1px solid var(--line-strong) !important; transition:all .15s cubic-bezier(.2,0,0,1) !important;
}}
.stButton > button[kind="primary"] {{ background:var(--teal) !important; color:#04302E !important; border-color:var(--teal) !important; }}
.stButton > button[kind="primary"]:hover {{ background:var(--teal-deep) !important; }}
.stButton > button[kind="secondary"]:hover {{ border-color:var(--ink-3) !important; color:var(--ink) !important; }}

/* ---- sidebar = calibration console ---- */
[data-testid="stSidebar"] {{ background:var(--surface-3); border-right:1px solid var(--line); }}
[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] [role="slider"] {{ background:var(--teal) !important; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2 {{ font-size:1.15rem; }}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ font-family:var(--f-sans); font-weight:600; color:var(--ink-3); }}
.stTabs [aria-selected="true"] {{ color:var(--ink) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--teal) !important; }}

/* ---- dataframe → ledger table ---- */
[data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:13px; }}
[data-testid="stDataFrame"] [role="columnheader"] {{ font-family:var(--f-mono) !important; font-size:.6rem !important; letter-spacing:.07em; text-transform:uppercase; color:var(--ink-3) !important; background:var(--surface-3) !important; }}
[data-testid="stDataFrame"] [role="gridcell"] {{ font-family:var(--f-mono) !important; font-variant-numeric:tabular-nums; }}

/* ---- reusable Florence component classes (used by helpers below) ---- */
.fl-ticker {{ display:flex; align-items:center; gap:0; border:1px solid var(--line); border-radius:12px; overflow:hidden; margin:2px 0 18px; background:var(--surface); }}
.fl-ticker .tk {{ display:flex; align-items:baseline; gap:7px; padding:11px 16px; border-left:1px solid var(--line); }}
.fl-ticker .tk:first-child {{ border-left:0; }}
.fl-ticker .lab {{ font-family:var(--f-mono); font-size:.62rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); }}
.fl-ticker .val {{ font-family:var(--f-mono); font-size:.86rem; font-weight:600; color:var(--ink); }}
.fl-ticker .up {{ color:var(--teal-text); font-family:var(--f-mono); font-size:.74rem; font-weight:600; }}
.fl-ticker .dn {{ color:#DC2626; font-family:var(--f-mono); font-size:.74rem; font-weight:600; }}
.fl-ticker .live {{ margin-left:auto; display:inline-flex; align-items:center; gap:6px; padding:0 16px; font-family:var(--f-mono); font-size:.62rem; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-2); }}
.fl-ticker .dot {{ width:7px; height:7px; border-radius:50%; background:var(--pos); box-shadow:0 0 0 0 rgba(14,140,79,.5); animation:flp 2.4s infinite; }}
@keyframes flp {{ 0%{{box-shadow:0 0 0 0 rgba(14,140,79,.5);}} 70%{{box-shadow:0 0 0 7px rgba(14,140,79,0);}} 100%{{box-shadow:0 0 0 0 rgba(14,140,79,0);}} }}

.fl-kpis {{ display:grid; grid-template-columns:repeat(5,1fr); border:1px solid var(--line); border-radius:13px; overflow:hidden; margin-bottom:20px; }}
.fl-kpis .kpi {{ padding:15px 18px 16px; border-left:1px solid var(--line); }}
.fl-kpis .kpi:first-child {{ border-left:0; }}
.fl-kpis .lab {{ font-family:var(--f-mono); font-size:.62rem; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3); }}
.fl-kpis .val {{ font-family:var(--f-disp); font-weight:700; font-size:2.05rem; letter-spacing:-.02em; color:var(--ink); line-height:1.05; margin-top:7px; font-variant-numeric:tabular-nums; }}
.fl-kpis .val small {{ font-family:var(--f-mono); font-size:.8rem; font-weight:500; color:var(--ink-3); }}
.fl-kpis .val.teal {{ color:var(--teal-text); }}
.fl-kpis .val.pur {{ color:var(--pur-text); }}
.fl-kpis .foot {{ font-size:.72rem; color:var(--ink-2); margin-top:5px; }}
.fl-kpis .foot b {{ color:var(--ink); }}

.fl-eyebrow {{ font-family:var(--f-mono); font-size:.68rem; font-weight:600; letter-spacing:.16em; text-transform:uppercase; color:var(--teal-text); }}
.fl-eyebrow.pur {{ color:var(--pur-text); }}
.fl-sectitle {{ font-family:var(--f-disp); font-weight:700; font-size:1.6rem; letter-spacing:-.018em; color:var(--ink); margin:3px 0 2px; }}
.fl-subhead {{ font-family:var(--f-serif); font-style:italic; font-size:.92rem; color:var(--ink-2); }}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Component helpers — emit the same HTML the prototype uses
# ---------------------------------------------------------------------------
def ticker_bar(st, *, openings, openings_d, quits, quits_d, ratio, avg_hr, as_of):
    def arrow(d): return f'<span class="{"up" if d>=0 else "dn"}">{"▲" if d>=0 else "▼"}{abs(d)}%</span>'
    st.markdown(f"""<div class="fl-ticker">
      <div class="tk"><span class="lab">HC openings</span><span class="val">{openings:,}K</span>{arrow(openings_d)}</div>
      <div class="tk"><span class="lab">Quits</span><span class="val">{quits:,}K</span>{arrow(quits_d)}</div>
      <div class="tk"><span class="lab">Open:Quit</span><span class="val">{ratio:.2f}×</span></div>
      <div class="tk"><span class="lab">Avg $/hr</span><span class="val">${avg_hr:.1f}</span></div>
      <div class="live"><span class="dot"></span>Live · {as_of}</div>
    </div>""", unsafe_allow_html=True)


def section_head(st, eyebrow, title, subhead="", purple=False):
    st.markdown(f"""<div style="margin:8px 0 14px">
      <div class="fl-eyebrow {'pur' if purple else ''}">{eyebrow}</div>
      <div class="fl-sectitle">{title}</div>
      {f'<div class="fl-subhead">{subhead}</div>' if subhead else ''}
    </div>""", unsafe_allow_html=True)


def kpi_strip(st, items):
    """items: list of dicts {lab, val, sub('small'), foot, tone('teal'|'pur'|'')}"""
    cells = ""
    for it in items:
        tone = it.get("tone", "")
        small = f"<small> {it['sub']}</small>" if it.get("sub") else ""
        foot = f'<div class="foot">{it["foot"]}</div>' if it.get("foot") else ""
        cells += f'<div class="kpi"><div class="lab">{it["lab"]}</div><div class="val {tone}">{it["val"]}{small}</div>{foot}</div>'
    st.markdown(f'<div class="fl-kpis">{cells}</div>', unsafe_allow_html=True)
