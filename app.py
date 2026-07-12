"""
Florence Workforce Economist — internal pricing tool.

Run with:
    streamlit run app.py

National dynamic pricing engine. For every Medicare-registered U.S. hospital,
runs the market-sensitive pricing engine, surfaces the financial picture for
all parties (hospital, partner channel, Florence net), and lets you generate a
proposal for any hospital or health system.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from pricing_batch import (
    calibration_sweep,
    load_universe,
    market_aggregate,
    price_batch,
    row_to_profile,
)
from pricing_engine import (
    Calibration,
    Channel,
    CohortMix,
    PricingMode,
    REQUIRED_COMPLIANCE_SENTENCE,
    price,
    render_evidence_pack,
)
from excel_writer import write_hospital_workbook, write_system_workbook
from exec_summary import build_hospital_exec_summary, build_system_exec_summary
from customer_deck import build_deck_from_system_recs
import system_overrides as sysov
import io
import tempfile
import zipfile

from florence_theme import inject_theme, kpi_strip, section_head  # editorial design system
from error_monitoring import init_monitoring

init_monitoring("economist")

DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(
    page_title="Florence Workforce Economist",
    page_icon="🩺",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Florence brand design system — matches the customer-facing deck language
# ---------------------------------------------------------------------------
FLORENCE_TEAL = "#0ABAB5"          # editorial brand teal (corrects legacy #0ABAB5)
FLORENCE_TEAL_DARK = "#067F7B"     # teal that passes contrast on white
FLORENCE_NAVY = "#101828"
FLORENCE_NAVY_SOFT = "#1D2939"
FLORENCE_GRAY = "#FAFBFB"
FLORENCE_GRAY_BORDER = "#E4E7EC"
FLORENCE_INK = "#101828"
FLORENCE_INK_MUTED = "#475467"

FLORENCE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800;900&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --f-teal: #0ABAB5;
    --f-teal-dark: #067F7B;
    --f-indigo: #7340C4;        /* Florence Capital — royal purple (financing/docs) */
    --f-indigo-dark: #5B2DA8;
    --f-navy: #101828;
    --f-navy-soft: #1D2939;
    --f-gray: #FAFBFB;
    --f-border: #E4E7EC;
    --f-ink: #101828;
    --f-muted: #475467;
}

/* Base typography — Inter for body. Apply only to root elements;
   inheritance handles the rest. NEVER apply to bare span or Material icons break. */
html, body, .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
/* Material icon spans use Streamlit's Material Symbols Rounded font.
   We must force this explicitly because html-level Inter inherits down. */
[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
}

/* Editorial serif for ALL headings (h1-h4) — matches the deck */
h1, h2, h3, h4,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 {
    font-family: 'Playfair Display', 'Source Serif Pro', Georgia, serif !important;
    color: var(--f-navy);
    font-weight: 600;
    letter-spacing: -0.015em;
}
h1 { font-size: 2.6rem; line-height: 1.1; }
h2 { font-size: 2.0rem; line-height: 1.15; }
h3 { font-size: 1.45rem; line-height: 1.2; }

/* Tightened captions in muted gray */
[data-testid="stCaptionContainer"], .stCaption {
    color: var(--f-muted) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.875rem;
}

/* === Brand header strip === */
.florence-brand-strip {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 0 16px 0;
    border-bottom: 1px solid var(--f-border);
    margin-bottom: 22px;
}
.florence-mark {
    display: flex; align-items: center; gap: 10px;
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.25rem; font-weight: 600; color: var(--f-navy);
}
.florence-mark .f-box {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; background: var(--f-teal);
    border-radius: 6px; color: white; font-weight: 700;
    font-family: 'Inter', sans-serif; font-size: 1rem;
}
.florence-section-tag {
    font-family: 'Inter', sans-serif;
    font-size: 0.75rem; font-weight: 600;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--f-muted);
}

/* === All-caps tracked section labels (deck-style "01 · THE OPPORTUNITY") === */
.florence-eyebrow {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--f-teal-dark);
    margin: 6px 0 10px 0;
}

/* === Deck-style comparison cards (TODAY vs WITH FLORENCE) === */
.florence-card {
    border-radius: 12px;
    padding: 28px 30px;
    height: 100%;
    box-sizing: border-box;
}
.florence-card.today {
    background: var(--f-gray);
    border: 1px solid var(--f-border);
}
.florence-card.with-florence {
    background: var(--f-teal);
    color: white;
}
.florence-card .card-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--f-muted);
    margin-bottom: 14px;
}
.florence-card.with-florence .card-label { color: rgba(255,255,255,0.85); }
.florence-card .card-number {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 3.6rem; font-weight: 600;
    line-height: 1;
    color: var(--f-navy);
    margin: 4px 0 6px 0;
}
.florence-card.with-florence .card-number { color: white; }
.florence-card .card-unit {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.4rem; font-weight: 400;
    color: var(--f-muted);
}
.florence-card.with-florence .card-unit { color: rgba(255,255,255,0.9); }
.florence-card .card-headline {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.25rem; font-weight: 600;
    color: var(--f-navy);
    margin: 18px 0 6px 0;
}
.florence-card.with-florence .card-headline { color: white; }
.florence-card .card-body {
    font-family: 'Inter', sans-serif;
    font-size: 0.92rem; line-height: 1.5;
    color: var(--f-muted);
}
.florence-card.with-florence .card-body { color: rgba(255,255,255,0.92); }

/* === Navy footer banner (closing pitch sentence, deck-style) === */
.florence-banner {
    background: var(--f-navy);
    color: white;
    padding: 22px 32px;
    border-radius: 12px;
    margin-top: 18px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 28px;
}
.florence-banner .banner-text {
    font-family: 'Inter', sans-serif;
    font-size: 0.98rem; font-weight: 500;
    line-height: 1.5;
}
.florence-banner .banner-value {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 2.4rem; font-weight: 600;
    color: var(--f-teal);
    white-space: nowrap;
}
.florence-banner .banner-suffix {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: rgba(255,255,255,0.7);
    margin-left: 10px;
}

/* === Headline + subhead pair (editorial-style serif) === */
.florence-headline {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 2.6rem; font-weight: 600;
    line-height: 1.08; letter-spacing: -0.018em;
    color: var(--f-navy);
    margin: 4px 0 14px 0;
}
.florence-subhead {
    font-family: 'Inter', sans-serif;
    font-size: 1.05rem; font-weight: 400;
    color: var(--f-muted); line-height: 1.55;
    margin: 0 0 16px 0;
    max-width: 720px;
}

/* === Streamlit overrides === */
/* Buttons: deck-styled */
.stButton > button, .stDownloadButton > button {
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    border: 1px solid var(--f-border);
    transition: all 0.12s ease;
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: var(--f-teal) !important;
    color: white !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
    background: var(--f-teal-dark) !important;
}

/* Metric tiles — softer, deck-card aesthetic */
[data-testid="stMetric"] {
    background: var(--f-gray);
    border: 1px solid var(--f-border);
    border-radius: 10px;
    padding: 14px 18px;
}
[data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    color: var(--f-muted) !important;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
[data-testid="stMetricValue"] {
    font-family: 'Playfair Display', Georgia, serif !important;
    color: var(--f-navy) !important;
    font-weight: 600 !important;
}
[data-testid="stMetricDelta"] {
    font-family: 'Inter', sans-serif !important;
    color: var(--f-muted) !important;
}

/* Tabs — flatter, brand-aligned */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid var(--f-border);
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    color: var(--f-muted);
    padding: 8px 14px;
}
.stTabs [aria-selected="true"] {
    color: var(--f-teal-dark) !important;
    border-bottom: 2px solid var(--f-teal) !important;
}

/* Success / info boxes — softer deck colors */
[data-testid="stAlert"] {
    border-radius: 10px;
    border: none;
}

/* Expander label — Inter inherits from html; only override weight */
[data-testid="stExpander"] details summary { font-weight: 500; }

/* Divider — softer */
hr { border-color: var(--f-border); margin: 28px 0 !important; }

/* Hide Streamlit's default deploy/menu chrome for a cleaner brand presence */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* =================================================================
   REDESIGN COMPONENTS — visual-first patterns to reduce prose
   ================================================================= */

/* === Timeline (horizontal payment schedule) === */
.fl-timeline {
    background: white;
    border: 1px solid var(--f-border);
    border-radius: 12px;
    padding: 28px 24px 22px 24px;
    margin: 12px 0 8px 0;
}
.fl-timeline-track {
    position: relative;
    display: grid;
    grid-template-columns: 1fr 2fr 1fr;
    gap: 0;
    margin: 32px 0 8px 0;
}
.fl-timeline-track::before {
    content: "";
    position: absolute;
    top: 24px;
    left: 4%;
    right: 4%;
    height: 2px;
    background: linear-gradient(90deg, var(--f-teal) 0%, var(--f-teal) 100%);
    z-index: 0;
}
.fl-timeline-node {
    position: relative;
    text-align: center;
    z-index: 1;
}
.fl-timeline-node .dot {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: white;
    border: 3px solid var(--f-teal);
    margin: 0 auto 12px auto;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Playfair Display', serif;
    font-size: 1rem;
    font-weight: 600;
    color: var(--f-teal-dark);
}
.fl-timeline-node.start .dot { background: var(--f-teal); color: white; }
.fl-timeline-node.end .dot { background: var(--f-navy); color: white; border-color: var(--f-navy); }
.fl-timeline-node .amount {
    font-family: 'Playfair Display', serif;
    font-size: 1.6rem;
    font-weight: 600;
    color: var(--f-navy);
    margin-bottom: 4px;
    line-height: 1.1;
}
.fl-timeline-node .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--f-muted);
    font-weight: 600;
}
.fl-timeline-node .caption {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: var(--f-muted);
    margin-top: 6px;
    line-height: 1.4;
}

/* === Delta diagram (Today → Florence — 4 icon row) === */
.fl-delta-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 12px 0 4px 0;
}
.fl-delta-item {
    text-align: center;
    padding: 18px 12px 14px 12px;
    border-radius: 10px;
    background: var(--f-gray);
    border: 1px solid var(--f-border);
}
.fl-delta-item.on-teal {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.22);
}
.fl-delta-item .icon {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined';
    font-size: 28px;
    color: var(--f-teal-dark);
    line-height: 1;
    margin-bottom: 6px;
    font-variation-settings: 'FILL' 0;
}
.fl-delta-item.on-teal .icon { color: white; }
.fl-delta-item .metric {
    font-family: 'Playfair Display', serif;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--f-navy);
    line-height: 1.1;
    margin: 2px 0 4px 0;
}
.fl-delta-item.on-teal .metric { color: white; }
.fl-delta-item .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    color: var(--f-muted);
    text-transform: uppercase;
    font-weight: 600;
}
.fl-delta-item.on-teal .label { color: rgba(255,255,255,0.85); }

/* === Deal flow (5-stage visual nodes) === */
.fl-flow {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 6px;
    margin: 16px 0;
    position: relative;
}
.fl-flow-stage {
    background: white;
    border: 1.5px solid var(--f-border);
    border-radius: 10px;
    padding: 14px 10px 12px 10px;
    text-align: center;
    position: relative;
    transition: all 0.15s ease;
}
.fl-flow-stage.active {
    background: var(--f-teal);
    border-color: var(--f-teal);
}
.fl-flow-stage.closed-won {
    background: var(--f-navy);
    border-color: var(--f-navy);
}
.fl-flow-stage.closed-lost {
    background: #B33A3A;
    border-color: #B33A3A;
}
.fl-flow-stage .icon {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined';
    font-size: 22px;
    color: var(--f-teal-dark);
    line-height: 1;
}
.fl-flow-stage.active .icon,
.fl-flow-stage.closed-won .icon,
.fl-flow-stage.closed-lost .icon { color: white; }
.fl-flow-stage .stage-name {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--f-navy);
    margin-top: 4px;
    letter-spacing: 0.02em;
}
.fl-flow-stage.active .stage-name,
.fl-flow-stage.closed-won .stage-name,
.fl-flow-stage.closed-lost .stage-name { color: white; }
.fl-flow-stage .gate {
    font-family: 'Inter', sans-serif;
    font-size: 0.7rem;
    color: var(--f-muted);
    margin-top: 4px;
    line-height: 1.3;
}
.fl-flow-stage.active .gate,
.fl-flow-stage.closed-won .gate,
.fl-flow-stage.closed-lost .gate { color: rgba(255,255,255,0.85); }
.fl-flow-arrow {
    color: var(--f-border);
    text-align: center;
    align-self: center;
    font-family: 'Material Symbols Rounded';
    font-size: 18px;
}

/* === Persona card === */
.fl-persona-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
    margin: 14px 0;
}
.fl-persona-card {
    background: white;
    border: 1px solid var(--f-border);
    border-radius: 12px;
    padding: 20px 22px;
}
.fl-persona-card .head {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 10px;
}
.fl-persona-card .head .icon {
    font-family: 'Material Symbols Rounded';
    font-size: 28px;
    color: var(--f-teal);
    background: rgba(10,186,181,0.12);
    border-radius: 9px;
    width: 44px; height: 44px;
    display: flex; align-items: center; justify-content: center;
}
.fl-persona-card .head .name {
    font-family: 'Playfair Display', serif;
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--f-navy);
}
.fl-persona-card .optimizes {
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    color: var(--f-muted);
    margin-bottom: 12px;
    line-height: 1.5;
}
.fl-persona-card .opener {
    background: var(--f-gray);
    border-left: 3px solid var(--f-teal);
    padding: 10px 14px;
    border-radius: 4px;
    font-family: 'Inter', sans-serif;
    font-size: 0.88rem;
    color: var(--f-navy);
    margin-bottom: 12px;
    font-style: italic;
}
.fl-persona-card .donts {
    display: flex; flex-wrap: wrap; gap: 6px;
}
.fl-persona-card .donts .chip {
    background: rgba(179,58,58,0.08);
    color: #B33A3A;
    border: 1px solid rgba(179,58,58,0.18);
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    padding: 3px 8px;
    border-radius: 8px;
    font-weight: 500;
}

/* === System tile grid (Inpatient landing) === */
.fl-tile-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
    margin: 14px 0 8px 0;
}
/* Deck-styled tile cards (Avila×Florence). Two brand accents alternate across
   the grid; the .hero stat + badge + rank pill + top rail pick up the accent. */
.fl-tile {
    position: relative;
    background: white;
    border: 1px solid var(--f-border);
    border-radius: 16px;
    padding: 22px 20px 16px 20px;
    margin-bottom: 8px;
    min-height: 196px;
    display: flex; flex-direction: column;
    overflow: hidden;
    --accent: var(--f-teal-dark);
    --accent-soft: rgba(8, 148, 120, 0.10);
    transition: transform 0.14s ease, box-shadow 0.14s ease, border-color 0.14s ease;
}
.fl-tile::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 4px;
    background: var(--accent);
}
.fl-tile.fl-accent-teal   { --accent: var(--f-teal-dark); --accent-soft: rgba(8, 148, 120, 0.10); }
.fl-tile.fl-accent-indigo { --accent: var(--f-indigo);    --accent-soft: rgba(62, 45, 143, 0.10); }
.fl-tile:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 26px rgba(15, 27, 45, 0.10);
    border-color: var(--accent);
}
.fl-tile-head {
    display: flex; align-items: flex-start; gap: 13px;
    margin-bottom: 14px;
    min-height: 56px;
}
.fl-tile-headtext { min-width: 0; }
.fl-tile-logo-img {
    width: 54px; height: 54px;
    object-fit: contain;
    border-radius: 12px;
    background: #fff;
    border: 1px solid var(--f-border);
    padding: 4px;
}
.fl-tile-logo-fallback {
    width: 54px; height: 54px;
    background: var(--accent);
    color: white;
    border-radius: 12px;
    font-family: 'Playfair Display', serif;
    font-size: 1.45rem;
    font-weight: 600;
    display: flex;
    align-items: center; justify-content: center;
    flex-shrink: 0;
}
.fl-tile-name {
    font-family: 'Playfair Display', serif;
    font-size: 1.18rem;
    font-weight: 600;
    color: var(--f-navy);
    line-height: 1.2;
    display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
.fl-tile-sub {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: var(--f-muted);
    margin-top: 3px;
    line-height: 1.35;
}
.fl-tile-tag {
    font-family: 'Inter', sans-serif;
    font-size: 0.68rem; font-weight: 600;
    letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--f-muted);
    margin-top: 6px;
}
.fl-tile-rank {
    display: inline-flex; align-items: center; gap: 5px;
    font-family: 'Inter', sans-serif;
    font-size: 0.66rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--accent);
    background: var(--accent-soft);
    padding: 3px 9px;
    border-radius: 20px;
    letter-spacing: 0.08em;
    margin-top: 6px;
}
.fl-tile-rank .dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--accent); display: inline-block;
}
.fl-tile-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 14px;
    margin: auto 0 4px 0;
}
.fl-tile-stat {
    border-left: 2px solid var(--f-border);
    padding: 1px 0 1px 11px;
}
.fl-tile-stat .v {
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--f-navy);
    line-height: 1.1;
}
.fl-tile-stat .v.hero { color: var(--accent); }
.fl-tile-stat .v .u {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem; font-weight: 500;
    color: var(--f-muted);
}
.fl-tile-stat .l {
    font-family: 'Inter', sans-serif;
    font-size: 0.66rem;
    letter-spacing: 0.10em;
    color: var(--f-muted);
    text-transform: uppercase;
    margin-top: 3px;
}
.fl-tile-actions { margin-top: auto; }

/* "Open →" button beneath each tile card — compact, full-width, brand hover */
section[data-testid="stMain"] .stButton > button[kind="secondary"]:hover {
    border-color: var(--f-teal) !important;
    color: var(--f-teal-dark) !important;
}

/* === Multi-logo strip (for consortium tiles like UC Health) === */
.fl-tile-logo-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-bottom: 10px;
    align-items: center;
}
.fl-tile-logo-strip .fl-tile-logo-fallback {
    width: auto;
    min-width: 38px;
    height: 30px;
    padding: 0 9px;
    font-size: 0.72rem;
    border-radius: 8px;
    background: var(--accent);
    opacity: 0.92;
    transition: transform 0.15s ease, opacity 0.15s ease;
}
.fl-tile-logo-strip .fl-tile-logo-fallback:hover {
    transform: scale(1.06);
    opacity: 1;
}

/* === Stat tile (compact number-led) === */
.fl-stat {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 14px;
    border-radius: 8px;
    background: var(--f-gray);
    border: 1px solid var(--f-border);
}
.fl-stat .icon {
    font-family: 'Material Symbols Rounded';
    font-size: 22px;
    color: var(--f-teal-dark);
}
.fl-stat .value {
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--f-navy);
}
.fl-stat .label {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: var(--f-muted);
}
</style>
"""

st.markdown(FLORENCE_CSS, unsafe_allow_html=True)
inject_theme(st)  # editorial design-system layer — restyles metrics/buttons/tabs/sidebar/dataframe


def florence_brand_strip(section_tag: str = "PRICING ENGINE · INTERNAL"):
    """Florence brand mark + page indicator strip — deck-style top header."""
    st.markdown(
        f"""
        <div class="florence-brand-strip">
          <div class="florence-mark">
            <span class="f-box">F</span>
            <span>Florence</span>
          </div>
          <div class="florence-section-tag">{section_tag}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def florence_eyebrow(text: str):
    """All-caps tracked label, deck-style ('01 · THE OPPORTUNITY')."""
    st.markdown(f'<div class="florence-eyebrow">{text}</div>', unsafe_allow_html=True)


def florence_headline(text: str, subhead: str | None = None):
    """Editorial-style serif headline + optional subhead."""
    html = f'<div class="florence-headline">{text}</div>'
    if subhead:
        html += f'<div class="florence-subhead">{subhead}</div>'
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Per-system proposal bundle + quick-actions popup
# ---------------------------------------------------------------------------

def _recs_with_ownership() -> pd.DataFrame:
    """recommendations.parquet with current ownership re-applied (same logic as
    the inpatient view's _load_recs, but callable from module-level helpers)."""
    rec_path = DATA_DIR / "recommendations.parquet"
    if not rec_path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(rec_path)
    u = cached_universe(sysov.overrides_mtime())
    u["ccn"] = u["ccn"].astype(str).str.zfill(6)
    df["ccn"] = df["ccn"].astype(str).str.zfill(6)
    df = df.drop(columns=["health_system_id", "health_system"], errors="ignore").merge(
        u[["ccn", "health_system_id", "health_system"]], on="ccn", how="left"
    )
    return df


@st.cache_data(show_spinner="Preparing the customer package…")
def build_system_bundle_zip(system_id: str, placeholder_msp_markup_pct: float):
    """Build ONE branded proposal ZIP (customer deck + exec summary PDF/HTML +
    Excel workbook) for a system. Cached so the quick-actions popup and the
    detail view share a single, consistent deliverable and re-opens are instant.
    Returns (zip_bytes, filename); (b"", "bundle.zip") if no recommendations."""
    df = _recs_with_ownership()
    if df.empty:
        return b"", "bundle.zip"
    sys_recs = df[df["health_system_id"] == system_id].copy()
    if sys_recs.empty:
        return b"", "bundle.zip"
    name = str(sys_recs.iloc[0]["health_system"])
    safe = name.replace(" ", "_").replace("/", "_").replace("'", "")[:48]
    offset = float(sys_recs["target_target_offset_pct"].median())
    cal = Calibration(
        target_offset_pct=offset,
        placeholder_msp_markup_pct=placeholder_msp_markup_pct,
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        xlsx = write_system_workbook(system_id, tmp / f"{safe}.xlsx", cal, CohortMix(eta=1.0))
        h, p = build_system_exec_summary(system_id, tmp, cal, CohortMix(eta=1.0))
        pptx_buf = build_deck_from_system_recs(sys_recs, name, target_offset_pct=offset)
        pptx_path = tmp / f"{safe}_customer_deck.pptx"
        pptx_path.write_bytes(pptx_buf.getvalue())

        # Ready-to-send outreach email, pre-filled with this system's figures so
        # the rep has the exact language + hero number the moment they download.
        import outreach_email as _oe

        def _sum(c):
            return float(sys_recs[c].sum()) if c in sys_recs.columns else 0.0
        _term_impact = _sum("target_term_net_savings_account")
        _rn_need = int(_sum("rn_need"))
        _seq = _oe.compose_sequence(
            system_name=name,
            annual_savings=_term_impact / 2,
            term_impact=_term_impact,
            rn_need=_rn_need,
            monthly_fee=_sum("target_monthly_florence_fee_account"),
        )
        import call_script as _cs
        _script = _cs.build_script(
            system_name=name, annual_savings=_term_impact / 2, term_impact=_term_impact,
            rn_need=_rn_need, monthly_fee=_sum("target_monthly_florence_fee_account"))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(pptx_path, pptx_path.name)
            zf.write(Path(xlsx), Path(xlsx).name)
            zf.write(Path(p), Path(p).name)
            zf.write(Path(h), Path(h).name)
            zf.writestr("outreach_email.txt", _oe.sequence_as_txt(_seq))
            zf.writestr("call_script.txt", _cs.as_text(_script))
        return buf.getvalue(), f"{safe}_recommendation_bundle.zip"


def build_outreach_pack_zip(system_ids, placeholder_msp_markup_pct):
    """Bulk 'work my queue': for each selected system, emit a folder with the
    ready-to-send outreach_email.txt + branded postcard/letter HTML, plus a
    manifest.csv. NOT cached (depends on mutable contacts). Returns
    (zip_bytes, manifest_df)."""
    import outreach_email as _oe
    import lob_mailer as _mail
    import contacts as _contacts
    rows, buf = [], io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sid in system_ids:
            m = _bundle_system_metrics(sid, sysov.overrides_mtime())
            if not m:
                continue
            cc = _contacts.get_contact("system", sid)
            annual = m["term_impact"] / 2
            email_seq = _oe.compose_sequence(
                system_name=m["name"], annual_savings=annual, term_impact=m["term_impact"],
                rn_need=m["rn_need"], monthly_fee=m["monthly_fee"],
                contact_name=cc.get("contact_name", ""),
            )
            safe = ("".join(c for c in m["name"] if c.isalnum() or c in " _-")
                    .strip().replace(" ", "_")[:48] or str(sid))
            common = dict(org_name=m["name"], contact_name=cc.get("contact_name", ""),
                          address1=cc.get("address1", ""), city=cc.get("city", ""),
                          state=cc.get("state", ""), zip=cc.get("zip", ""),
                          monthly_fee=m["monthly_fee"], term_impact=m["term_impact"],
                          rn_need=m["rn_need"])
            pc = _mail.mailpiece_html("postcard", **common)
            ltr = _mail.mailpiece_html("letter", title=cc.get("title", ""), **common)
            zf.writestr(f"{safe}/outreach_email.txt", _oe.sequence_as_txt(email_seq))
            zf.writestr(f"{safe}/postcard_front.html", pc["front"])
            zf.writestr(f"{safe}/postcard_back.html", pc["back"])
            zf.writestr(f"{safe}/letter.html", ltr["letter"])
            rows.append({"system": m["name"], "annual_savings": annual,
                         "has_email": bool(cc.get("email")), "mailable": bool(cc.get("mailable")),
                         "contact": cc.get("contact_name", "")})
        man = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["system", "annual_savings", "has_email", "mailable", "contact"])
        zf.writestr("manifest.csv", man.to_csv(index=False))
    return buf.getvalue(), man


@st.cache_data(show_spinner=False)
def _bundle_system_metrics(system_id: str, overrides_mtime: float = 0.0) -> dict:
    """Headline numbers for the quick-actions popup (cached)."""
    df = _recs_with_ownership()
    if df.empty:
        return {}
    rows = df[df["health_system_id"] == system_id]
    if rows.empty:
        return {}

    def _sum(c):
        return float(rows[c].sum()) if c in rows.columns else 0.0

    return {
        "name": str(rows.iloc[0]["health_system"]),
        "n_facilities": int(len(rows)),
        "rn_need": int(_sum("rn_need")),
        "monthly_fee": _sum("target_monthly_florence_fee_account"),
        "term_impact": _sum("target_term_net_savings_account"),
    }


@st.cache_data(show_spinner=False)
def _all_systems_agg(overrides_mtime: float = 0.0) -> pd.DataFrame:
    """System-level rollup (id, name, rn_need, fee, 24-mo savings) for the Today
    worklist + priority ranking outside the inpatient view. Excludes the
    'independent' bucket. Cached on the contact/overrides mtime."""
    df = _recs_with_ownership()
    if df.empty:
        return pd.DataFrame()
    if "feasible" in df.columns:
        df = df[df["feasible"]]
    df = df[df["health_system_id"] != "independent"]
    if df.empty:
        return pd.DataFrame()
    if "state" not in df.columns:
        df = df.assign(state="")
    g = (
        df.groupby("health_system_id")
        .agg(
            health_system=("health_system",
                           lambda s: max(s.dropna().astype(str), key=len, default="")),
            rn_need=("rn_need", "sum"),
            monthly_fee_target=("target_monthly_florence_fee_account", "sum"),
            term_savings_target=("target_term_net_savings_account", "sum"),
            primary_state=("state", lambda s: s.mode().iat[0] if len(s.mode()) else ""),
        )
        .reset_index()
        .sort_values("term_savings_target", ascending=False)
    )
    return g


def _money(v) -> str:
    v = float(v or 0)
    if v >= 1e9:
        return f"${v / 1e9:,.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.2f}K"
    return f"${v:,.2f}"


def _push_recent(system_id: str) -> None:
    rec = st.session_state.setdefault("recent_systems", [])
    if system_id in rec:
        rec.remove(system_id)
    rec.insert(0, system_id)
    del rec[6:]


@st.dialog("System quick actions", width="large")
def open_system_quick_actions(system_id: str, placeholder_msp_markup_pct: float):
    """Popup from a system tile: preview the headline numbers + deal stage, then
    open the full detail view or download the branded ZIP in one click."""
    import workbench
    m = _bundle_system_metrics(system_id, sysov.overrides_mtime())
    if not m:
        st.warning("This system has no current recommendations.")
        return
    florence_eyebrow(m["name"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Facilities", f"{m['n_facilities']:,}")
    c2.metric("RN need", f"{m['rn_need']:,}")
    c3.metric("Florence fee / mo", _money(m["monthly_fee"]))
    c4.metric("24-mo impact", _money(m["term_impact"]))

    stage = workbench.system_stage_map().get(system_id, "")
    if stage:
        lbl = workbench.STAGE_LABEL.get(stage, stage)
        clr = workbench.STAGE_COLOR.get(stage, "#475467")
        st.markdown(
            f"<span style='display:inline-block;margin-top:4px;padding:2px 10px;"
            f"border-radius:999px;font-size:0.72rem;font-weight:600;"
            f"background:{clr}1A;color:{clr};'>&#9679; {lbl}</span>",
            unsafe_allow_html=True,
        )
    # ── Owner (territory / my-book) ───────────────────────────────────
    import ownership as _own
    _rep = st.session_state.get("current_user_email") or ""
    _owner = _own.owner_of(system_id)
    _ow1, _ow2 = st.columns([2.6, 1])
    _ow1.caption(f"Owner: {_owner or 'unassigned'}")
    with _ow2:
        if _rep and _owner == _rep.lower():
            if st.button("Release", key=f"qa_release_{system_id}", use_container_width=True):
                _own.unassign(system_id)
        elif _rep:
            if st.button("Assign to me", key=f"qa_assign_{system_id}", use_container_width=True):
                _own.assign(system_id, _rep, by=_rep)

    # Outreach status — system-level de-dupe + the next coordinated touch.
    import sales_intel as _si
    _touched = _si.already_touched("system", system_id)
    if _touched:
        _resp = " · responded" if _touched["responded"] else ""
        st.caption(
            f":material/history: Last touch: {_touched['piece_type'] or 'mail'} "
            f"({_touched['status']}{_resp}) on {_touched['when']} · {_touched['count']} "
            f"total — coordinate, don't duplicate."
        )
    _cad = _si.cadence_next("system", system_id)
    if not _cad.get("done"):
        _due = ("due now" if _cad.get("ready")
                else (f"in {_cad['due_in_days']}d" if _cad.get("due_in_days") else ""))
        st.markdown(
            f"<div style='font-size:.82rem;color:var(--f-muted);margin-top:2px;'>"
            f"<b>Next touch:</b> {_cad['label']}{(' · ' + _due) if _due else ''}</div>",
            unsafe_allow_html=True,
        )
    # Log an outcome — one click advances the deal stage AND halts the cadence.
    _oc_rep = st.session_state.get("current_user_email") or ""

    def _log_outcome(outcome: str, stage_to: str):
        import lob_mailer as _mail_oc
        _mail_oc.record_outcome("system", system_id, outcome, org_name=m["name"], by=_oc_rep)
        try:
            import workbench as _wb_oc
            _wb_oc.upsert_system_stage(system_id, m["name"], stage_to, _oc_rep, note=outcome)
        except Exception:
            pass
        try:
            import crm_sync as _crm_oc
            _crm_oc.streak_upsert_box(name=m["name"], fields={"stage": stage_to, "outcome": outcome})
        except Exception:
            pass
        st.toast(f"Logged: {outcome}")

    _o1, _o2, _o3 = st.columns(3)
    if _o1.button("Replied", key=f"qa_oc_reply_{system_id}", use_container_width=True):
        _log_outcome("Replied", "discovery")
    if _o2.button("Meeting booked", key=f"qa_oc_meet_{system_id}", use_container_width=True):
        _log_outcome("Meeting booked", "discovery")
    if _o3.button("Not interested", key=f"qa_oc_no_{system_id}", use_container_width=True):
        _log_outcome("Not interested", "closed_lost")

    # Snooze — defer this account; it drops off Today until the date.
    import reminders as _rem
    _snz = _rem.snoozed_until("system", system_id)
    if _snz:
        _zc1, _zc2 = st.columns([2.6, 1])
        _zc1.caption(f"Snoozed until {_snz}")
        if _zc2.button("Unsnooze", key=f"qa_unsnz_{system_id}", use_container_width=True):
            _rem.clear("system", system_id)
    else:
        _zc1, _zc2 = st.columns([1.6, 1])
        _snz_days = _zc1.selectbox(
            "Snooze", [3, 7, 14, 30], format_func=lambda d: f"in {d} days",
            key=f"qa_snzdays_{system_id}", label_visibility="collapsed")
        if _zc2.button("Snooze", key=f"qa_snz_{system_id}", use_container_width=True):
            _rem.snooze("system", system_id, _snz_days,
                        by=(st.session_state.get("current_user_email") or ""))
    st.divider()

    a, b, d = st.columns([1.2, 1.2, 0.7])
    with a:
        if st.button("Open full detail →", type="primary", use_container_width=True,
                     key=f"qa_detail_{system_id}"):
            st.session_state["inpatient_active_system"] = system_id
            st.rerun()
    with b:
        data, fname = build_system_bundle_zip(system_id, placeholder_msp_markup_pct)
        st.download_button(
            ":material/inventory_2: Download ZIP package",
            data, file_name=fname, mime="application/zip",
            use_container_width=True, disabled=not data,
            key=f"qa_zipdl_{system_id}",
        )
    with d:
        pinned = st.session_state.setdefault("pinned_systems", [])
        is_pinned = system_id in pinned
        # No st.rerun() here — the button's own rerun re-renders the open dialog.
        if st.button("★" if is_pinned else "☆ Pin", use_container_width=True,
                     key=f"qa_pin_{system_id}",
                     help="Unpin" if is_pinned else "Pin for quick access"):
            if is_pinned:
                pinned.remove(system_id)
            else:
                pinned.append(system_id)

    # ── Customer contact (editable) ───────────────────────────────────
    st.divider()
    import contacts as _contacts
    cc = _contacts.get_contact("system", system_id)
    who = " · ".join([x for x in (cc.get("contact_name"), cc.get("title")) if x]) or "No named contact yet"
    st.markdown(
        f"<div class='fl-eyebrow pur'>Customer contact</div>"
        f"<div style='margin-top:4px;font-size:.95rem;color:var(--f-ink);'>{who}</div>"
        f"<div style='font-family:var(--f-mono);font-size:.82rem;color:var(--f-muted);margin-top:2px;'>"
        f"Tel {cc.get('phone') or '—'} &nbsp;·&nbsp; Email {cc.get('email') or '—'}</div>",
        unsafe_allow_html=True,
    )
    # ── Find email — derive from the contact's name + the system's domain ─
    import email_discovery as _ed
    _sugg_key = f"sugg_email_{system_id}"
    if not cc.get("email") and cc.get("contact_name"):
        with st.expander("Find email"):
            _sug = _ed.suggest_for(name=cc.get("contact_name", ""), system_id=system_id)
            if not _sug["domain"]:
                st.caption("No email domain on file for this system — add one to the "
                           "directory to enable suggestions.")
            elif not _sug["candidates"]:
                st.caption("Need a first + last name to derive an email.")
            else:
                _mxtxt = ("domain accepts mail ✓" if _sug["mx"] is True
                          else "domain may not accept mail" if _sug["mx"] is False
                          else "deliverability unknown")
                st.caption(f"Likely emails at {_sug['domain']} · {_mxtxt}")
                for _c in _sug["candidates"]:
                    st.code(_c["email"], language=None)
                if st.button("Use top suggestion", key=f"qa_useemail_{system_id}"):
                    st.session_state[_sugg_key] = _sug["top"]
    with st.expander("Edit contact"):
        with st.form(f"qa_contact_{system_id}"):
            f_name = st.text_input("Contact name", value=cc.get("contact_name", ""))
            f_title = st.text_input("Title", value=cc.get("title", ""))
            ce, cp = st.columns(2)
            with ce:
                f_email = st.text_input(
                    "Email",
                    value=cc.get("email") or st.session_state.get(_sugg_key, ""),
                )
            with cp:
                f_phone = st.text_input("Phone", value=cc.get("phone", ""))
            f_addr = st.text_input("Street address", value=cc.get("address1", ""))
            a1, a2, a3 = st.columns([2, 1, 1])
            with a1:
                f_city = st.text_input("City", value=cc.get("city", ""))
            with a2:
                f_state = st.text_input("State", value=cc.get("state", ""))
            with a3:
                f_zip = st.text_input("ZIP", value=cc.get("zip", ""))
            f_notes = st.text_area("Notes", value=cc.get("notes", ""), height=72)
            if st.form_submit_button("Save contact", type="primary"):
                rep = (st.session_state.get("current_user_email")
                       or st.session_state.get("rep_email") or "")
                _contacts.save_contact(
                    "system", system_id, org_name=m["name"],
                    contact_name=f_name, title=f_title, email=f_email, phone=f_phone,
                    address1=f_addr, city=f_city, state=f_state, zip=f_zip,
                    notes=f_notes, by=rep,
                )
                st.success("Contact saved.")

    # ── Direct mail (Lob) — the AI SDR drafts; a human sends ──────────
    import lob_mailer as _mail
    from streamlit.components.v1 import html as _components_html
    mst = _mail.status_for("system", system_id)
    with st.expander("Direct mail" + (f" · {mst['status']}" if mst else "")):
        st.caption(
            ("Lob connected." if _mail.is_configured()
             else "Lob not connected — drafts a preview only; set LOB_API_KEY to send.")
        )
        _ptype = st.radio(
            "Format", ["Postcard", "Letter"], horizontal=True,
            key=f"qa_ptype_{system_id}",
        ).lower()
        _code_now = (mst or {}).get("retrieval_code", "") if mst else ""
        _prev = _mail.preview_html(
            _ptype, org_name=m["name"], contact_name=cc.get("contact_name", ""),
            title=cc.get("title", ""), address1=cc.get("address1", ""),
            city=cc.get("city", ""), state=cc.get("state", ""), zip=cc.get("zip", ""),
            monthly_fee=m["monthly_fee"], term_impact=m["term_impact"],
            rn_need=m["rn_need"], code=_code_now,
            rep_email=(st.session_state.get("current_user_email") or ""),
        )
        _components_html(_prev, height=(720 if _ptype == "letter" else 840), scrolling=True)
        if not cc.get("mailable"):
            st.caption("Add a street address + ZIP on the contact to enable a send.")
        if st.button(f"Draft {_ptype}", key=f"qa_mail_{system_id}",
                     disabled=not cc.get("mailable")):
            st.session_state[f"qa_mailres_{system_id}"] = _mail.draft_and_send(
                "system", system_id, org_name=m["name"],
                to_name=cc.get("contact_name", ""), address1=cc.get("address1", ""),
                city=cc.get("city", ""), state=cc.get("state", ""), zip=cc.get("zip", ""),
                monthly_fee=m["monthly_fee"], term_impact=m["term_impact"],
                rn_need=m["rn_need"], piece_type=_ptype, title=cc.get("title", ""),
                rep_email=(st.session_state.get("current_user_email") or ""),
                by=(st.session_state.get("current_user_email") or ""), live=False,
            )
        res = st.session_state.get(f"qa_mailres_{system_id}")
        if res:
            st.markdown(
                f"**Retrieval code:** `{res['code']}`\n\n"
                f"**{res['preview']['headline']}** — {res['preview']['body']}\n\n"
                f"_{res['preview']['cta']}_"
            )
            if res.get("detail"):
                st.caption(res["detail"])
        if mst and mst.get("status") in ("drafted", "sent"):
            if st.button("Mark responded", key=f"qa_resp_{system_id}"):
                _mail.record_response("system", system_id)

    # ── Outreach email (ready to send) — exact language + this system's numbers ─
    import outreach_email as _oe
    _code = (mst or {}).get("retrieval_code", "") if mst else ""
    _au = f"{_mail.SIGNUP_BASE}?code={_code}" if _code else ""
    _opener = st.session_state.get(f"opener_{system_id}", "")
    _seq = _oe.compose_sequence(
        system_name=m["name"], annual_savings=m["term_impact"] / 2,
        term_impact=m["term_impact"], rn_need=m["rn_need"],
        monthly_fee=m["monthly_fee"], code=_code, activation_url=_au,
        contact_name=cc.get("contact_name", ""),
        rep_email=(st.session_state.get("current_user_email") or ""),
        opener=_opener,
    )
    # Default the step selector to where the cadence says this account is.
    _em_default = 0
    if not _cad.get("done") and _cad.get("step"):
        _em_default = min(int(_cad["step"]), len(_seq)) - 1
    with st.expander("Outreach email · ready to send"):
        st.caption(
            "Pick the sequence step (defaults to where the cadence is). Numbers are "
            "pre-filled — drop in [First name] + your sign-off, send from your inbox."
        )
        _em_i = st.radio(
            "Step", list(range(len(_seq))), index=_em_default,
            format_func=lambda i: _seq[i]["label"], horizontal=True,
            key=f"qa_em_step_{system_id}", label_visibility="collapsed",
        )
        _email = _seq[_em_i]
        st.text_input("Subject", value=_email["subject"], key=f"qa_em_subj_{system_id}")
        st.code(_email["body"], language=None)  # the code block has a copy button
        st.markdown(f"[Open prefilled in your email client →]({_email['mailto']})")
        # Personalize the Intro's lead line from this system's facts (AI if a key
        # is set; otherwise a deterministic local-data opener).
        import ai_opener as _aio
        if st.button("Personalize opener (AI)" if _aio.is_configured() else "Personalize opener",
                     key=f"qa_openers_{system_id}"):
            _r = _aio.generate({"system_name": m["name"], "n_facilities": m.get("n_facilities"),
                                "rn_need": m["rn_need"], "annual_savings": m["term_impact"] / 2})
            st.session_state[f"opener_{system_id}"] = _r["opener"]
            st.session_state[f"opener_src_{system_id}"] = _r["source"]
        if _opener:
            _src = st.session_state.get(f"opener_src_{system_id}", "rule")
            st.caption(f"Personalized opener applied ({'AI' if _src == 'ai' else 'rule-based'}) — "
                       "it leads the Intro step above.")
            if st.button("Clear opener", key=f"qa_openerx_{system_id}"):
                st.session_state.pop(f"opener_{system_id}", None)
                st.session_state.pop(f"opener_src_{system_id}", None)

    # ── Call script + battlecard (phone is the channel with coverage) ─
    import call_script as _cs_popup
    with st.expander("Call script · " + (cc.get("phone") or "no phone on file")):
        _scr = _cs_popup.build_script(
            system_name=m["name"], annual_savings=m["term_impact"] / 2,
            term_impact=m["term_impact"], rn_need=m["rn_need"], monthly_fee=m["monthly_fee"],
            contact_name=cc.get("contact_name", ""), contact_phone=cc.get("phone", ""),
            rep_name=(st.session_state.get("current_user_email") or "").split("@")[0].replace(".", " ").title(),
        )
        _n = _scr["numbers"]
        st.markdown(
            f"<div style='font-family:var(--f-mono);font-size:.82rem;color:var(--f-muted);'>"
            f"{_n['hero_annual']}/yr · ~{_n['per_nurse_mo']}/nurse/mo · {_n['term_24mo']} 24-mo · "
            f"{_n['rn_need']:,} RN</div>", unsafe_allow_html=True)
        st.markdown("**Opening**")
        st.write(_scr["opening"])
        st.markdown("**Talk track**")
        for _b in _scr["beats"]:
            st.markdown(f"- {_b}")
        st.markdown("**Objections**")
        for _q, _a in _scr["objections"]:
            st.markdown(f"- **{_q}**  \n  {_a}")
        st.download_button(
            "Download call script (.txt)", _cs_popup.as_text(_scr),
            file_name="call_script.txt", mime="text/plain",
            key=f"qa_callscript_{system_id}", use_container_width=True)

    # ── Activity & notes — a real per-account timeline ───────────────
    import activity as _act
    with st.expander("Activity & notes"):
        _note = st.text_input("Log a call or note", key=f"qa_note_{system_id}",
                              placeholder="e.g. Left VM with CNO office — call back Thursday")
        _act_rep = st.session_state.get("current_user_email") or ""
        _na, _nb = st.columns(2)
        if _na.button("Log call", key=f"qa_logcall_{system_id}",
                      use_container_width=True, disabled=not _note.strip()):
            _act.log("system", system_id, "call", _note.strip(), org_name=m["name"], by=_act_rep)
            st.toast("Call logged")
        if _nb.button("Log note", key=f"qa_lognote_{system_id}",
                      use_container_width=True, disabled=not _note.strip()):
            _act.log("system", system_id, "note", _note.strip(), org_name=m["name"], by=_act_rep)
            st.toast("Note logged")
        _tl = _act.timeline("system", system_id)
        if not _tl:
            st.caption("No activity yet — touches, outcomes, and notes will appear here.")
        for _e in _tl[:15]:
            _when = str(_e.get("ts", ""))[:16].replace("T", " ")
            st.markdown(
                f"<div style='font-size:.82rem;border-left:2px solid #E4E7EC;"
                f"padding:1px 0 6px 10px;margin:0 0 2px 2px;'>"
                f"<span style='font-family:var(--f-mono);font-size:.72rem;color:var(--f-muted);'>"
                f"{_when}</span> · <b>{_e.get('kind', '')}</b> — {_e.get('detail', '')}</div>",
                unsafe_allow_html=True,
            )

    # ── CRM + Gmail sync (dormant until keys are provisioned) ─────────
    import crm_sync as _crm
    _gok, _sok = _crm.gmail_is_configured(), _crm.streak_is_configured()
    with st.expander("Sync · Gmail draft + Streak CRM"):
        _gc, _sc = st.columns(2)
        with _gc:
            st.caption(f"Gmail: {'connected' if _gok else 'not connected'}")
            if st.button("Create Gmail draft", key=f"qa_gmail_{system_id}",
                         disabled=not cc.get("email"), use_container_width=True):
                st.session_state[f"qa_gmailres_{system_id}"] = _crm.create_gmail_draft(
                    to=cc.get("email", ""), subject=_email["subject"], body=_email["body"])
            if not cc.get("email"):
                st.caption("Add a contact email to draft.")
            _gr = st.session_state.get(f"qa_gmailres_{system_id}")
            if _gr:
                (st.success if _gr.get("ok") else st.caption)(_gr.get("detail", ""))
        with _sc:
            st.caption(f"Streak: {'connected' if _sok else 'not connected'}")
            if st.button("Log to Streak", key=f"qa_streak_{system_id}",
                         use_container_width=True):
                st.session_state[f"qa_streakres_{system_id}"] = _crm.streak_upsert_box(
                    name=m["name"], fields={
                        "annual_savings": m["term_impact"] / 2, "monthly_fee": m["monthly_fee"],
                        "rn_need": m["rn_need"], "stage": stage, "code": _code_now,
                    })
            _sr = st.session_state.get(f"qa_streakres_{system_id}")
            if _sr:
                (st.success if _sr.get("ok") else st.caption)(_sr.get("detail", ""))

    # Account dossier — one-page HTML handoff/leave-behind (hero + script + timeline).
    import dossier as _dossier, call_script as _cs_d, activity as _act_d
    _dz_html = _dossier.render_html(
        system_name=m["name"], metrics=m, contact=cc,
        script=_cs_d.build_script(
            system_name=m["name"], annual_savings=m["term_impact"] / 2,
            term_impact=m["term_impact"], rn_need=m["rn_need"], monthly_fee=m["monthly_fee"],
            contact_name=cc.get("contact_name", ""), contact_phone=cc.get("phone", "")),
        email_intro=_seq[0]["body"], timeline=_act_d.timeline("system", system_id),
        owner=_owner, stage=stage,
    )
    st.download_button(
        ":material/description: Download account dossier (HTML)", _dz_html,
        file_name=f"florence_dossier_{system_id}.html", mime="text/html",
        use_container_width=True, key=f"qa_dossier_{system_id}")

    st.caption(
        "ZIP includes the customer deck (.pptx), exec summary (PDF + HTML), the "
        "Excel workbook, and a ready-to-send outreach email (outreach_email.txt)."
    )


@st.dialog("Call workspace", width="large")
def open_call_workspace(ccn: str, agent: str):
    """Focused outbound-call panel: claim → dial → script → disposition → timeline."""
    import contacts as _c, call_script as _cs, callcenter as _cc, activity as _act
    _cc.claim(ccn, agent)
    cc = _c.get_contact("facility", ccn)
    name = cc.get("org_name") or str(ccn)
    phone = (cc.get("phone") or "").strip()
    florence_eyebrow(name)
    _loc = " · ".join(x for x in (cc.get("city"), cc.get("state")) if x)
    _who = " · ".join(x for x in (cc.get("contact_name"), cc.get("title")) if x) or "No named contact"
    st.markdown(f"<div style='color:var(--f-muted);font-size:.9rem;'>{_loc}</div>"
                f"<div style='font-size:.9rem;'>{_who}</div>", unsafe_allow_html=True)
    if phone:
        _digits = "".join(c for c in phone if c.isdigit() or c == "+")
        st.markdown(f"<div style='font-family:var(--f-mono);font-size:1.5rem;color:var(--f-ink);"
                    f"margin:6px 0;'>{phone}</div>", unsafe_allow_html=True)
        st.link_button(f"Call {phone}", f"tel:{_digits}", use_container_width=True, type="primary")
        import ringcentral as _rc
        if _rc.is_configured():
            if st.button("Call via RingCentral (RingOut)", key=f"cw_ro_{ccn}", use_container_width=True):
                _r = _rc.ringout(agent_number=st.session_state.get("rc_agent_number", ""), to_number=_digits)
                (st.success if _r.get("ok") else st.caption)(_r.get("detail", ""))
    else:
        st.caption("No phone on file for this facility.")
    _pr = _cc.facility_pricing(ccn)
    _scr = _cs.build_script(
        system_name=name, annual_savings=(_pr.get("term_impact", 0) or 0) / 2,
        term_impact=_pr.get("term_impact", 0), rn_need=_pr.get("rn_need", 0),
        monthly_fee=_pr.get("monthly_fee", 0), contact_name=cc.get("contact_name", ""),
        contact_phone=phone, rep_name=(agent.split("@")[0].replace(".", " ").title() if agent else ""))
    with st.expander("Script + objections", expanded=True):
        st.write(_scr["opening"])
        for _b in _scr["beats"]:
            st.markdown(f"- {_b}")
        st.markdown("**If they push back**")
        for _q, _a in _scr["objections"][:3]:
            st.markdown(f"- **{_q}** — {_a}")
    st.markdown("**Log the call**")
    _note = st.text_input("Note (optional)", key=f"cw_note_{ccn}")
    _cbd = st.selectbox("Callback in", [3, 7, 14], format_func=lambda d: f"{d} days", key=f"cw_cbd_{ccn}")

    def _disp(outcome, cb=None):
        _cc.disposition(ccn, agent, outcome, note=_note, callback_days=cb, org_name=name)
        st.session_state["cc_flash"] = f"{name}: {outcome}"
        st.rerun()

    _r1 = st.columns(3)
    if _r1[0].button("Connected", key=f"cw_c_{ccn}", use_container_width=True):
        _disp("Connected")
    if _r1[1].button("No answer", key=f"cw_na_{ccn}", use_container_width=True):
        _disp("No answer", _cbd)
    if _r1[2].button("Left VM", key=f"cw_vm_{ccn}", use_container_width=True):
        _disp("Left voicemail", _cbd)
    _r2 = st.columns(3)
    if _r2[0].button("Callback", key=f"cw_cb_{ccn}", use_container_width=True):
        _disp("Callback", _cbd)
    if _r2[1].button("Not interested", key=f"cw_ni_{ccn}", use_container_width=True):
        _disp("Not interested")
    if _r2[2].button("Interested →", key=f"cw_int_{ccn}", type="primary", use_container_width=True):
        _disp("Interested → handoff")
    _tl = _act.timeline("facility", ccn)
    if _tl:
        st.divider()
        for _e in _tl[:5]:
            st.markdown(f"<div style='font-size:.8rem;color:var(--f-muted);'>"
                        f"{str(_e.get('ts',''))[:16].replace('T',' ')} · {_e.get('kind','')} — "
                        f"{_e.get('detail','')}</div>", unsafe_allow_html=True)


def _render_quick_access_row(sys_agg, placeholder_msp_markup_pct: float) -> None:
    """Compact 'Pinned & recent' quick-open chips above the tile grid."""
    pinned = st.session_state.get("pinned_systems", [])
    recent = st.session_state.get("recent_systems", [])
    ids = list(dict.fromkeys(list(pinned) + list(recent)))[:8]
    if not ids:
        return
    name_by_id = {}
    if "health_system_id" in getattr(sys_agg, "columns", []):
        for _, r in sys_agg.iterrows():
            name_by_id[r["health_system_id"]] = r.get("health_system", r["health_system_id"])
    st.markdown(
        "<div class='florence-eyebrow' style='margin:2px 0 6px 0;'>Pinned &amp; recent</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    for i, sid in enumerate(ids):
        label = ("★ " if sid in pinned else "") + str(name_by_id.get(sid, sid))[:22]
        with cols[i % 4]:
            if st.button(label, key=f"quick_open_{sid}", use_container_width=True):
                _push_recent(sid)
                open_system_quick_actions(sid, placeholder_msp_markup_pct)


def render_contact_panel(entity_type: str, entity_id: str, *, org_name: str,
                         monthly_fee: float = 0.0, term_impact: float = 0.0) -> None:
    """Inline customer-contact + direct-mail panel for any account
    (hospital / outpatient facility / chain). Display + edit (incl. address),
    NPPES address fetch, and the Lob drafter — all tracked. Reusable across views."""
    import contacts as _contacts
    import lob_mailer as _mail
    cc = _contacts.get_contact(entity_type, str(entity_id))
    florence_eyebrow("Customer contact")
    who = " · ".join([x for x in (cc.get("contact_name"), cc.get("title")) if x]) or "No named contact yet"
    addr = " · ".join([x for x in (cc.get("address1"), cc.get("city"), cc.get("state"), cc.get("zip")) if x]) or "No address on file"
    st.markdown(
        f"<div style='font-size:.95rem;color:var(--f-ink);'>{who}</div>"
        f"<div style='font-family:var(--f-mono);font-size:.82rem;color:var(--f-muted);'>"
        f"Tel {cc.get('phone') or '—'} · Email {cc.get('email') or '—'}</div>"
        f"<div style='font-family:var(--f-mono);font-size:.78rem;color:var(--f-muted);'>{addr}</div>",
        unsafe_allow_html=True,
    )
    if entity_type in ("facility", "hospital") and not cc.get("address1"):
        if st.button("Fetch address (NPPES)", key=f"cp_fetch_{entity_type}_{entity_id}"):
            try:
                import nppes_enrich
                got = nppes_enrich.enrich_ccn(str(entity_id))
                st.success("Address found." if got else "No NPPES address for this NPI.")
            except Exception as e:
                st.caption(f"Lookup failed: {e}")

    with st.expander("Edit contact"):
        with st.form(f"cp_form_{entity_type}_{entity_id}"):
            f_name = st.text_input("Contact name", value=cc.get("contact_name", ""))
            f_title = st.text_input("Title", value=cc.get("title", ""))
            e1, e2 = st.columns(2)
            with e1:
                f_email = st.text_input("Email", value=cc.get("email", ""))
            with e2:
                f_phone = st.text_input("Phone", value=cc.get("phone", ""))
            f_addr = st.text_input("Street address", value=cc.get("address1", ""))
            a1, a2, a3 = st.columns([2, 1, 1])
            with a1:
                f_city = st.text_input("City", value=cc.get("city", ""))
            with a2:
                f_state = st.text_input("State", value=cc.get("state", ""))
            with a3:
                f_zip = st.text_input("ZIP", value=cc.get("zip", ""))
            f_notes = st.text_area("Notes", value=cc.get("notes", ""), height=68)
            if st.form_submit_button("Save contact", type="primary"):
                rep = (st.session_state.get("current_user_email")
                       or st.session_state.get("rep_email") or "")
                _contacts.save_contact(
                    entity_type, str(entity_id), org_name=org_name,
                    contact_name=f_name, title=f_title, email=f_email, phone=f_phone,
                    address1=f_addr, city=f_city, state=f_state, zip=f_zip,
                    notes=f_notes, by=rep,
                )
                st.success("Contact saved.")

    mst = _mail.status_for(entity_type, str(entity_id))
    with st.expander("Direct mail" + (f" · {mst['status']}" if mst else "")):
        st.caption("Lob connected." if _mail.is_configured()
                   else "Lob not connected — drafts a preview; set LOB_API_KEY to send.")
        if not cc.get("mailable"):
            st.caption("Add a street address + ZIP (or Fetch from NPPES) to enable mail.")
        if st.button("Draft postcard", key=f"cp_mail_{entity_type}_{entity_id}",
                     disabled=not cc.get("mailable")):
            st.session_state[f"cp_mres_{entity_type}_{entity_id}"] = _mail.draft_and_send(
                entity_type, str(entity_id), org_name=org_name,
                to_name=cc.get("contact_name", ""), address1=cc.get("address1", ""),
                city=cc.get("city", ""), state=cc.get("state", ""), zip=cc.get("zip", ""),
                monthly_fee=monthly_fee, term_impact=term_impact,
                by=(st.session_state.get("current_user_email") or ""), live=False,
            )
        res = st.session_state.get(f"cp_mres_{entity_type}_{entity_id}")
        if res:
            st.markdown(f"**Code:** `{res['code']}` — {res['preview']['body'][:140]}…")
            if res.get("detail"):
                st.caption(res["detail"])
        if mst and mst.get("status") in ("drafted", "sent"):
            if st.button("Mark responded", key=f"cp_resp_{entity_type}_{entity_id}"):
                _mail.record_response(entity_type, str(entity_id))


# ---------------------------------------------------------------------------
# Cached data
# ---------------------------------------------------------------------------

@st.cache_data
def cached_universe(overrides_mtime: float = 0.0) -> pd.DataFrame:
    """Universe with any active system-ownership overrides applied.

    `overrides_mtime` is used as a cache key — when the override file changes,
    Streamlit invalidates the cache and reloads.
    """
    return sysov.apply_overrides(load_universe())


@st.cache_data
def cached_priced(
    pricing_mode: str,
    target_offset_pct: float,
    price_floor_monthly: float, price_ceiling_monthly: float,
    standard_monthly_fee: float,
    eta: float, fica_eligible_months: int, term_months: int,
    immigration_addon_enabled: bool,
    amn_partner_markup_pct: float, direct_partner_markup_pct: float,
    rn_share_of_contracted_labor: float, coverage_fill_factor: float,
    agency_displacement_factor: float,
    placeholder_msp_markup_pct: float,
) -> pd.DataFrame:
    cal = Calibration(
        pricing_mode=PricingMode(pricing_mode),
        target_offset_pct=target_offset_pct,
        price_floor_monthly=price_floor_monthly,
        price_ceiling_monthly=price_ceiling_monthly,
        standard_monthly_fee=standard_monthly_fee,
        term_months=term_months,
        fica_eligible_months_default=fica_eligible_months,
        immigration_addon_enabled=immigration_addon_enabled,
        amn_partner_markup_pct=amn_partner_markup_pct,
        direct_partner_markup_pct=direct_partner_markup_pct,
        rn_share_of_contracted_labor=rn_share_of_contracted_labor,
        coverage_fill_factor=coverage_fill_factor,
        agency_displacement_factor=agency_displacement_factor,
        placeholder_msp_markup_pct=placeholder_msp_markup_pct,
    )
    cohort = CohortMix(eta=eta)
    return price_batch(cached_universe(sysov.overrides_mtime()), cohort, cal)


@st.cache_data
def cached_sweep() -> pd.DataFrame:
    return calibration_sweep(cached_universe(sysov.overrides_mtime()))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("Pricing calibration")
st.sidebar.caption(
    "Florence Workforce Economist v2 (May 2026). "
    "FICA-offset target pricing. Adjust the sliders below; all views update live."
)

# Pricing mode is locked to FICA_OFFSET_TARGET — the v2 canonical mode.
# ─── Sidebar: clean grouped layout ────────────────────────────────────
# Defaults that the rep rarely needs to touch live as constants;
# everything in the sidebar is what a rep WOULD touch per deal.
eta = 1.0                       # η — full F-1 cohort (locked, see bottom footnote)
fica_eligible_months = 24       # FICA-exempt months per nurse

# ── 1. Pricing mode — the top-level choice ──
st.sidebar.markdown(
    "<div style='font-family:Inter,sans-serif; font-size:0.7rem; "
    "letter-spacing:0.18em; text-transform:uppercase; color:#067F7B; "
    "font-weight:600; margin: 0 0 6px 0;'>Market-based pricing</div>",
    unsafe_allow_html=True,
)
# Market-based (FICA-offset) pricing only — flat placement fee retired.
pricing_mode = PricingMode.FICA_OFFSET_TARGET.value

# ── 2. Market-based calibration ──
st.sidebar.markdown("**Market-based calibration**")
_target_offset_pct_int = st.sidebar.slider(
    "Target FICA offset %", 10, 100, 40, 5,
    format="%d%%",
    help="Target share of the Florence fee offset by employer FICA savings. "
         "Default 40% — Florence retains 60% of fee net of FICA.",
)
target_offset_pct = _target_offset_pct_int / 100.0
price_floor_monthly = st.sidebar.slider(
    "Price floor ($/RN/month)", 500, 3000, 750, 50,
)
price_ceiling_monthly = st.sidebar.slider(
    "Price ceiling ($/RN/month)", 1000, 5000, 2000, 50,
)
term_months = st.sidebar.selectbox(
    "Contract term (months)", [12, 18, 24, 36, 48], index=2,
)
standard_monthly_fee = 1750.0

# ── 3. Partner channel ──
with st.sidebar.expander(":material/handshake: Partner channel (atop core rate)", expanded=False):
    st.caption(
        "Partners add their margin on top of Florence's core rate. "
        "Florence's net is protected at the core rate; customer pays core + markup."
    )
    _direct_markup_int = st.slider(
        "Direct enterprise markup", 0, 50, 0, 5,
        format="%d%%",
        key="sb_direct_markup",
    )
    _amn_markup_int = st.slider(
        "Distribution-partner markup", 0, 50, 20, 1,
        format="%d%%",
        key="sb_amn_markup",
    )
    direct_partner_markup_pct = _direct_markup_int / 100.0
    amn_partner_markup_pct = _amn_markup_int / 100.0
amn_partner_share = amn_partner_markup_pct
direct_partner_share = direct_partner_markup_pct

# ── 4. Capacity assumptions (per-deal levers, less common) ──
with st.sidebar.expander(":material/tune: Capacity & need assumptions", expanded=False):
    rn_share = st.slider(
        "RN share of contracted labor", 0.50, 1.0, 0.80, 0.05, key="sb_rn_share",
    )
    coverage = st.slider(
        "Coverage / displacement target", 0.50, 1.0, 0.90, 0.05, key="sb_coverage",
    )
    agency_displacement_factor = st.slider(
        "Agency displacement factor", 0.50, 1.0, 1.0, 0.05, key="sb_disp_factor",
        help="Fraction of each Florence RN's hours that displace agency labor (vs. fills new vacancy).",
    )
    immigration_addon_enabled = st.checkbox(
        "Include $5K immigration add-on",
        value=False,
        key="sb_immig",
        help="$5,000 over 24mo = $208/RN/mo for transition coordination.",
    )

# ── 5. MSP overlay (one-line, mostly autopilot) ──
with st.sidebar.expander(":material/balance: MSP / agency-overlay tuning", expanded=False):
    st.caption(
        "**Kaiser** uses real-disclosed $622M partner overlay (+$17.39/hr). "
        "**11 other systems** (HCA, Sutter, Providence, UPMC, etc.) use the placeholder "
        "% below until their MSP data is disclosed."
    )
    _msp_markup_int = st.slider(
        "Placeholder MSP markup %",
        0, 50, 25, 1,
        format="%d%%",
        key="sb_msp_markup",
    )
    placeholder_msp_markup_pct = _msp_markup_int / 100.0

# ── Backward-compat aliases for downstream code that referenced v1 names ─
premium_capture_rate = 0.075         # legacy v1 default (kept for display only)
premium_floor = 0.50
premium_cap = 3.00
exempt_years = fica_eligible_months / 12.0  # years equivalent
commitment_years = max(1, int(round(term_months / 12)))
amortization_months = term_months
zeta = 0.0  # no buffer in v2 model


# ---------------------------------------------------------------------------
# Page header (compute aggregates silently; surface only via collapsed panel)
# ---------------------------------------------------------------------------

universe = cached_universe(sysov.overrides_mtime())
priced = cached_priced(
    pricing_mode,
    target_offset_pct, price_floor_monthly, price_ceiling_monthly,
    standard_monthly_fee,
    eta, fica_eligible_months, term_months,
    immigration_addon_enabled,
    amn_partner_markup_pct, direct_partner_markup_pct,
    rn_share, coverage, agency_displacement_factor,
    placeholder_msp_markup_pct,
)

total = len(priced)
feas = priced[priced["feasible"]]
manual_review_count = int(priced["manual_review_flag"].sum())
addressable_rn = feas["rn_need"].sum()

# v2 5 primary buyer-facing numbers (medians)
median_monthly_fee = feas["florence_monthly_fee_per_rn"].median() if len(feas) else 0
median_fica = feas["employer_fica_savings_per_rn_per_month"].median() if len(feas) else 0
median_effective = feas["fica_adjusted_effective_cost_per_rn_month"].median() if len(feas) else 0
median_offset_pct = feas["actual_fica_offset_pct"].median() if len(feas) else 0
median_net = feas["net_monthly_savings_per_rn"].median() if len(feas) else 0

# Aggregates
total_monthly_fee = feas["monthly_florence_fee_account"].sum()
total_monthly_fica = feas["monthly_fica_offset_account"].sum()
total_monthly_net_savings = feas["monthly_net_savings_account"].sum()
term_florence_fee = feas["term_florence_fee_account"].sum()
term_net_savings = feas["term_net_savings_account"].sum()

# Retain legacy variable aliases used by older tabs
median_premium = median_monthly_fee
median_fee = feas["f_total"].median() if len(feas) else 0
median_monthly = median_monthly_fee
gross_fee = term_florence_fee
monthly_fee = total_monthly_fee
florence_net = feas["florence_net_term_account"].sum() if len(feas) else 0
partner_rev = feas["partner_revenue_term_account"].sum() if len(feas) else 0
gross_agency_savings = feas["term_gross_agency_savings_account"].sum() if len(feas) else 0
net_savings = term_net_savings
# (Dropped legacy c5/c6 metric duplicates; v2 metrics are above in the k* and a* rows.)


# ---------------------------------------------------------------------------
# Auth gate — FlorenceRN Core SSO (shared fl_session cookie), with fallbacks
# ---------------------------------------------------------------------------
# Off by default so local dev runs without ceremony. In any shared / staging /
# production deployment set:
#     export FLORENCE_INTERNAL_AUTH=1
# PREFERRED path: FlorenceRN Core SSO — the shared cookie is verified against
# Core's JWKS (core_auth.py) and the Core role maps to rbac.py's admin/ops/rep;
# territory comes from the token, else the rbac CSV. The Google-OIDC
# (florence_auth.py) and email-OTP (auth.py) paths remain as fallbacks.
import os as _os
_AUTH_REQUIRED = _os.environ.get("FLORENCE_INTERNAL_AUTH") == "1"
current_user = None
current_role = "admin"   # default in unauthenticated local mode
current_territory = "ALL"

try:
    import rbac as _rbac
except Exception:
    _rbac = None

# 1) FlorenceRN Core SSO — verify the shared cookie (preferred across the fleet).
import core_auth as _core
_core_user = _core.current_user(st) if _core.is_configured() else None
if _core_user and _core_user.get("role"):
    current_user = {"email": _core_user["email"], "name": _core_user.get("name", "")}
    current_role = _core_user["role"]
    current_territory = _core_user.get("territory") or (
        _rbac.get_territory(_core_user["email"]) if _rbac else None) or "ALL"
elif _AUTH_REQUIRED and _core.is_configured():
    # Auth required but no valid Core session → send the user to Core to sign in.
    _core.require_login(st)  # renders a sign-in card and st.stop()s

# 2) Legacy fallbacks (only when Core didn't resolve a signed-in user).
if current_user is None:
    import florence_auth as _gauth
    _g_user = _gauth.require_login(st)  # Google OIDC; no-ops unless [auth] secrets exist
    if _g_user is not None:
        current_user = {"email": _g_user["email"], "name": _g_user.get("name", "")}
        if _rbac:
            try:
                _rbac.bootstrap_first_admin(_g_user["email"])
                current_role = _rbac.get_role(_g_user["email"]) or "rep"
                current_territory = _rbac.get_territory(_g_user["email"]) or "ALL"
            except Exception:
                pass
    if _g_user is None and _AUTH_REQUIRED and _rbac:
        import auth as _flo_auth
        _tok = st.session_state.get("florence_session_token")
        current_user = _flo_auth.get_session(_tok) if _tok else None
        if _tok and current_user is None:
            st.session_state["florence_session_token"] = None
        if current_user is None:
            st.markdown(
                "<div style='max-width:520px; margin:80px auto; padding:32px; "
                "border:1px solid #E5E8EE; border-radius:12px; background:white;'>",
                unsafe_allow_html=True,
            )
            st.markdown("### Florence Workforce Economist")
            st.caption("Internal tool — staff sign-in required.")
            current_user = _flo_auth.streamlit_login(st, default_role="rep", title="", blurb="")
            st.markdown("</div>", unsafe_allow_html=True)
            if current_user is None:
                st.stop()
            # Bootstrap: first user becomes admin
            _rbac.bootstrap_first_admin(current_user["email"])
            current_user = _flo_auth.get_user(current_user["email"]) or current_user
        current_role = _rbac.get_role(current_user["email"]) or "rep"
        current_territory = _rbac.get_territory(current_user["email"]) or "ALL"
else:
    import florence_auth as _gauth  # ensure _gauth exists for the logout control below

# Expose for downstream code (tabs can call _rbac.require_role() etc.)
st.session_state["current_user"] = current_user
st.session_state["current_role"] = current_role
st.session_state["current_territory"] = current_territory
if current_user and current_user.get("email"):
    st.session_state["current_user_email"] = current_user["email"]

# Sidebar sign-out: Core logout when signed in via Core; else the native (Google)
# control, which no-ops unless Google auth is configured.
if _core_user and _core_user.get("role"):
    st.sidebar.caption(f"Signed in · {_core_user['email']} ({current_role})")
    st.sidebar.link_button("Sign out", _core.logout_url(_core.app_origin(st)))
else:
    _gauth.logout_button(st)


# ---------------------------------------------------------------------------
# Coaching tooltip helper — surfaces playbook.coach_tip() inline.
# ---------------------------------------------------------------------------
# Use anywhere a number, button, or chart would benefit from a one-paragraph
# explanation. Role-aware: reps see "what to say"; admins see "where it
# comes from." Pass to any Streamlit widget's `help=` kwarg.
def _tip(key: str, value=None) -> str:
    try:
        import playbook as _playbook_helper
        return _playbook_helper.coach_tip(
            key,
            role=st.session_state.get("current_role", "rep"),
            value=value,
        )
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sidebar navigation — single source of truth for navigating the system
# ---------------------------------------------------------------------------
# Inpatient + Outpatient are the daily sales-today views and sit at the top
# of the sidebar. Everything else is grouped by purpose below. On mobile
# Streamlit collapses this into a hamburger icon automatically.
if "nav_view" not in st.session_state:
    st.session_state["nav_view"] = "inpatient"


def _nav_button(label: str, view_key: str, icon: str = "") -> None:
    is_active = (st.session_state.get("nav_view") == view_key)
    full_label = f":material/{icon}: {label}" if icon else label
    if st.sidebar.button(
        full_label,
        key=f"nav_{view_key}",
        use_container_width=True,
        type=("primary" if is_active else "secondary"),
    ):
        st.session_state["nav_view"] = view_key
        st.rerun()


def _nav_section(title: str) -> None:
    st.sidebar.markdown(
        f"<div style='font-family:Inter,sans-serif; font-size:0.7rem; "
        f"letter-spacing:0.14em; text-transform:uppercase; color:#475467; "
        f"margin:18px 0 6px 0; font-weight:600;'>{title}</div>",
        unsafe_allow_html=True,
    )


# Brand at top of sidebar
st.sidebar.markdown(
    "<div style='display:flex; align-items:center; gap:10px; "
    "padding:6px 0 4px 0; margin-bottom:6px;'>"
    "<span style='display:inline-block; width:32px; height:32px; "
    "background:#0ABAB5; color:#fff; border-radius:7px; text-align:center; "
    "line-height:32px; font-family:Playfair Display,Georgia,serif; "
    "font-size:1.15rem; font-weight:500;'>F</span>"
    "<span style='font-family:Playfair Display,Georgia,serif; font-size:1.05rem; "
    "color:#101828; font-weight:500; line-height:1.1;'>"
    "Workforce<br>Economist</span></div>"
    "<div style='font-family:Inter,sans-serif; font-size:0.7rem; "
    "letter-spacing:0.14em; color:#475467; text-transform:uppercase;'>"
    "INTERNAL</div>",
    unsafe_allow_html=True,
)

# ─── Sales today ──────────────────────────────────────────────────
_nav_section("Sales today")
_nav_button("Today", "today", "today")
_nav_button("Inpatient", "inpatient", "local_hospital")
_nav_button("Outpatient", "outpatient", "medical_services")
_nav_button("Funnel", "funnel", "filter_alt")
_nav_button("Call center", "call_center", "call")

# ─── Growth automation ───────────────────────────────────────────
_nav_section("Growth automation")
_nav_button("Growth automation", "growth", "rocket_launch")

# ─── Live intelligence ───────────────────────────────────────────
_nav_section("Live intelligence")
_nav_button("Market intelligence", "market_intel", "trending_up")
_nav_button("Forecasting", "forecast", "insights")

# ─── Sales training ──────────────────────────────────────────────
_nav_section("Sales training")
_nav_button("Playbook", "playbook", "menu_book")
_nav_button("Onboarding", "onboarding", "school")
_nav_button("Pipeline", "pipeline", "assignment")

# ─── Deep tools ──────────────────────────────────────────────────
_nav_section("Deep tools")
_nav_button("Market map", "market_map", "map")
_nav_button("Health systems", "health_systems", "business")
_nav_button("System ownership", "system_ownership", "swap_horiz")
_nav_button("Price a hospital", "price_hospital", "local_hospital")
_nav_button("Hospital table", "hospital_table", "table_view")
_nav_button("Market view", "market_view", "stacked_line_chart")
_nav_button("Elasticity", "elasticity", "show_chart")
_nav_button("Calibration sweep", "calibration_sweep", "settings")

# ─── Data ────────────────────────────────────────────────────────
_nav_section("Data")
_nav_button("Contacts", "contacts", "contacts")
_nav_button("Data quality", "data_quality", "verified")
_nav_button("Data provenance", "data_provenance", "library_books")

# ─── Auth signed-in info (at the bottom of sidebar) ─────────────
if _AUTH_REQUIRED and current_user is not None:
    st.sidebar.markdown(
        "<hr style='border:none; border-top:1px solid #E5E8EE; margin:18px 0 10px 0;'>",
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown(
            f"<div style='font-size:0.7rem; letter-spacing:0.12em; "
            f"text-transform:uppercase; color:#475467; font-weight:600;'>"
            f"SIGNED IN</div>"
            f"<div style='font-weight:600; color:#101828; font-size:0.9rem; "
            f"margin-top:2px;'>{current_user['email']}</div>"
            f"<div style='font-size:0.78rem; color:#475467; margin-top:2px;'>"
            f"Role: <b>{current_role}</b> · Territory: <b>{current_territory}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("Sign out", use_container_width=True, key="internal_signout"):
            import auth as _flo_auth_logout
            _flo_auth_logout.streamlit_logout(st)
            st.rerun()

        # Admin panel — role assignment, only for admins
        if current_role == "admin":
            with st.expander(":material/admin_panel_settings: Admin · "
                             "user roles", expanded=False):
                import rbac as _rbac_admin
                _rbac_admin.streamlit_admin_panel(st)


# Active view from session state (used by every content block below)
view = st.session_state.get("nav_view", "inpatient")


# Florence brand header at the top of the main area
florence_brand_strip(section_tag="WORKFORCE ECONOMIST  ·  INTERNAL")

# =====================================================================
# 🎯 SYSTEM RECOMMENDATION TAB — the sales-rep landing page
# =====================================================================
if view == "inpatient":
    florence_eyebrow("Inpatient · Build a customer proposal")
    florence_headline(
        "Pick a hospital system. See the impact.",
        subhead="Premium agency labor → permanent international RNs. One-click proposal.",
    )

    # ── Data load ─────────────────────────────────────────────────────
    @st.cache_data
    def _load_recs(overrides_mtime: float = 0.0) -> pd.DataFrame:
        """Load recommendations parquet and apply any active system overrides
        on top of it, so the System Recommendation tab always shows current
        ownership mappings without needing a full recompute."""
        rec_path = DATA_DIR / "recommendations.parquet"
        if not rec_path.exists():
            from recommendation_engine import batch_recommend
            df = batch_recommend(cached_universe(sysov.overrides_mtime()))
            df.to_parquet(rec_path, index=False)
        else:
            df = pd.read_parquet(rec_path)
        # Re-apply current ownership from the override-applied universe
        u = cached_universe(overrides_mtime)
        u["ccn"] = u["ccn"].astype(str).str.zfill(6)
        df["ccn"] = df["ccn"].astype(str).str.zfill(6)
        df = df.drop(columns=["health_system_id", "health_system"], errors="ignore")
        df = df.merge(
            u[["ccn", "health_system_id", "health_system"]],
            on="ccn", how="left",
        )
        return df

    CENSUS_REGION = {
        # Northeast
        "CT": "Northeast", "ME": "Northeast", "MA": "Northeast", "NH": "Northeast",
        "NJ": "Northeast", "NY": "Northeast", "PA": "Northeast", "RI": "Northeast", "VT": "Northeast",
        # Midwest
        "IL": "Midwest", "IN": "Midwest", "IA": "Midwest", "KS": "Midwest", "MI": "Midwest",
        "MN": "Midwest", "MO": "Midwest", "NE": "Midwest", "ND": "Midwest", "OH": "Midwest",
        "SD": "Midwest", "WI": "Midwest",
        # South
        "AL": "South", "AR": "South", "DE": "South", "DC": "South", "FL": "South",
        "GA": "South", "KY": "South", "LA": "South", "MD": "South", "MS": "South",
        "NC": "South", "OK": "South", "SC": "South", "TN": "South", "TX": "South",
        "VA": "South", "WV": "South",
        # West
        "AK": "West", "AZ": "West", "CA": "West", "CO": "West", "HI": "West",
        "ID": "West", "MT": "West", "NV": "West", "NM": "West", "OR": "West",
        "UT": "West", "WA": "West", "WY": "West",
    }

    recs = _load_recs(sysov.overrides_mtime())
    # RBAC: filter recs to the signed-in rep's territory (no-op if territory == ALL)
    if _AUTH_REQUIRED:
        import rbac as _rbac_filt
        _terr = st.session_state.get("current_territory", "ALL")
        recs_pre = len(recs)
        recs = _rbac_filt.filter_by_territory(recs, _terr, state_col="state")
        if _terr != "ALL" and recs_pre != len(recs):
            st.caption(
                f":material/filter_alt: Filtered to your territory "
                f"({_terr}) — {len(recs):,} of {recs_pre:,} facilities."
            )
    feas_recs = recs[recs["feasible"]].copy()
    feas_recs["region"] = feas_recs["state"].map(CENSUS_REGION).fillna("Other")

    # ── Find a system — prominent search at the very top of the landing ──
    if st.session_state.get("inpatient_active_system") is None:
        st.text_input(
            "Find a health system",
            placeholder="Type a system name — e.g. Honor Health, HCA, Sutter…",
            key="inpatient_search",
        )

    # ── Compact filter & sort (collapsed by default) ──────────────────
    with st.expander(":material/tune: Filter & sort", expanded=False):
        ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.2, 1.2, 1.4, 1.0])
        with ctrl_col1:
            rate_basis = st.radio(
                "Show pricing as",
                ["Per RN per month", "Per RN per hour"],
                horizontal=True,
                help="Hospital CFOs anchor in different units — monthly for budgets, hourly for agency comparisons.",
            )
            use_hourly = rate_basis == "Per RN per hour"
        with ctrl_col2:
            sort_mode = st.selectbox(
                "Sort systems",
                ["By Florence revenue (desc)", "Alphabetical", "By primary state",
                 "By region (West→Northeast)"],
            )
        with ctrl_col3:
            state_filter = st.multiselect(
                "Filter by state (multi)",
                sorted(feas_recs["state"].unique()),
                help="For regional reps: select your states; only systems with facilities there are shown.",
            )
        with ctrl_col4:
            show_independent = st.checkbox(
                "Include Independent / Unknown",
                value=False,
                help="Hospitals not yet classified into a named system. ~85% of the universe.",
            )

    # Apply filter
    fr = feas_recs.copy()
    if state_filter:
        sys_with_state = fr[fr["state"].isin(state_filter)]["health_system_id"].unique()
        fr = fr[fr["health_system_id"].isin(sys_with_state)]
    if not show_independent:
        fr = fr[fr["health_system"] != "Independent / Unknown"]

    # Group by health_system_id ONLY to avoid duplicates when the universe
    # has inconsistent display names for the same system (e.g. "CommonSpirit"
    # vs "CommonSpirit Health"). We take the longest health_system string in
    # each group as the canonical name; the directory display_name overrides
    # this downstream in merged_systems().
    sys_agg = (
        fr.groupby("health_system_id")
        .agg(
            health_system=("health_system",
                           lambda s: max(s.dropna().astype(str), key=len, default="")),
            n_facilities=("ccn", "count"),
            rn_need=("rn_need", "sum"),
            monthly_fee_target=("target_monthly_florence_fee_account", "sum"),
            term_savings_target=("target_term_net_savings_account", "sum"),
            primary_state=("state", lambda s: s.mode().iat[0] if len(s.mode()) else ""),
        )
        .reset_index()
    )
    sys_agg["primary_region"] = sys_agg["primary_state"].map(CENSUS_REGION).fillna("Other")

    if sort_mode == "Alphabetical":
        sys_agg = sys_agg.sort_values("health_system")
    elif sort_mode == "By primary state":
        sys_agg = sys_agg.sort_values(["primary_state", "health_system"])
    elif sort_mode == "By region (West→Northeast)":
        region_order = {"West": 0, "Midwest": 1, "South": 2, "Northeast": 3, "Other": 4}
        sys_agg["_ro"] = sys_agg["primary_region"].map(region_order)
        sys_agg = sys_agg.sort_values(["_ro", "primary_state", "health_system"])
    else:
        sys_agg = sys_agg.sort_values("monthly_fee_target", ascending=False)

    if len(sys_agg) == 0:
        st.warning("No systems match the current filter — clear state filter or include Independent.")
        st.stop()

    # Build selector labels — customer-savings-led, not Florence-rev-led
    sys_label_map = {}
    last_region = None
    for _, row in sys_agg.iterrows():
        if sort_mode == "By region (West→Northeast)" and row["primary_region"] != last_region:
            divider = f"── {row['primary_region']} ──"
            sys_label_map[divider] = None
            last_region = row["primary_region"]
        savings_b = row["term_savings_target"] / 1e9
        savings_m = row["term_savings_target"] / 1e6
        savings_str = f"${savings_b:.2f}B" if savings_b >= 1 else f"${savings_m:,.0f}M"
        label = (
            f"{row['health_system']} ({row['primary_state']}) — "
            f"{row['n_facilities']} facilities · {savings_str} impact over 24 mo"
        )
        sys_label_map[label] = row["health_system_id"]

    # ── Tile-grid landing OR detail view (session-state driven) ──────
    import system_tiles
    active_sys = st.session_state.get("inpatient_active_system")

    if active_sys is None:
        # ── Priority outreach queue — savings × reachability ───────────
        import sales_intel as _si_rank
        import contacts as _ct_rank
        with st.expander(":material/bolt: Priority outreach queue — work these first",
                         expanded=False):
            st.caption(
                "Ranked by 24-mo customer impact weighted by how reachable the account "
                "is. A high-impact system with no contact yet is your cue to go find one."
            )
            import ownership as _own_pq
            _rep_pq = st.session_state.get("current_user_email") or ""
            _recs_pq = sys_agg.to_dict("records")
            if _rep_pq and st.checkbox("My book only", value=False, key="prio_mybook"):
                _book_pq = _own_pq.book_of(_rep_pq)
                _recs_pq = [r for r in _recs_pq if str(r.get("health_system_id")) in _book_pq]
            _ranked = _si_rank.rank_systems(_recs_pq, _ct_rank.get_contact, limit=30)[:12]

            # Bulk — work my queue: one outreach pack for several systems.
            _opt_map = {p["name"]: p["system_id"] for p in _ranked}
            with st.container(border=True):
                st.markdown("**Bulk — work my queue**")
                _pick = st.multiselect(
                    "Systems to pack", list(_opt_map.keys()),
                    default=list(_opt_map.keys())[:5], key="bulk_queue_pick",
                    label_visibility="collapsed",
                )
                _ids = [_opt_map[n] for n in _pick]
                _bk1, _bk2 = st.columns([1.4, 1])
                with _bk1:
                    # Build on click only — never compute the ZIP on page load, and
                    # never let a failure here take down the landing page.
                    if not _ids:
                        st.caption("Pick at least one system above.")
                    elif st.button(f":material/inventory_2: Build outreach pack ({len(_ids)})",
                                   key="bulk_queue_build", use_container_width=True):
                        try:
                            st.session_state["bulk_pack"] = build_outreach_pack_zip(
                                _ids, placeholder_msp_markup_pct)
                            st.session_state.pop("bulk_pack_err", None)
                        except Exception as _e:
                            st.session_state["bulk_pack"] = None
                            st.session_state["bulk_pack_err"] = str(_e)[:200]
                    _bp = st.session_state.get("bulk_pack")
                    if _bp:
                        _pack, _man = _bp
                        st.download_button(
                            f":material/download: Download pack ({len(_man)} systems)",
                            _pack, file_name="florence_outreach_pack.zip",
                            mime="application/zip", use_container_width=True,
                            key="bulk_queue_dl",
                        )
                        st.caption(
                            f"{int(_man['has_email'].sum())} of {len(_man)} have an email · "
                            f"{int(_man['mailable'].sum())} mailable · each folder: email + "
                            "postcard + letter"
                        )
                    elif st.session_state.get("bulk_pack_err"):
                        st.caption("Pack build failed — " + st.session_state.pop("bulk_pack_err"))
                with _bk2:
                    import crm_sync as _crm_bulk
                    import outreach_email as _oe_bulk
                    _gok, _sok = _crm_bulk.gmail_is_configured(), _crm_bulk.streak_is_configured()
                    if st.button("Queue Gmail + Streak", key="bulk_queue_crm",
                                 use_container_width=True, disabled=not (_ids and (_gok or _sok))):
                        _gn = _sn = 0
                        for _sid in _ids:
                            _mm = _bundle_system_metrics(_sid, sysov.overrides_mtime())
                            if not _mm:
                                continue
                            _cc2 = _ct_rank.get_contact("system", _sid)
                            _em = _oe_bulk.compose_email(
                                system_name=_mm["name"], annual_savings=_mm["term_impact"] / 2,
                                term_impact=_mm["term_impact"], rn_need=_mm["rn_need"],
                                monthly_fee=_mm["monthly_fee"], contact_name=_cc2.get("contact_name", ""))
                            if _gok and _cc2.get("email") and _crm_bulk.create_gmail_draft(
                                    to=_cc2["email"], subject=_em["subject"], body=_em["body"]).get("ok"):
                                _gn += 1
                            if _sok and _crm_bulk.streak_upsert_box(
                                    name=_mm["name"], fields={"annual_savings": _mm["term_impact"] / 2,
                                                              "rn_need": _mm["rn_need"]}).get("ok"):
                                _sn += 1
                        st.success(f"Queued {_gn} Gmail drafts · {_sn} Streak boxes")
                    if not (_gok or _sok):
                        st.caption("Connect Gmail / Streak to queue drafts here.")
            st.divider()

            for _pr in _ranked:
                _c1, _c2, _c3, _c4 = st.columns([3, 1.3, 1.5, 1.0])
                with _c1:
                    st.markdown(
                        f"**{_pr['name']}**<br>"
                        f"<span style='color:var(--f-muted);font-size:.8rem;'>"
                        f"{_pr['rn_need']:,} RN need · {_money(_pr['monthly_fee'])}/mo fee</span>",
                        unsafe_allow_html=True,
                    )
                _c2.metric("24-mo impact", _money(_pr["term_savings"]))
                _rc = {"Reachable": "#067F7B", "Partial": "#B7791F",
                       "No contact": "#B33A3A"}.get(_pr["reach_label"], "#475467")
                _miss = (f"<div style='font-size:.7rem;color:var(--f-muted);margin-top:2px;'>"
                         f"needs {', '.join(_pr['missing'][:2])}</div>" if _pr["missing"] else "")
                _c3.markdown(
                    f"<div style='margin-top:6px;'><span style='font-size:.72rem;"
                    f"font-weight:600;padding:2px 8px;border-radius:999px;"
                    f"background:{_rc}1A;color:{_rc};'>{_pr['reach_label']} "
                    f"{_pr['reach_pct']}%</span>{_miss}</div>",
                    unsafe_allow_html=True,
                )
                with _c4:
                    if st.button("Open →", key=f"prio_open_{_pr['system_id']}",
                                 use_container_width=True):
                        open_system_quick_actions(_pr["system_id"], placeholder_msp_markup_pct)

        # Tile grid — the rep's landing
        # Toggle: Health systems (ranked by scale) vs Hospitals (by RN need)
        tile_mode = st.radio(
            "Show",
            ["Biggest health systems", "Biggest hospitals"],
            horizontal=True,
            label_visibility="collapsed",
            key="inpatient_tile_mode",
        )

        if tile_mode == "Biggest health systems":
            florence_eyebrow("Top U.S. health systems · by scale")
            search_q = st.session_state.get("inpatient_search", "")  # box now lives at the top
            _render_quick_access_row(sys_agg, placeholder_msp_markup_pct)
            with st.expander(":material/inventory_2: Bulk download — bundles for several systems"):
                _opts = {str(r["health_system"]): str(r["health_system_id"])
                         for _, r in sys_agg.iterrows()
                         if str(r.get("health_system", "")).strip()}
                _picks = st.multiselect("Systems", list(_opts.keys()), key="bulk_picks")
                if _picks and st.button(f"Build {len(_picks)} bundle(s) (.zip)", key="bulk_build"):
                    with st.spinner("Building bundles…"):
                        _buf = io.BytesIO()
                        with zipfile.ZipFile(_buf, "w", zipfile.ZIP_DEFLATED) as _zf:
                            for _nm in _picks:
                                _data, _fn = build_system_bundle_zip(_opts[_nm], placeholder_msp_markup_pct)
                                if _data:
                                    _zf.writestr(f"{_nm.replace('/', '_')}/{_fn}", _data)
                        st.session_state["bulk_zip"] = _buf.getvalue()
                if st.session_state.get("bulk_zip"):
                    st.download_button(
                        ":material/download: Download all bundles (.zip)",
                        st.session_state["bulk_zip"],
                        file_name="florence_proposal_bundles.zip",
                        mime="application/zip", key="bulk_dl",
                    )
            st.caption(
                ":material/touch_app: Click a tile to preview the numbers, "
                "download the package, or open full detail."
            )
            try:
                import workbench as _wb
                _stage_map = _wb.system_stage_map()
            except Exception:
                _stage_map = {}
            clicked = system_tiles.render_inpatient_tile_grid(
                st, sys_agg, search=search_q, status_map=_stage_map,
            )
            if clicked:
                _action, _sid = clicked
                _push_recent(_sid)
                if _action == "open":
                    st.session_state["inpatient_active_system"] = _sid
                    st.rerun()
                else:
                    open_system_quick_actions(_sid, placeholder_msp_markup_pct)

            # Fallback dropdown for unranked / "everything else"
            _unranked = system_tiles.render_unranked_count(st, sys_agg)
            with st.expander(
                f":material/search: Search all systems "
                f"({_unranked} not in the ranked directory)",
                expanded=False,
            ):
                selected_label = st.selectbox(
                    "Pick any system",
                    list(sys_label_map.keys()),
                    label_visibility="collapsed",
                    key="inpatient_dropdown_fallback",
                )
                if selected_label and sys_label_map.get(selected_label):
                    if st.button(
                        f"Open {selected_label.split(' (')[0]} →",
                        type="primary",
                        key="inpatient_dropdown_open",
                    ):
                        st.session_state["inpatient_active_system"] = sys_label_map[selected_label]
                        st.rerun()
        else:
            # Hospitals view — individual facilities sorted by RN need
            florence_eyebrow("Top U.S. hospitals · by RN need")
            st.caption(":material/touch_app: Click any tile to open the hospital in Price-a-hospital.")
            clicked_ccn = system_tiles.render_hospital_tile_grid(st, fr)
            if clicked_ccn:
                # Pre-select this hospital in the Price-a-hospital view + navigate
                st.session_state["price_hospital_preselect_ccn"] = clicked_ccn
                st.session_state["nav_view"] = "price_hospital"
                st.rerun()

        st.stop()

    # ── Detail view ────────────────────────────────────────────────
    if st.button("← Back to systems", key="inpatient_back"):
        st.session_state["inpatient_active_system"] = None
        st.rerun()

    selected_sys_id = active_sys
    sys_recs = fr[fr["health_system_id"] == selected_sys_id].copy()
    if sys_recs.empty:
        st.warning(
            "This system isn't in the current filter. Clearing the filter "
            "and showing the system list."
        )
        st.session_state["inpatient_active_system"] = None
        st.rerun()
    selected_sys_name = sys_recs.iloc[0]["health_system"]

    # ── Core numbers (computed once, used everywhere) ─────────────────
    n_facilities = len(sys_recs)
    states = sorted(sys_recs["state"].unique())
    total_rn_need = sys_recs["rn_need"].sum()
    total_monthly_target = sys_recs["target_monthly_florence_fee_account"].sum()
    total_monthly_stretch = sys_recs["stretch_monthly_florence_fee_account"].sum()
    total_monthly_reference = sys_recs["reference_monthly_florence_fee_account"].sum()
    total_term_fee_target = sys_recs["target_term_florence_fee_account"].sum()
    total_term_savings_target = sys_recs["target_term_net_savings_account"].sum()
    total_monthly_savings_target = total_term_savings_target / 24
    median_target_fee_monthly = sys_recs["target_monthly_fee"].median()
    median_target_savings_monthly = sys_recs["target_net_monthly_savings_per_rn"].median()
    median_savings_ratio = sys_recs["target_savings_ratio"].median()
    median_target_pct = sys_recs["target_target_offset_pct"].median()
    weighted_deal_score = (
        (sys_recs["target_deal_score"] * sys_recs["target_monthly_florence_fee_account"]).sum()
        / total_monthly_target if total_monthly_target > 0 else 0
    )
    posture = (
        "Aggressive (high-confidence accounts)" if median_target_pct <= 0.42 else
        "Balanced" if median_target_pct <= 0.52 else
        "Conservative (focus on close rate)"
    )

    def _fmt_rate(monthly: float) -> str:
        if use_hourly:
            return f"${monthly/156:,.2f}/hr"
        return f"${monthly:,.0f}/mo"

    def _fmt_big(value: float) -> str:
        """Format a $ value as $X.XXB or $XXM as appropriate."""
        if value >= 1e9:
            return f"${value/1e9:.2f}B"
        return f"${value/1e6:,.0f}M"

    # ─────────────────────────────────────────────────────────────────
    # 🏥 CUSTOMER PITCH HERO — deck-style "Same hours. Two prices."
    # ─────────────────────────────────────────────────────────────────
    st.divider()
    states_str = ", ".join(states[:5]) + ("..." if len(states) > 5 else "")

    # Compute deck-style comparison numbers
    median_agency_premium = float(sys_recs["signal_agency_premium"].median())
    median_florence_hourly = float(sys_recs["target_hourly_fee"].median())
    median_fica_per_hour = float(sys_recs["target_fica_savings_per_rn_per_month"].median()) / 156
    florence_net_hourly = max(median_florence_hourly - median_fica_per_hour, 0.01)
    annual_savings = total_term_savings_target / 2  # 24mo → annual
    annual_rn_hours = total_rn_need * 156 * 12
    cost_ratio = median_agency_premium / florence_net_hourly if florence_net_hourly > 0 else 0

    florence_eyebrow(f"01 · The opportunity · For {selected_sys_name}")
    florence_headline(
        "Same hours. Two prices.",
        subhead=(
            f"The {annual_rn_hours/1e6:,.1f}M agency RN hours {selected_sys_name} used last year will recur. "
            f"The choice is what to pay per hour, and what to get for it."
        ),
    )

    st.markdown(
        f"""
        <div style="display:flex; align-items:baseline; gap:14px; margin: 6px 0 22px 0;">
          <div style="font-family:'Inter',sans-serif; font-size:0.78rem; font-weight:600;
                      letter-spacing:0.22em; text-transform:uppercase; color:#475467;">SAME</div>
          <div style="font-family:'Playfair Display',serif; font-size:1.9rem; font-weight:600;
                      color:#101828;">{annual_rn_hours/1e6:,.1f}M</div>
          <div style="font-family:'Inter',sans-serif; font-size:0.95rem; color:#475467;">
            RN hours per year · {selected_sys_name} baseline, expected to recur
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Two-card price comparison — TODAY (white) vs WITH FLORENCE (teal)
    card_l, card_arrow, card_r = st.columns([5, 0.6, 5])
    with card_l:
        st.markdown(
            f"""
            <div class="florence-card today">
              <div class="card-label">Today</div>
              <div style="display:flex; align-items:baseline; gap:6px;">
                <div class="card-number">${median_agency_premium:,.2f}</div>
                <div class="card-unit">/hour</div>
              </div>
              <div class="card-headline">Agency staffing premium.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with card_arrow:
        st.markdown(
            "<div style='font-family:Playfair Display,serif; font-size:2rem; color:#0ABAB5;"
            " text-align:center; padding-top:75px;'>→</div>",
            unsafe_allow_html=True,
        )
    with card_r:
        st.markdown(
            f"""
            <div class="florence-card with-florence">
              <div class="card-label">With Florence</div>
              <div style="display:flex; align-items:baseline; gap:6px;">
                <div class="card-number">${florence_net_hourly:,.2f}</div>
                <div class="card-unit">/hour</div>
              </div>
              <div class="card-headline">Permanent capacity.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Delta row — 4 icons showing what shifts between Today and With Florence
    _hourly_delta = median_agency_premium - florence_net_hourly
    st.markdown(
        f"""
        <div class="fl-delta-row">
          <div class="fl-delta-item">
            <div class="icon">savings</div>
            <div class="metric">${_hourly_delta:,.0f}/hr</div>
            <div class="label">Cost impact</div>
          </div>
          <div class="fl-delta-item">
            <div class="icon">group_add</div>
            <div class="metric">{int(total_rn_need):,} RNs</div>
            <div class="label">Permanent capacity</div>
          </div>
          <div class="fl-delta-item">
            <div class="icon">loyalty</div>
            <div class="metric">24+ mo</div>
            <div class="label">Median retention</div>
          </div>
          <div class="fl-delta-item">
            <div class="icon">verified</div>
            <div class="metric">Replacement</div>
            <div class="label">Protection</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Navy footer banner — the closing pitch number
    st.markdown(
        f"""
        <div class="florence-banner">
          <div class="banner-text">
            Annual financial impact · net of Florence fees
          </div>
          <div style="display:flex; align-items:baseline; gap:14px;">
            <div class="banner-value">{_fmt_big(annual_savings)}</div>
            <div class="banner-suffix">{cost_ratio:.0f}× lower per-hour cost</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─────────────────────────────────────────────────────────────────
    # 02 · CHANNEL PRICING — Direct vs Via distribution partner (markup atop core rate)
    # ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("02 · Channel pricing")
    florence_headline(
        "Two channels. Same Florence economics.",
        subhead="Direct = customer-friendly price. Distribution partner = markup on top. Florence net is identical.",
    )
    core_monthly = sys_recs["target_monthly_fee"].median()
    core_per_rn_per_mo = sys_recs["target_monthly_florence_fee_account"].sum() / max(sys_recs["rn_need"].sum(), 1)
    direct_per_rn_per_mo = core_per_rn_per_mo * (1 + direct_partner_markup_pct)
    amn_per_rn_per_mo = core_per_rn_per_mo * (1 + amn_partner_markup_pct)
    amn_margin_per_rn = core_per_rn_per_mo * amn_partner_markup_pct

    ch_l, ch_r = st.columns(2)
    with ch_l:
        st.markdown(
            f"""
            <div class="florence-card today" style="min-height:200px;">
              <div class="card-label">Direct enterprise</div>
              <div style="display:flex; align-items:baseline; gap:6px;">
                <div class="card-number">${direct_per_rn_per_mo:,.0f}</div>
                <div class="card-unit">/RN/mo</div>
              </div>
              <div class="card-headline">Sold direct.</div>
              <div class="card-body">
                Florence direct enterprise channel. Customer pays Florence's core rate
                with {direct_partner_markup_pct:.0%} partner markup. Florence collects
                <b>${core_per_rn_per_mo:,.0f}/RN/mo</b> net.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with ch_r:
        st.markdown(
            f"""
            <div class="florence-card with-florence" style="min-height:200px;">
              <div class="card-label">Via distribution partner ({amn_partner_markup_pct:.0%} markup)</div>
              <div style="display:flex; align-items:baseline; gap:6px;">
                <div class="card-number">${amn_per_rn_per_mo:,.0f}</div>
                <div class="card-unit">/RN/mo</div>
              </div>
              <div class="card-headline">Sold through distribution partner.</div>
              <div class="card-body">
                Partner's distribution channel. Customer pays Florence's core rate
                <b>+ ${amn_margin_per_rn:,.0f}/RN/mo</b> partner margin atop.
                Florence still collects <b>${core_per_rn_per_mo:,.0f}/RN/mo</b> —
                core rate protected.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─────────────────────────────────────────────────────────────────
    # 03 · SEND THIS TO THE CUSTOMER — proposal downloads
    # ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("03 · Send this to the customer")
    florence_headline(
        "Customer-ready proposal in one click.",
        subhead=f"Recommended Target calibration · {median_target_pct:.0%} offset · reproducible.",
    )
    safe_sys = selected_sys_name.replace(" ", "_").replace("/", "_").replace("'", "")[:48]
    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        if st.button(":material/slideshow:  Customer deck (.pptx)", key="reco_pptx",
                     type="primary", use_container_width=True):
            buf = build_deck_from_system_recs(
                sys_recs, selected_sys_name,
                target_offset_pct=float(sys_recs["target_target_offset_pct"].median()),
            )
            st.session_state[f"reco_pptx_{safe_sys}"] = buf.getvalue()
        if f"reco_pptx_{safe_sys}" in st.session_state:
            st.download_button(
                ":material/download: Download .pptx",
                st.session_state[f"reco_pptx_{safe_sys}"],
                file_name=f"{safe_sys}_customer_deck.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )
    with rc2:
        if st.button(":material/description:  Exec Summary (PDF)", key="reco_pdf",
                     use_container_width=True):
            with tempfile.TemporaryDirectory() as tmp:
                bundle_cal = Calibration(
                    target_offset_pct=float(sys_recs["target_target_offset_pct"].median()),
                    placeholder_msp_markup_pct=placeholder_msp_markup_pct,
                )
                h, p = build_system_exec_summary(selected_sys_id, Path(tmp), bundle_cal, CohortMix(eta=1.0))
                st.session_state[f"reco_pdf_{safe_sys}"] = p.read_bytes()
        if f"reco_pdf_{safe_sys}" in st.session_state:
            st.download_button(
                ":material/download: Download PDF",
                st.session_state[f"reco_pdf_{safe_sys}"],
                file_name=f"{safe_sys}_exec_summary.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    with rc3:
        if st.button(":material/table_view:  Excel workbook", key="reco_xlsx",
                     use_container_width=True):
            with tempfile.TemporaryDirectory() as tmp:
                bundle_cal = Calibration(
                    target_offset_pct=float(sys_recs["target_target_offset_pct"].median()),
                    placeholder_msp_markup_pct=placeholder_msp_markup_pct,
                )
                out = Path(tmp) / f"{safe_sys}_recommendation.xlsx"
                write_system_workbook(selected_sys_id, out, bundle_cal, CohortMix(eta=1.0))
                st.session_state[f"reco_xlsx_{safe_sys}"] = out.read_bytes()
        if f"reco_xlsx_{safe_sys}" in st.session_state:
            st.download_button(
                ":material/download: Download .xlsx",
                st.session_state[f"reco_xlsx_{safe_sys}"],
                file_name=f"{safe_sys}_recommendation.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with rc4:
        if st.button(":material/inventory_2:  Complete bundle (.zip)", key="reco_zip",
                     use_container_width=True):
            # Shared builder — identical deliverable to the tile quick-actions popup.
            data, fname = build_system_bundle_zip(selected_sys_id, placeholder_msp_markup_pct)
            st.session_state[f"reco_zip_{safe_sys}"] = (data, fname)
        if f"reco_zip_{safe_sys}" in st.session_state:
            _zbytes, _zname = st.session_state[f"reco_zip_{safe_sys}"]
            st.download_button(
                ":material/download: Download bundle.zip",
                _zbytes,
                file_name=_zname,
                mime="application/zip",
                use_container_width=True,
                disabled=not _zbytes,
            )

    # Client Deck (HTML) — the data-driven pitch deck for this system as ONE
    # self-contained, emailable file (client-deck/; FICA-disclosed proposal).
    if st.button(":material/web:  Client Deck (HTML)", key="reco_deck",
                 use_container_width=True):
        try:
            import client_deck_export as _cde
            _deck_html = _cde.export_deck_html(selected_sys_id)
        except Exception as _e:
            st.warning(f"Deck export failed: {_e}")
            _deck_html = None
        if _deck_html is None:
            st.caption("No client deck for this system yet (not in the deck universe).")
        else:
            st.session_state[f"reco_deck_{safe_sys}"] = _deck_html.encode("utf-8")
    if f"reco_deck_{safe_sys}" in st.session_state:
        st.download_button(
            ":material/download: Download Client Deck (.html)",
            st.session_state[f"reco_deck_{safe_sys}"],
            file_name=f"Florence - {selected_sys_name} - Client Deck.html",
            mime="text/html",
            use_container_width=True,
        )

    # ─────────────────────────────────────────────────────────────────
    # 03 · PER-FACILITY SAVINGS STORY
    # ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("04 · Per-facility detail")
    fac_left, fac_right = st.columns([3, 1])
    with fac_left:
        florence_headline(
            "What this means, facility by facility.",
            subhead=(
                "Each row leads with what the hospital saves. Expand any facility to see "
                "the three-tier negotiation band the rep can work with."
            ),
        )
    with fac_right:
        st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
        facility_view = st.radio(
            "Show",
            ["Top 10", f"All {n_facilities}"],
            horizontal=True,
            label_visibility="collapsed",
        )

    sys_recs_sorted = sys_recs.sort_values("target_term_net_savings_account", ascending=False)
    if facility_view == "Top 10":
        sys_recs_sorted = sys_recs_sorted.head(10)
    unit_label = "/hr" if use_hourly else "/RN/mo"

    def _fmt_fee(v: float) -> str:
        return f"${v:,.2f}" if use_hourly else f"${v:,.0f}"

    for i, (_, r) in enumerate(sys_recs_sorted.iterrows()):
        fac_savings = r["target_term_net_savings_account"]
        fac_fee = r["target_term_florence_fee_account"]
        t_fee = r["target_hourly_fee"] if use_hourly else r["target_monthly_fee"]

        with st.expander(
            f"{r['name']}  ·  {r['city']}, {r['state']}  ·  "
            f"{_fmt_big(fac_savings)} impact over 24 mo  ·  "
            f"Florence fee {_fmt_fee(t_fee)}{unit_label}",
            expanded=(i == 0),
        ):
            # Deck-style two-pane comparison
            fica_pct_of_fee = (
                r['target_fica_savings_per_rn_per_month']
                / max(r['target_monthly_fee'], 1) * 100
            )
            pane_l, pane_r = st.columns(2)
            with pane_l:
                st.markdown(
                    f"""
                    <div class="florence-card today" style="min-height:240px;">
                      <div class="card-label">The Agency Model Today</div>
                      <div class="card-headline" style="margin-top:8px;">
                        Contingent. Recycled. Premium-priced.
                      </div>
                      <div class="card-body" style="margin-top:14px;">
                        • Hospital pays <b>${r['signal_agency_premium']:.2f}/hour</b> agency premium over baseline RN wage<br/>
                        • <b>{r['signal_cl_intensity']*100:.0f}%</b> of nursing payroll currently runs through contract labor<br/>
                        • No continuity of unit, team, or panel<br/>
                        • Premium recurs every fiscal cycle
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with pane_r:
                st.markdown(
                    f"""
                    <div class="florence-card with-florence" style="min-height:240px;">
                      <div class="card-label">The Florence Pathway</div>
                      <div class="card-headline" style="margin-top:8px;">
                        Permanent. Aligned. Repeatable.
                      </div>
                      <div class="card-body" style="margin-top:14px;">
                        • <b>{r['rn_need']:.0f} full-time international RNs</b> placed under standard hiring &amp; onboarding<br/>
                        • Florence fee <b>{_fmt_rate(r['target_monthly_fee'])}</b> per RN, amortized over 24 months<br/>
                        • FICA exemption alone covers <b>{fica_pct_of_fee:.0f}%</b> of the Florence fee<br/>
                        • Net hospital savings: <b>{_fmt_rate(r['target_net_monthly_savings_per_rn'])}</b> per RN
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Closing pitch banner for this facility
            st.markdown(
                f"""
                <div class="florence-banner" style="margin-top:18px;">
                  <div class="banner-text">
                    24-month savings net of Florence fees &amp; FICA equivalence
                  </div>
                  <div style="display:flex; align-items:baseline; gap:14px;">
                    <div class="banner-value">{_fmt_big(fac_savings)}</div>
                    <div class="banner-suffix">{r['target_savings_ratio']:.1f}× return</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Negotiation band — rep-facing, secondary
            st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
            florence_eyebrow("Three-tier negotiation band · For the rep")
            t_col1, t_col2, t_col3 = st.columns(3)
            for col, prefix, icon, label in [
                (t_col1, "stretch",   "Stretch",   "Open high"),
                (t_col2, "target",    "Target",    "Land here"),
                (t_col3, "reference", "Reference", "Max customer pitch"),
            ]:
                fee_monthly = r[f"{prefix}_monthly_fee"]
                fee_hourly = r[f"{prefix}_hourly_fee"]
                fee_show = f"${fee_hourly:,.2f}/hr" if use_hourly else f"${fee_monthly:,.0f}/mo"

                savings_monthly = r[f"{prefix}_net_monthly_savings_per_rn"]
                savings_hourly = savings_monthly / 156
                savings_show = (
                    f"${savings_hourly:,.2f}/hr"
                    if use_hourly
                    else f"${savings_monthly:,.0f}/mo"
                )

                col.markdown(f"**{icon}** &nbsp;<span style='color:#475467;'>{label}</span>",
                             unsafe_allow_html=True)
                col.metric(
                    "Hospital saves",
                    savings_show,
                    f"{r[f'{prefix}_savings_ratio']:.1f}× return",
                )
                col.metric(
                    "Florence fee",
                    fee_show,
                    f"{r[f'{prefix}_target_offset_pct']:.0%} FICA-offset",
                )
                col.caption(
                    f"Deal-attractiveness: **{r[f'{prefix}_deal_score']*100:.0f}/100**  ·  "
                    f"24-mo: {_fmt_big(r[f'{prefix}_term_net_savings_account'])} saved "
                    f"on {_fmt_big(r[f'{prefix}_term_florence_fee_account'])} fee"
                )

            # Why this band
            with st.expander(":material/menu_book: Why this recommendation", expanded=False):
                st.markdown(r["rationale"])
                st.caption("**Signals informing the recommendation:**")
                sig_cols = st.columns(5)
                sig_cols[0].metric(
                    "Savings ratio", f"{r['target_savings_ratio']:.1f}×",
                    help=_tip("savings"),
                )
                sig_cols[1].metric(
                    "CL share", f"{r['signal_cl_intensity']*100:.1f}%",
                    help=_tip("contract_labor_intensity"),
                )
                sig_cols[2].metric(
                    "Agency premium", f"${r['signal_agency_premium']:,.0f}/hr",
                    help=_tip("agency_premium"),
                )
                sig_cols[3].metric(
                    "FICA offset", f"{r['signal_fica_offset_pct']*100:.0f}%",
                    help=_tip("fica_offset"),
                )
                sig_cols[4].metric(
                    "Data confidence", f"{r['signal_data_confidence']:.2f}",
                    help=(
                        "0–1 score combining HCRIS data completeness and "
                        "MSA wage availability. Low = honor the manual-review "
                        "flag; don't quote without admin sign-off."
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # 💼 SYSTEM-WIDE ECONOMICS (Florence-internal — collapsed at bottom)
    # ─────────────────────────────────────────────────────────────────
    st.divider()
    with st.expander(":material/business_center: System-wide totals & Florence internal economics", expanded=False):
        st.caption(
            "Aggregate across all facilities at the recommended Target tier — "
            "internal numbers for Florence sales ops, not for the customer-facing pitch."
        )
        h1, h2, h3, h4, h5 = st.columns(5)
        h1.metric(
            "Total monthly Florence revenue",
            f"${total_monthly_target/1e6:,.1f}M/mo",
            f"{_fmt_big(total_term_fee_target)} over 24 months",
            help=_tip("florence_fee"),
        )
        h2.metric(
            "Total financial impact",
            _fmt_big(total_term_savings_target),
            f"vs Florence fee {_fmt_big(total_term_fee_target)}",
            help=_tip("savings", value=f"{total_term_savings_target/1e6:,.0f}M"),
        )
        h3.metric(
            "Median Target fee",
            _fmt_rate(median_target_fee_monthly),
            f"FICA-offset {median_target_pct:.0%}",
            help=_tip("fica_offset"),
        )
        h4.metric(
            "Deal-attractiveness (median)",
            f"{sys_recs['target_deal_score'].median()*100:.0f}/100",
            f"rev-weighted {weighted_deal_score*100:.0f}/100",
            help=_tip("deal_score"),
        )
        h5.metric(
            "Impact : fee ratio",
            f"{total_term_savings_target/total_term_fee_target:.1f}×"
                if total_term_fee_target > 0 else "—",
            help=_tip("savings"),
        )

        st.markdown("**Negotiation band — system-wide monthly revenue**")
        band_col1, band_col2, band_col3 = st.columns(3)
        band_col1.metric(
            "Stretch",
            f"${total_monthly_stretch/1e6:,.1f}M/mo",
            f"median {_fmt_rate(sys_recs['stretch_monthly_fee'].median())}",
        )
        band_col2.metric(
            "Target",
            f"${total_monthly_target/1e6:,.1f}M/mo",
            f"median {_fmt_rate(sys_recs['target_monthly_fee'].median())}",
        )
        band_col3.metric(
            "Reference",
            f"${total_monthly_reference/1e6:,.1f}M/mo",
            f"median {_fmt_rate(sys_recs['reference_monthly_fee'].median())}",
        )

    with st.expander(":material/balance: Methodology & compliance disclosure", expanded=False):
        st.markdown(
            "**Pricing methodology:** Florence Workforce Restoration Economics v2 — "
            "FICA-offset target pricing. Per-facility Target offset percentages are "
            "calibrated using HCRIS contract-labor rates (CMS Form 2552-10 Worksheet S-3 "
            "line 01100), BLS OEWS MSA-level RN wages, and known system-level overlays "
            "(Kaiser distribution-partner markup, placeholder MSP fees for HCA / Sutter / Ascension / etc.)."
        )
        st.markdown(
            f"**Recommendation posture for {selected_sys_name}:** {posture} "
            f"(median Target offset {median_target_pct:.0%})"
        )
        st.info(REQUIRED_COMPLIANCE_SENTENCE, icon=":material/balance:")



# =====================================================================
# CONTACTS — import the book you already have / export the current one
# =====================================================================
if view == "contacts":
    florence_brand_strip("CONTACTS · INTERNAL")
    florence_headline("Contact book.",
                      "Import contacts you already have; export your current book.")
    import contacts as _ct_io
    _cE, _cI = st.columns(2)
    with _cE:
        st.markdown("#### Export")
        st.download_button(
            ":material/download: Download contacts.csv", _ct_io.export_overrides_csv(),
            file_name="florence_contacts.csv", mime="text/csv", use_container_width=True)
        st.caption(_ct_io.coverage_note())
    with _cI:
        st.markdown("#### Import")
        st.caption(
            "CSV columns (any subset): entity_type, entity_id, org_name (or system_name), "
            "contact_name, title, email, phone, address1, city, state, zip, notes. Rows "
            "without entity_id are matched to a system by name; blank cells never "
            "overwrite existing values.")
        _derive = st.checkbox("Also derive missing emails (name + system domain)", value=False)
        _up = st.file_uploader("Contacts CSV", type=["csv"], key="contacts_import")
        if _up is not None:
            try:
                _idf = pd.read_csv(_up, dtype=str).fillna("")
            except Exception as _e:
                st.error(f"Couldn't read CSV: {_e}")
                _idf = None
            if _idf is not None:
                st.dataframe(_idf.head(15), use_container_width=True, hide_index=True)
                if st.button("Import contacts", type="primary", key="contacts_do_import"):
                    _rep = st.session_state.get("current_user_email") or ""
                    _res = _ct_io.bulk_import(_idf, by=_rep, derive_emails=_derive)
                    _msg = f"Imported {_res['imported']} · skipped {_res['skipped']}"
                    if _derive:
                        _msg += f" · derived {_res['derived']} emails"
                    st.success(_msg)
                    if _res["skipped"]:
                        st.caption("Skipped rows had no entity_id and no org/system name we "
                                   "could match to a known system.")

    st.divider()
    st.markdown("#### Activity log")
    import activity as _act_io
    _aq = st.text_input("Search calls / notes / activity", key="activity_search",
                        placeholder="e.g. CNO, voicemail, callback")
    _adf = _act_io.search(_aq)
    if _adf.empty:
        st.caption("No activity logged yet. Log calls + notes from any system's popup.")
    else:
        st.dataframe(_adf[["ts", "org_name", "kind", "detail", "by"]],
                     use_container_width=True, hide_index=True)


# =====================================================================
# CALL CENTER — outbound queue over the outpatient phone universe
# =====================================================================
if view == "call_center":
    florence_brand_strip("CALL CENTER · INTERNAL")
    florence_headline("Outbound call queue.",
                      "Work the outpatient phone list — claim, dial, log the call, set the callback.")
    import callcenter as _ccq, reminders as _rem_cc
    _agent = (st.session_state.get("current_user_email") or "").strip()
    if not _agent:
        _agent = st.text_input("Your name or extension (claims + call logs attribute to you)",
                               key="cc_agent_name").strip()
    if not _agent:
        st.info("Enter your name/extension to start working the queue.", icon=":material/badge:")
    elif _ccq._facilities().empty:
        st.warning("No facility contact file found (data/facility_contacts.parquet).")
    else:
        st.text_input("Your phone for one-click RingOut (optional)", key="rc_agent_number",
                      placeholder="+1…  — only used when RingCentral is connected")
        _fc1, _fc2, _fc3 = st.columns([1.4, 1.1, 1.5])
        _states = _fc1.multiselect("States", _ccq.states_with_phones(), key="cc_states")
        _typeopts = sorted(set(_ccq._facilities().get("facility_type", pd.Series(dtype=str))
                               .dropna().astype(str)) - {""})
        _types = _fc2.multiselect("Type", _typeopts, key="cc_types")
        _chainq = _fc3.text_input("Chain / name contains", key="cc_chain")
        _q = _ccq.queue(states=_states or None, facility_types=_types or None,
                        chain_query=_chainq, limit=300)
        _snoozed = {str(a["entity_id"]) for a in _rem_cc.active() if a.get("entity_type") == "facility"}
        _claims = _ccq.active_claims()
        if not _q.empty:
            _q = _q[~_q["ccn"].astype(str).isin(_snoozed)]
        st.caption(f"{len(_q):,} to call"
                   + (f" · {len(_snoozed)} on scheduled callback" if _snoozed else "")
                   + (f" · {len(_claims)} claimed now" if _claims else ""))
        if st.session_state.get("cc_flash"):
            st.success("Logged — " + st.session_state.pop("cc_flash"))
        for _, _row in _q.head(40).iterrows():
            _ccn = str(_row["ccn"])
            _by = _claims.get(_ccn, "")
            _k1, _k2, _k3 = st.columns([3.4, 2, 1.1])
            _chain = f" · {_row.get('chain_name')}" if str(_row.get("chain_name") or "").strip() else ""
            _k1.markdown(
                f"**{_row['name']}**<br><span style='color:var(--f-muted);font-size:.8rem;'>"
                f"{_row.get('city','')}, {_row.get('state','')} · {_row.get('facility_type','')}{_chain}</span>",
                unsafe_allow_html=True)
            _k2.markdown(f"<span style='font-family:var(--f-mono);font-size:.85rem;'>"
                         f"{_row['facility_phone']}</span>", unsafe_allow_html=True)
            with _k3:
                if _by and _by != _agent:
                    st.caption(":material/lock: " + _by)
                elif st.button("Call →", key=f"cc_work_{_ccn}", use_container_width=True):
                    open_call_workspace(_ccn, _agent)
        if _snoozed:
            with st.expander(f"Scheduled callbacks ({len(_snoozed)})"):
                for _a in sorted(_rem_cc.active(), key=lambda x: x.get("snooze_until", "")):
                    if _a.get("entity_type") == "facility":
                        st.markdown(f"<div style='font-size:.82rem;'>{_a.get('snooze_until','')} · "
                                    f"{_a.get('entity_id','')} — {_a.get('note','')}</div>",
                                    unsafe_allow_html=True)


# =====================================================================
# TODAY — the daily worklist (follow-ups due + top untouched targets)
# =====================================================================
if view == "today":
    florence_brand_strip("TODAY · INTERNAL")
    florence_headline("Today's worklist.",
                      "Follow-ups due now, then your highest-value untouched targets.")
    import sales_intel as _si_today
    import contacts as _ct_today
    _agg = _all_systems_agg(sysov.overrides_mtime())
    if _agg.empty:
        st.info("No systems available yet.", icon=":material/info:")
    else:
        _recs_t = _agg.to_dict("records")
        import ownership as _own_today
        _rep_today = st.session_state.get("current_user_email") or ""
        if _rep_today and st.checkbox("My book only", value=False, key="today_mybook"):
            _book_t = _own_today.book_of(_rep_today)
            _recs_t = [r for r in _recs_t if str(r.get("health_system_id")) in _book_t]
        _by_id = {str(r["health_system_id"]): r for r in _recs_t}
        _touched = _si_today.touched_system_ids()

        # 1) Follow-ups due — active sequences whose next touch is ready.
        _due = []
        for _sid in _touched:
            if _sid not in _by_id:
                continue
            _cad = _si_today.cadence_next("system", _sid)
            if _cad.get("ready") and not _cad.get("done"):
                _due.append((_sid, _cad))
        import reminders as _rem_today
        _due = [(s, c) for (s, c) in _due if not _rem_today.is_snoozed("system", s)]
        _due.sort(key=lambda t: (t[1].get("due_in_days")
                                 if t[1].get("due_in_days") is not None else 0))
        st.markdown(f"#### Follow-ups due ({len(_due)})")
        if not _due:
            st.caption("Nothing due — you're caught up on active sequences.")
        for _sid, _cad in _due:
            _r = _by_id[_sid]
            _dd = _cad.get("due_in_days")
            _due_txt = "overdue" if (_dd is not None and _dd < 0) else "due now"
            _t1, _t2, _t3 = st.columns([3.2, 2.3, 1.0])
            _t1.markdown(
                f"**{_r['health_system']}**<br><span style='color:var(--f-muted);"
                f"font-size:.8rem;'>{_money(_r['term_savings_target'])} impact · "
                f"{int(_r['rn_need']):,} RN</span>", unsafe_allow_html=True)
            _t2.markdown(f"<div style='font-size:.82rem;margin-top:4px;'><b>{_due_txt}</b> · "
                         f"{_cad['label']}</div>", unsafe_allow_html=True)
            with _t3:
                if st.button("Open →", key=f"today_due_{_sid}", use_container_width=True):
                    open_system_quick_actions(_sid, placeholder_msp_markup_pct)
        st.divider()

        # 2) Start these — top-priority untouched.
        _ranked_t = _si_today.rank_systems(_recs_t, _ct_today.get_contact, limit=50)
        _starts = [r for r in _ranked_t if r["system_id"] not in _touched
                   and not _rem_today.is_snoozed("system", r["system_id"])][:10]
        _snz_n = len(_rem_today.active())
        if _snz_n:
            st.caption(f":material/snooze: {_snz_n} account(s) snoozed — they'll resurface on their date.")
        st.markdown("#### Start these — top untouched targets")
        for _pr in _starts:
            _s1, _s2, _s3 = st.columns([3.2, 2.3, 1.0])
            _s1.markdown(
                f"**{_pr['name']}**<br><span style='color:var(--f-muted);font-size:.8rem;'>"
                f"{_money(_pr['term_savings'])} impact · {_pr['rn_need']:,} RN</span>",
                unsafe_allow_html=True)
            _rc = {"Reachable": "#067F7B", "Partial": "#B7791F",
                   "No contact": "#B33A3A"}.get(_pr["reach_label"], "#475467")
            _s2.markdown(
                f"<div style='margin-top:6px;'><span style='font-size:.72rem;font-weight:600;"
                f"padding:2px 8px;border-radius:999px;background:{_rc}1A;color:{_rc};'>"
                f"{_pr['reach_label']} {_pr['reach_pct']}%</span></div>", unsafe_allow_html=True)
            with _s3:
                if st.button("Open →", key=f"today_start_{_pr['system_id']}",
                             use_container_width=True):
                    open_system_quick_actions(_pr["system_id"], placeholder_msp_markup_pct)
        # Map of your top untouched targets (plotted at state centroids).
        import geo as _geo
        _pts = []
        for _pr in _starts:
            _cen = _geo.centroid(_by_id.get(_pr["system_id"], {}).get("primary_state", ""))
            if _cen:
                _pts.append({"name": _pr["name"], "lat": _cen[0], "lon": _cen[1],
                             "sav": _pr["term_savings"],
                             "state": _by_id[_pr["system_id"]].get("primary_state", "")})
        if _pts:
            with st.expander("Map of your top targets"):
                import plotly.graph_objects as _go_t
                _md = pd.DataFrame(_pts)
                _md["_n"] = _md.groupby("state").cumcount()
                _md["lat"] = _md["lat"] + (_md["_n"] % 5) * 0.35
                _md["lon"] = _md["lon"] + (_md["_n"] // 5) * 0.45
                _mx = float(_md["sav"].max() or 1)
                _fig_t = _go_t.Figure(_go_t.Scattergeo(
                    lon=_md["lon"], lat=_md["lat"],
                    text=_md["name"] + " · " + _md["sav"].map(_money),
                    mode="markers",
                    marker=dict(size=(_md["sav"] / _mx * 26 + 8), color="#0ABAB5",
                                line=dict(width=0.5, color="#067F7B"), opacity=0.82),
                ))
                _fig_t.update_layout(geo=dict(scope="usa", bgcolor="rgba(0,0,0,0)"),
                                     margin=dict(l=0, r=0, t=0, b=0), height=360)
                st.plotly_chart(_fig_t, use_container_width=True)

        st.caption(
            "Follow-ups come from logged touches + the cadence; untouched targets are "
            "ranked by savings × reachability. Open any to act, then log the outcome."
        )


# =====================================================================
# FUNNEL — outreach → engaged → activated → hired
# =====================================================================
if view == "funnel":
    florence_brand_strip("FUNNEL · INTERNAL")
    florence_headline("Outreach to hires.",
                      "Every account from first touch to closed-won — overall and by rep.")
    import funnel as _fn
    _counts = _fn.funnel_counts()
    _cols = st.columns(len(_counts) + 1)
    for (lbl, val), c in zip(_counts.items(), _cols):
        c.metric(lbl, f"{val:,}")
    _cols[-1].metric("Open deals", f"{_fn.open_deals():,}")
    if sum(_counts.values()) == 0:
        st.info(
            "No outreach logged yet. Draft mail, capture replies, and log "
            "activations and the funnel fills in here.",
            icon=":material/info:",
        )
    else:
        import plotly.graph_objects as _go
        _labels, _vals = list(_counts.keys()), list(_counts.values())
        _fig = _go.Figure(_go.Funnel(
            y=_labels, x=_vals, textinfo="value+percent initial",
            marker={"color": ["#0ABAB5", "#15ABA8", "#067F7B", "#7340C4", "#5B2DA8"][:len(_labels)]},
        ))
        _fig.update_layout(margin=dict(l=8, r=8, t=8, b=8), height=380,
                           font=dict(family="Inter, sans-serif"))
        st.plotly_chart(_fig, use_container_width=True)
    st.markdown("#### By rep")
    _rep = _fn.by_rep()
    if _rep.empty:
        st.caption("No rep activity yet.")
    else:
        st.dataframe(_rep, use_container_width=True, hide_index=True)

    st.markdown("#### This week")
    _wd_days = st.radio("Window", [7, 14, 30], format_func=lambda d: f"last {d} days",
                        horizontal=True, key="wd_window", label_visibility="collapsed")
    _wd = _fn.weekly_digest(_wd_days)
    _me = (st.session_state.get("current_user_email") or "").lower()
    if _me and not _wd.empty and (_wd["rep"] == _me).any():
        _r = _wd[_wd["rep"] == _me].iloc[0]
        _mc = st.columns(4)
        _mc[0].metric("My outreach", int(_r["outreach"]))
        _mc[1].metric("My replies", int(_r["replies"]))
        _mc[2].metric("My calls/notes", int(_r["calls_notes"]))
        _mc[3].metric("My hires", int(_r["hires"]))
    if _wd.empty:
        st.caption("No activity in this window yet.")
    else:
        st.dataframe(_wd, use_container_width=True, hide_index=True)
    st.caption(
        "Sources: mail_log (outreach + replies), activity_log (calls/notes), "
        "activations.csv (sign-ups), sales_pipeline (deals + closed-won)."
    )


# =====================================================================
# PLAYBOOK — sales onboarding + source-of-truth for the pitch
# =====================================================================
if view == "playbook":
    import playbook as _playbook
    _playbook.streamlit_render(
        st,
        current_role=current_role,
        current_user_email=(current_user or {}).get("email", "") if current_user else "",
    )


# =====================================================================
# ONBOARDING — 5-day guided sales rep onboarding track
# =====================================================================
if view == "onboarding":
    import onboarding as _onboarding
    _rep_email_onb = (
        (current_user or {}).get("email", "")
        if current_user else "demo@florence.dev"
    )
    # Admins + ops see the team view; reps see their own track
    if current_role in ("admin", "ops"):
        leader_col, rep_col = st.tabs(["Team progress", "My track"])
        with leader_col:
            _onboarding.streamlit_leader_view(st)
        with rep_col:
            _onboarding.streamlit_rep_view(st, rep_email=_rep_email_onb)
    else:
        _onboarding.streamlit_rep_view(st, rep_email=_rep_email_onb)


# =====================================================================
# PIPELINE — workbench: per-rep deals, suggested next moves, stage tracking
# =====================================================================
if view == "pipeline":
    import workbench as _workbench_pipeline
    florence_eyebrow("Pipeline")
    florence_headline(
        "Your active deals. One next move per deal.",
        subhead="Stage, notes, and the next-best-move — auto-suggested.",
    )

    _pipe_rep_email = (
        (current_user or {}).get("email", "") if current_user else ""
    ) or "demo@florence.dev"
    _pipe_active_deal = st.session_state.get("workbench_active_deal")

    if not _pipe_active_deal:
        # Pipeline list view
        _workbench_pipeline.streamlit_pipeline_view(
            st, rep_email=_pipe_rep_email,
        )

        # Quoted-vs-closed calibration (fed by close-out capture)
        _workbench_pipeline.streamlit_calibration_section(st)

        st.markdown("---")
        # New-deal form — derive system list from cached_universe (works
        # for any care setting). Apply RBAC territory filter when auth is on.
        try:
            _u_for_pipe = cached_universe(sysov.overrides_mtime())
            _systems_for_pipe = (
                _u_for_pipe[["health_system_id", "health_system", "state"]]
                .drop_duplicates("health_system_id")
            )
            if _AUTH_REQUIRED:
                import rbac as _rbac_pipe2
                _systems_for_pipe = _rbac_pipe2.filter_by_territory(
                    _systems_for_pipe,
                    st.session_state.get("current_territory", "ALL"),
                    state_col="state",
                )
        except Exception:
            _systems_for_pipe = pd.DataFrame()
        _workbench_pipeline.streamlit_new_deal_form(
            st, rep_email=_pipe_rep_email,
            systems_df=_systems_for_pipe,
        )
    else:
        # Deal detail view
        _workbench_pipeline.streamlit_deal_detail(
            st, deal_id=_pipe_active_deal,
            generate_proposal_callback=lambda d: st.info(
                "To generate the proposal bundle for this deal, open the "
                "**Inpatient** or **Outpatient** tab, pick this system, "
                "and the existing Excel + PDF generators will run as before. "
                "Paste the resulting filename below to save it on the deal.",
                icon=":material/lightbulb:",
            ),
        )


# =====================================================================
# GROWTH AUTOMATION — AI SDR engine: employer demand + university supply
# =====================================================================
if view == "growth":
    import growth_automation as _ga
    florence_eyebrow("Growth automation · AI SDR engine")
    florence_headline(
        "Acquire both sides of the network.",
        subhead="AI-personalized outreach to long-tail employers and global "
                "nursing programs — discovered, generated, and tracked.",
    )

    @st.cache_data
    def _ga_load_priced() -> pd.DataFrame:
        path = DATA_DIR / "non_hospital_priced.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    _ga_priced = _ga_load_priced()
    _ga_territory_states = None
    if _AUTH_REQUIRED and not _ga_priced.empty:
        try:
            import rbac as _rbac_ga
            _terr = st.session_state.get("current_territory", "ALL")
            _ga_priced = _rbac_ga.filter_by_territory(
                _ga_priced, _terr, state_col="state"
            )
            if _terr and _terr != "ALL":
                _ga_territory_states = sorted(
                    _ga_priced["state"].dropna().unique().tolist()
                )
        except Exception:
            pass

    _ga_rep_email = (
        (current_user or {}).get("email", "") if current_user else ""
    ) or "demo@florence.dev"

    _ga.streamlit_growth_view(
        st, priced_df=_ga_priced, rep_email=_ga_rep_email,
        territory_states=_ga_territory_states,
    )


# =====================================================================
# MARKET INTELLIGENCE — live BLS surveillance + interactive Plotly charts
# =====================================================================
if view == "market_intel":
    florence_eyebrow("Market intelligence")
    florence_headline(
        "What changed in the U.S. RN labor market.",
        subhead="Live BLS · JOLTS · CES · OEWS.",
    )

    # ─── Natural-language query box (AI Q&A if configured, else rule-based) ─
    try:
        from ai_qa.llm_client import is_available as _ai_available
        ai_ready = _ai_available()
    except Exception:
        ai_ready = False
    ai_status = (
        ":material/auto_awesome: AI Q&A active"
        if ai_ready
        else ":material/info: Rule-based parser (set ANTHROPIC_API_KEY for AI Q&A)"
    )
    st.caption(ai_status)
    nl_query = st.text_input(
        "Ask a market question",
        placeholder=(
            "Try: 'Show me California RN wages' · 'Compare CA TX FL' · "
            "'Top 10 states by wage' · 'What's the labor market headline?'"
        ),
        key="intel_nl_query",
    )

    # Load surveillance data
    try:
        from surveillance.briefing import BRIEFINGS_DIR
        latest_briefings = sorted(BRIEFINGS_DIR.glob("*.json"))
        if not latest_briefings:
            st.info(
                "No briefing yet. Run `python -m surveillance.briefing` from the project root.",
                icon=":material/info:",
            )
            st.stop()
        import json as _json
        with open(latest_briefings[-1]) as f:
            briefing = _json.load(f)
    except Exception as e:
        st.error(f"Surveillance load error: {e}")
        st.stop()

    # Load state wages
    state_bench = pd.read_csv(DATA_DIR / "state_benchmarks.csv")
    state_bench = state_bench[~state_bench["state"].isin(["GU","PR","VI","MP","AS"])]

    # Load JOLTS / CES history
    try:
        jolts_hist = pd.read_csv(DATA_DIR / "surveillance" / "jolts_healthcare" / "long_history.csv")
        ces_hist = pd.read_csv(DATA_DIR / "surveillance" / "ces_rn" / "long_history.csv")
    except Exception:
        jolts_hist = pd.DataFrame()
        ces_hist = pd.DataFrame()

    # ─── Process natural-language query (AI first, then rule-based fallback) ─
    query_result = None
    if nl_query.strip():
        # 1) Try AI Q&A if available
        if ai_ready:
            try:
                from ai_qa.router import ask as ai_ask
                ai_result = ai_ask(nl_query)
                if ai_result.get("kind") == "table" and hasattr(ai_result.get("data"), "columns"):
                    query_result = ("table", ai_result["data"])
                elif ai_result.get("kind") == "text":
                    query_result = ("text", str(ai_result.get("data", "")))
                if ai_result.get("narrative"):
                    st.caption(ai_result["narrative"])
            except Exception as e:
                st.warning(f"AI Q&A error: {e}; falling back to rules.")

        # 2) Rule-based fallback (and primary when no API key)
        if query_result is None:
            q = nl_query.lower().strip()
            import re as _re
            state_codes_in_q = _re.findall(r"\b([A-Z]{2})\b", nl_query.upper())
            valid_states = [s for s in state_codes_in_q if s in set(state_bench["state"])]
            if "headline" in q or "summary" in q or "what changed" in q:
                query_result = ("text", briefing["headline"])
            elif "top" in q and "wage" in q:
                n_match = _re.search(r"top\s+(\d+)", q)
                n = int(n_match.group(1)) if n_match else 10
                top = state_bench.sort_values("rn_wage", ascending=False).head(n)
                query_result = ("table", top[["state", "rn_wage"]].rename(
                    columns={"state": "State", "rn_wage": "RN hourly wage"}))
            elif "compare" in q and len(valid_states) >= 2:
                cmp = state_bench[state_bench["state"].isin(valid_states)]
                query_result = ("table", cmp[["state", "rn_wage"]].rename(
                    columns={"state": "State", "rn_wage": "RN hourly wage"}))
            elif len(valid_states) == 1:
                st_code = valid_states[0]
                row = state_bench[state_bench["state"] == st_code].iloc[0]
                rank = (state_bench["rn_wage"] > row["rn_wage"]).sum() + 1
                query_result = ("text",
                    f"**{st_code}** prevailing RN wage: **${row['rn_wage']:,.2f}/hour** "
                    f"— ranked #{rank} of {len(state_bench)} states. "
                    f"At ${row['rn_wage']:,.2f}/hr × 156 = ${row['rn_wage']*156:,.0f}/mo wage, "
                    f"a Florence placement here delivers strong unit economics for the customer."
                )
            else:
                query_result = ("text",
                    "Couldn't parse that query with rules. "
                    "Set ANTHROPIC_API_KEY to enable AI Q&A for free-form queries, or try one of "
                    "the suggested patterns in the placeholder.")

        if query_result is not None:
            kind, payload = query_result
            st.markdown(
                f"""
                <div style="background:#F4F6F8; border-left:4px solid #0ABAB5;
                            padding:14px 22px; border-radius:0 8px 8px 0; margin: 18px 0;">
                  <div style="font-family:Inter,sans-serif; font-size:0.72rem;
                              font-weight:600; letter-spacing:0.18em; text-transform:uppercase;
                              color:#067F7B; margin-bottom:6px;">Query result</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if kind == "text":
                st.markdown(payload)
            else:  # table
                st.dataframe(payload, use_container_width=True, hide_index=True)

    # ─── Headline banner ────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="florence-banner" style="margin: 18px 0;">
          <div class="banner-text">
            {briefing["headline"]}
          </div>
          <div style="font-family:Inter,sans-serif; font-size:0.78rem;
                      font-weight:600; letter-spacing:0.18em;
                      text-transform:uppercase; color:rgba(255,255,255,0.7);">
            AS OF {briefing["as_of"]}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── State-level RN wage choropleth (Plotly) ─────────────────────
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("State-level RN wages — interactive map")
    try:
        from viz.charts import state_choropleth
        state_dict = dict(zip(state_bench["state"], state_bench["rn_wage"]))
        fig = state_choropleth(
            state_dict,
            title="Prevailing RN hourly wage by state (BLS OEWS, May 2024)",
            colorbar_title="$/hr",
            value_format="$,.2f",
            height=480,
        )
        st.plotly_chart(fig, use_container_width=True)
        # Education caption
        st.caption(
            "California, Hawaii, and Oregon lead in RN wages — driven by union density, "
            "cost of living, and state nurse-staffing ratio laws. The bottom quartile (AL, MS, AR, "
            "SD) reflects rural labor markets and lower union penetration. Florence flat-fee "
            "economics scale uniformly — but customer ROI improves in higher-wage markets where "
            "agency premiums are highest."
        )
    except Exception as e:
        st.warning(f"Map render error: {e}")

    # ─── JOLTS time series ───────────────────────────────────────────
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("Healthcare labor market — JOLTS trends")
    if not jolts_hist.empty:
        try:
            from viz.charts import time_series
            # Filter to last 24 months of data
            jolts_hist["period_num"] = jolts_hist["period"].str.replace("M", "").astype(int)
            jolts_hist["yearmonth"] = (
                jolts_hist["year"].astype(str) + "-" +
                jolts_hist["period_num"].astype(str).str.zfill(2)
            )
            jolts_filtered = jolts_hist[
                jolts_hist["metric"].isin(["job_openings_level", "hires_level",
                                           "quits_level", "layoffs_level"])
            ].dropna(subset=["value"])
            # Pretty metric labels
            label_map = {
                "job_openings_level": "Job openings",
                "hires_level": "Hires",
                "quits_level": "Quits",
                "layoffs_level": "Layoffs",
            }
            jolts_filtered["metric"] = jolts_filtered["metric"].map(label_map)
            jolts_filtered = jolts_filtered.sort_values(["metric", "year", "period_num"])
            fig_ts = time_series(
                jolts_filtered.tail(96),  # last 24mo × 4 metrics = 96 rows
                x_col="yearmonth", y_col="value", color_col="metric",
                title="Healthcare sector openings / hires / quits / layoffs (thousands)",
                y_label="Thousands of workers", height=400,
            )
            st.plotly_chart(fig_ts, use_container_width=True)
            st.caption(
                "The JOLTS series tracks monthly flows: **openings** = unmet demand, "
                "**hires** = actual filling, **quits** = worker leverage (people leaving "
                "voluntarily), **layoffs** = employer cost-pressure. When openings > hires "
                "for sustained periods, wages rise. When quits stay elevated, operators face "
                "retention costs. Florence's permanent-placement value increases in both "
                "scenarios."
            )
        except Exception as e:
            st.warning(f"Time series error: {e}")

    # ─── Insight stat cards (preserved from before) ──────────────────
    by_cat: dict[str, list] = {}
    for ins in briefing["insights"]:
        by_cat.setdefault(ins["category"], []).append(ins)
    for cat, items in by_cat.items():
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        florence_eyebrow(cat)
        n_cols = min(len(items), 4)
        cols = st.columns(n_cols)
        for i, ins in enumerate(items):
            col = cols[i % n_cols]
            arrow = "↑" if ins["delta_pct"] >= 0 else "↓"
            severity_color = "#0ABAB5" if ins["severity"] == "high" else "#475467"
            col.markdown(
                f"""
                <div style="background:#F4F6F8; border:1px solid #E5E8EE;
                            border-radius:10px; padding:14px 18px; margin-bottom:14px;
                            height:160px;">
                  <div style="font-family:Inter,sans-serif; font-size:0.72rem;
                              font-weight:600; letter-spacing:0.12em; text-transform:uppercase;
                              color:#475467;">{ins['metric'].upper()}</div>
                  <div style="font-family:Playfair Display,serif; font-size:1.65rem;
                              font-weight:600; color:#101828; margin-top:6px;">
                    {ins['current']:,.1f}
                  </div>
                  <div style="font-family:Inter,sans-serif; font-size:0.85rem;
                              color:{severity_color}; font-weight:600;">
                    {arrow} {ins['delta_pct']:+.1f}%
                    <span style="color:#475467; font-weight:400;">
                      from {ins['prior_period']}
                    </span>
                  </div>
                  <div style="font-family:Inter,sans-serif; font-size:0.78rem;
                              color:#475467; line-height:1.4; margin-top:8px;">
                    {ins['interpretation']}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ─── Top + bottom states by wage (horizontal bars) ───────────────
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("State wage distribution")
    wc1, wc2 = st.columns(2)
    try:
        from viz.charts import bar_horizontal
        top10 = state_bench.nlargest(10, "rn_wage")[["state", "rn_wage"]]
        bot10 = state_bench.nsmallest(10, "rn_wage")[["state", "rn_wage"]]
        with wc1:
            fig_top = bar_horizontal(
                top10, label_col="state", value_col="rn_wage",
                title="Top 10 states by RN hourly wage",
                x_label="$/hour", height=380,
            )
            st.plotly_chart(fig_top, use_container_width=True)
        with wc2:
            fig_bot = bar_horizontal(
                bot10, label_col="state", value_col="rn_wage",
                title="Bottom 10 states by RN hourly wage",
                x_label="$/hour", height=380,
            )
            st.plotly_chart(fig_bot, use_container_width=True)
        st.caption(
            "**Florence opportunity:** highest-wage states (CA, HI, OR) face the steepest "
            "agency premiums — the deepest pool for Florence's hospital pricing power. "
            "Lowest-wage states (AL, MS, AR, SD) have the strongest capacity-expansion "
            "story for non-hospital settings, where flat-fee economics scale uniformly."
        )
    except Exception as e:
        st.warning(f"Bar chart error: {e}")

    # ─── Surveillance feed status ────────────────────────────────────
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("Surveillance feeds")
    feed_cols = st.columns(len(briefing["feeds_status"]))
    for col, (feed, status) in zip(feed_cols, briefing["feeds_status"].items()):
        marker = ":material/check_circle:" if status == "current" else ":material/warning:"
        col.markdown(f"**{feed}**  \n{marker} {status}")

    with st.expander(":material/refresh: Manual refresh & history", expanded=False):
        st.code(
            "python -m surveillance.jolts_healthcare\n"
            "python -m surveillance.ces_rn\n"
            "python -m surveillance.oews_state_rn   # state RN wages (API ID refinement pending)\n"
            "python -m surveillance.briefing",
            language="bash",
        )
        st.caption(
            "Schedule monthly via cron — `5 0 5 * *` runs at 00:05 on the 5th of each "
            "month (after BLS publishes JOLTS monthly release on the 1st). "
            "Brings each feed to current and regenerates the briefing."
        )
        if len(latest_briefings) > 1:
            st.markdown("**Past briefings:**")
            for b in latest_briefings[-10:]:
                st.caption(f"- {b.stem}")


# =====================================================================
# FORECASTING — 12-24mo projection of JOLTS healthcare labor signals
# =====================================================================
if view == "forecast":
    florence_eyebrow("Forecasting")
    florence_headline(
        "Where the RN labor market is going.",
        subhead="SARIMA projection · 6–24 months forward · 80% confidence band.",
    )

    # ─── Controls ─────────────────────────────────────────────────────
    col_h, col_r = st.columns([3, 2])
    with col_h:
        horizon = st.slider(
            "Forecast horizon (months)",
            min_value=6, max_value=24, value=12, step=1,
            help="How far forward to project. 12mo is the default for annual planning.",
        )
    with col_r:
        if st.button(":material/refresh: Re-run forecast",
                     type="primary", use_container_width=True):
            st.cache_data.clear()

    @st.cache_data(show_spinner="Fitting SARIMA models…")
    def _run_forecasts(periods: int) -> dict:
        from surveillance.forecast import forecast_jolts_metric
        out = {}
        for metric in ["job_openings_level", "hires_level",
                       "quits_level", "layoffs_level"]:
            out[metric] = forecast_jolts_metric(metric, periods=periods)
        return out

    @st.cache_data
    def _load_jolts_hist() -> pd.DataFrame:
        path = DATA_DIR / "surveillance" / "jolts_healthcare" / "long_history.csv"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        df["period_num"] = df["period"].astype(str).str.replace("M", "")
        df["period_num"] = pd.to_numeric(df["period_num"], errors="coerce")
        df = df.dropna(subset=["period_num"])
        df["date"] = pd.to_datetime(
            df["year"].astype(int).astype(str) + "-" +
            df["period_num"].astype(int).astype(str).str.zfill(2) + "-01",
            errors="coerce",
        )
        return df.sort_values("date")

    hist = _load_jolts_hist()
    if hist.empty:
        st.info(
            "No JOLTS history yet. Run `python -m surveillance.jolts_healthcare` "
            "to seed the forecasting layer.",
            icon=":material/info:",
        )
        st.stop()

    fc_results = _run_forecasts(horizon)

    # ─── Narrative headline ──────────────────────────────────────────
    op = fc_results.get("job_openings_level", {})
    qt = fc_results.get("quits_level", {})
    if "forecast_mean" in op and "forecast_mean" in qt:
        cur_op = op["last_observed"]
        fut_op = op["forecast_mean"][-1]
        cur_qt = qt["last_observed"]
        fut_qt = qt["forecast_mean"][-1]
        cur_ratio = cur_op / max(cur_qt, 1)
        fut_ratio = fut_op / max(fut_qt, 1)
        tightening = fut_ratio > cur_ratio
        direction = "TIGHTENING" if tightening else "SOFTENING"
        pricing_dir = "expanding" if tightening else "normalizing"

        st.markdown(
            f"""
            <div style="background: {'#0ABAB5' if tightening else '#F4A261'}1A;
                        border-left: 4px solid {'#0ABAB5' if tightening else '#F4A261'};
                        padding: 16px 20px; border-radius: 8px; margin: 12px 0;">
              <div style="font-family: Inter, sans-serif; font-size: 12px;
                          letter-spacing: 0.08em; color: #5A6B82; text-transform: uppercase;">
                Forward-looking headline
              </div>
              <div style="font-family: Playfair Display, Georgia, serif; font-size: 24px;
                          color: #101828; font-weight: 500; margin: 6px 0 4px 0;">
                Healthcare labor market projected to be <b>{direction}</b> over the next {horizon} months.
              </div>
              <div style="font-family: Inter, sans-serif; font-size: 14px; color: #2C3E50;">
                Openings:quits ratio · <b>{cur_ratio:.2f}</b> today &nbsp;→&nbsp; <b>{fut_ratio:.2f}</b> in {horizon}mo.
                Florence pricing power {pricing_dir} over the period.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─── Metric summary cards ────────────────────────────────────────
    metric_labels = {
        "job_openings_level": "Healthcare job openings",
        "hires_level": "Hires",
        "quits_level": "Quits",
        "layoffs_level": "Layoffs",
    }
    cols = st.columns(4)
    for col, (metric, label) in zip(cols, metric_labels.items()):
        r = fc_results.get(metric, {})
        with col:
            if "error" in r:
                st.metric(label, "—", help=r["error"])
                continue
            cur = r["last_observed"]
            fut = r["forecast_mean"][-1]
            pct = (fut - cur) / max(cur, 1) * 100
            st.metric(
                label,
                f"{fut:,.0f}",
                delta=f"{pct:+.1f}% vs today",
                delta_color="normal" if metric != "layoffs_level" else "inverse",
            )
            st.caption(f"Today: {cur:,.0f}")

    # ─── Forecast charts ─────────────────────────────────────────────
    st.markdown("### Projection charts")
    st.caption(
        "Solid line = observed history. Dashed line = SARIMA forecast. "
        "Shaded band = 80% confidence interval."
    )

    import plotly.graph_objects as _go
    from viz import (FLORENCE_TEAL as _FL_TEAL,
                     FLORENCE_NAVY as _FL_NAVY,
                     FLORENCE_MUTED as _FL_MUTED)

    def _make_forecast_fig(metric: str, label: str) -> _go.Figure:
        m_hist = hist[hist["metric"] == metric].copy()
        r = fc_results.get(metric, {})
        fig = _go.Figure()
        if not m_hist.empty:
            fig.add_trace(_go.Scatter(
                x=m_hist["date"], y=m_hist["value"],
                mode="lines", name="Observed",
                line=dict(color=_FL_NAVY, width=2),
                hovertemplate="%{x|%b %Y}<br>%{y:,.0f}<extra></extra>",
            ))
        if "forecast_mean" in r and not m_hist.empty:
            last_dt = m_hist["date"].max()
            future_dates = pd.date_range(
                start=last_dt + pd.DateOffset(months=1),
                periods=len(r["forecast_mean"]), freq="MS",
            )
            fig.add_trace(_go.Scatter(
                x=future_dates, y=r["ci_upper"],
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ))
            fig.add_trace(_go.Scatter(
                x=future_dates, y=r["ci_lower"],
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(11, 197, 160, 0.18)",
                name="80% CI", hoverinfo="skip",
            ))
            fig.add_trace(_go.Scatter(
                x=future_dates, y=r["forecast_mean"],
                mode="lines", name="Forecast",
                line=dict(color=_FL_TEAL, width=2.5, dash="dash"),
                hovertemplate="%{x|%b %Y}<br>%{y:,.0f}<extra></extra>",
            ))
        fig.update_layout(
            title=dict(text=label,
                       font=dict(family="Playfair Display, Georgia, serif",
                                 size=18, color=_FL_NAVY),
                       x=0, xanchor="left"),
            font=dict(family="Inter, sans-serif", color=_FL_NAVY, size=12),
            paper_bgcolor="white", plot_bgcolor="white",
            height=320, margin=dict(l=20, r=20, t=50, b=30),
            legend=dict(orientation="h", yanchor="bottom",
                        y=1.0, xanchor="right", x=1.0),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#EEF1F5"),
        )
        return fig

    chart_cols = st.columns(2)
    for i, (metric, label) in enumerate(metric_labels.items()):
        with chart_cols[i % 2]:
            r = fc_results.get(metric, {})
            if "error" in r:
                st.warning(f"{label}: {r['error']}")
                continue
            st.plotly_chart(_make_forecast_fig(metric, label),
                            use_container_width=True)

    # ─── Florence pricing implication block ──────────────────────────
    with st.expander(":material/insights: Florence pricing & sales implication"):
        st.markdown(
            f"""
**Annual sales planning** — Plug `{horizon}mo` projected openings into your TAM model.
Today: **{op.get('last_observed', 0):,.0f}** open healthcare positions.
{horizon}-month projection: **{op.get('forecast_mean', [0])[-1]:,.0f}** open positions
({((op.get('forecast_mean', [0])[-1] - op.get('last_observed', 1)) / max(op.get('last_observed', 1), 1) * 100):+.1f}% change).

**Pricing power** — When openings:quits ratio rises, employers are competing harder
for fewer movers. That is when Florence's permanent-placement value proposition
commands the most price. The ratio is moving from **{cur_ratio:.2f}** to
**{fut_ratio:.2f}** over the next {horizon} months.

**Fundraising story** — Use the chart above when investors ask whether the RN
shortage is a "blip." The SARIMA fit on multi-year BLS data shows the structural
trajectory, not a snapshot.
            """
            if "forecast_mean" in op and "forecast_mean" in qt else
            "Forecast data not yet available for all metrics. "
            "Run `python -m surveillance.jolts_healthcare` to extend history."
        )

    # ─── Methodology footnote ────────────────────────────────────────
    with st.expander(":material/help: Methodology"):
        st.markdown(
            """
**Model.** SARIMA(1,1,1)×(1,1,0)₁₂ fit on monthly BLS JOLTS healthcare series.
Confidence intervals at 80% (alpha=0.20).

**Source data.** `data/surveillance/jolts_healthcare/long_history.csv`.
Refreshed via `python -m surveillance.jolts_healthcare` (recommended monthly,
right after BLS releases on the 1st of each month).

**Series.**
- *Job openings level* — JTU6200000000000000JOL
- *Hires level* — JTU6200000000000000HIL
- *Quits level* — JTU6200000000000000QUL
- *Layoffs level* — JTU6200000000000000LDL

**Caveats.**
- SARIMA is a structural projection. Major regime shifts (Medicare cuts,
  pandemic surge) require manual override.
- Confidence widens with horizon — 24mo intervals are wide. Use 12mo for
  point estimates and the band for sensitivity.
- Aggregate national signal. State / MSA forecasts require state-level
  JOLTS subscriptions (not in the free BLS API).
            """
        )


# =====================================================================
# CARE SETTINGS BEYOND HOSPITALS — ASCs, HHAs, SNFs, Hospices, Dialysis
# =====================================================================
if view == "outpatient":
    florence_eyebrow("Outpatient · Build a customer proposal")
    florence_headline(
        "Monthly subscription. Credit card. Expand RN capacity.",
        subhead="ASCs · HHAs · SNFs · hospice · dialysis. Monthly credit-card subscription with 1-month deposit.",
    )

    @st.cache_data
    def _load_non_hospital() -> pd.DataFrame:
        import non_hospital_pricing as nhp
        path = DATA_DIR / "non_hospital_priced.parquet"
        if not path.exists():
            facilities = pd.read_csv(DATA_DIR / "non_hospital_facilities.csv",
                                     dtype={"ccn": str})
            facilities["ccn"] = facilities["ccn"].astype(str).str.zfill(6)
            df = nhp.price_non_hospital(facilities)
            df.to_parquet(path, index=False)
            return df
        return pd.read_parquet(path)

    nh = _load_non_hospital()

    # ── Filters (compact) ─────────────────────────────────────────────
    with st.expander(":material/tune: Filter & sort", expanded=False):
        ctrl1, ctrl2, ctrl3 = st.columns([1.4, 1.2, 1.2])
        with ctrl1:
            type_filter = st.multiselect(
                "Facility types",
                ["ASC", "HHA", "SNF", "HOSPICE", "DIALYSIS"],
                default=["ASC", "HHA", "SNF", "HOSPICE", "DIALYSIS"],
                key="nh_types",
            )
        with ctrl2:
            nh_state = st.multiselect(
                "State",
                sorted(nh["state"].dropna().unique()),
                key="nh_state",
            )
        with ctrl3:
            sort_by = st.selectbox(
                "Sort facilities by",
                ["Revenue uplift (highest)", "Florence fee (highest)",
                 "RN headcount (largest)", "Facility name (A–Z)"],
                key="nh_sort",
            )

    fr = nh[nh["facility_type"].isin(type_filter)].copy() if type_filter else nh.copy()
    if nh_state:
        fr = fr[fr["state"].isin(nh_state)]
    if len(fr) == 0:
        st.warning("No facilities match the current filter.")
        st.stop()

    # ── Chain selector — tile grid sorted by state, with dropdown fallback ──
    import system_tiles as _outpatient_tiles
    active_chain = st.session_state.get("outpatient_active_chain")

    chain_summary = (
        fr.groupby(["health_system_id", "health_system"])
        .agg(n=("ccn", "count"),
             rn=("rn_estimate", "sum"),
             rev=("account_term_revenue_uplift", "sum"))
        .reset_index()
        .sort_values("rev", ascending=False)
    )

    if active_chain is None:
        # Tile grid landing — sorted by state
        florence_eyebrow("Top outpatient chains · sorted by state")
        st.caption(":material/touch_app: Click any tile to open the chain.")
        clicked = _outpatient_tiles.render_outpatient_tile_grid(st, fr)
        if clicked:
            st.session_state["outpatient_active_chain"] = clicked
            st.rerun()

        # Fallback for systems not in the directory + "All facilities"
        with st.expander(
            ":material/search: Search all chains or view full universe",
            expanded=False,
        ):
            chain_labels = ["All facilities in this filter"]
            chain_map = {chain_labels[0]: None}
            for _, r in chain_summary.iterrows():
                if r["health_system_id"] == "independent":
                    continue
                label = f"{r['health_system']} · {int(r['n']):,} facilities"
                chain_labels.append(label)
                chain_map[label] = r["health_system_id"]
            indep_row = chain_summary[chain_summary["health_system_id"] == "independent"]
            if len(indep_row):
                ir = indep_row.iloc[0]
                label = f"Independent / Unknown · {int(ir['n']):,} facilities"
                chain_labels.append(label)
                chain_map[label] = "independent"

            picked = st.selectbox(
                "Pick a chain",
                chain_labels,
                label_visibility="collapsed",
                key="nh_chain_selector_fallback",
            )
            if st.button("Open →", type="primary", key="nh_chain_open"):
                st.session_state["outpatient_active_chain"] = (
                    chain_map[picked] if chain_map[picked] is not None
                    else "__ALL__"
                )
                st.rerun()
        st.stop()

    # Detail view
    if st.button("← Back to chains", key="outpatient_back"):
        st.session_state["outpatient_active_chain"] = None
        st.rerun()

    selected_chain_id = active_chain if active_chain != "__ALL__" else None
    if selected_chain_id is not None:
        fr = fr[fr["health_system_id"] == selected_chain_id]
        if fr.empty:
            st.warning("This chain isn't in the current filter. Clearing.")
            st.session_state["outpatient_active_chain"] = None
            st.rerun()
        selected_chain_name = fr.iloc[0]["health_system"]
    else:
        selected_chain_name = None

    # Customer contacts at the facility level (CMS phone + NPPES address live here).
    if not fr.empty:
        with st.expander(":material/contact_mail: Customer contacts & direct mail", expanded=False):
            _fac_opts = {
                f"{r['name']} — {r.get('city', '')}, {r.get('state', '')}": str(r["ccn"])
                for _, r in fr.head(200).iterrows()
            }
            if _fac_opts:
                _pick = st.selectbox("Facility", list(_fac_opts.keys()), key="out_contact_fac")
                _ccn = _fac_opts[_pick]
                _rev = (float(fr[fr["ccn"].astype(str) == _ccn]["account_term_revenue_uplift"].iloc[0])
                        if "account_term_revenue_uplift" in fr.columns else 0.0)
                render_contact_panel("facility", _ccn, org_name=_pick.split(" — ")[0],
                                     monthly_fee=_rev / 24 if _rev else 0.0, term_impact=_rev)

    # ── Aggregate hero numbers ────────────────────────────────────────
    total_facilities = len(fr)
    total_rns = int(fr["rn_estimate"].sum())
    total_term_fee = fr["account_term_florence_fee"].sum()
    total_term_fica = (fr["account_monthly_fica_savings"] * 24).sum()
    total_term_net_cost = fr["account_term_net_cost"].sum()
    total_term_rev = fr["account_term_revenue_uplift"].sum()
    total_term_benefit = fr["account_term_net_benefit"].sum()
    annual_rev_uplift = total_term_rev / 2
    median_wage = fr["rn_wage_hourly"].median()
    median_fee = fr["florence_fee_per_rn_month"].median()
    median_fica = fr["monthly_fica_savings_per_rn"].median()
    median_rev_per_rn_mo = fr["capacity_revenue_per_rn_month"].median()

    def _fmt_big(v: float) -> str:
        if v >= 1e12: return f"${v/1e12:.2f}T"
        if v >= 1e9:  return f"${v/1e9:.2f}B"
        return f"${v/1e6:,.0f}M"

    # ── Hero: Without Florence (gray) vs With Florence (teal) ─────────
    st.divider()
    type_label = " · ".join(type_filter) if len(type_filter) < 5 else "All non-hospital settings"
    if selected_chain_name and selected_chain_name != "Independent / Unknown":
        florence_eyebrow(f"01 · The opportunity · For {selected_chain_name}")
    else:
        florence_eyebrow("01 · The opportunity · The full non-hospital universe")
    st.markdown(
        f"""
        <div style="display:flex; align-items:baseline; gap:14px; margin: 6px 0 22px 0;">
          <div style="font-family:'Inter',sans-serif; font-size:0.78rem; font-weight:600;
                      letter-spacing:0.22em; text-transform:uppercase; color:#475467;">UNIVERSE</div>
          <div style="font-family:'Playfair Display',serif; font-size:1.9rem; font-weight:600;
                      color:#101828;">{total_facilities:,}</div>
          <div style="font-family:'Inter',sans-serif; font-size:0.95rem; color:#475467;">
            facilities · {total_rns:,} placeable RNs · {type_label}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    card_l, card_arrow, card_r = st.columns([5, 0.6, 5])
    with card_l:
        st.markdown(
            f"""
            <div class="florence-card today">
              <div class="card-label">Without Florence</div>
              <div style="display:flex; align-items:baseline; gap:6px;">
                <div class="card-number" style="font-size:2.6rem;">Labor-capped</div>
              </div>
              <div class="card-headline">Revenue ceiling = staffing ceiling.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with card_arrow:
        st.markdown(
            "<div style='font-family:Playfair Display,serif; font-size:2rem; color:#0ABAB5;"
            " text-align:center; padding-top:75px;'>→</div>",
            unsafe_allow_html=True,
        )
    with card_r:
        st.markdown(
            f"""
            <div class="florence-card with-florence">
              <div class="card-label">With Florence</div>
              <div style="display:flex; align-items:baseline; gap:6px;">
                <div class="card-number">${median_fee:,.0f}</div>
                <div class="card-unit">/RN/month</div>
              </div>
              <div class="card-headline">Monthly subscription.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Delta row — 4 icons showing what shifts in outpatient when Florence is in
    st.markdown(
        f"""
        <div class="fl-delta-row">
          <div class="fl-delta-item">
            <div class="icon">trending_up</div>
            <div class="metric">${median_rev_per_rn_mo:,.0f}/RN/mo</div>
            <div class="label">Revenue unlocked</div>
          </div>
          <div class="fl-delta-item">
            <div class="icon">credit_card</div>
            <div class="metric">Monthly</div>
            <div class="label">Credit card subscription</div>
          </div>
          <div class="fl-delta-item">
            <div class="icon">savings</div>
            <div class="metric">No $50K</div>
            <div class="label">No upfront capex</div>
          </div>
          <div class="fl-delta-item">
            <div class="icon">loyalty</div>
            <div class="metric">Permanent</div>
            <div class="label">FTEs, not agency</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="florence-banner">
          <div class="banner-text">
            Annual incremental revenue unlocked across this filter
          </div>
          <div style="display:flex; align-items:baseline; gap:14px;">
            <div class="banner-value">{_fmt_big(annual_rev_uplift)}</div>
            <div class="banner-suffix">{(total_term_rev / max(total_term_fee, 1)):.0f}× revenue : Florence fee</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── How the customer pays (NEW — timeline redesign) ─────────────
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("02 · How the customer pays")
    florence_headline("Monthly subscription. Credit card. 1-month deposit.")

    median_fee_per_rn = float(median_fee)
    _ex_rn_count = 8
    _ex_monthly = median_fee_per_rn * _ex_rn_count
    _ex_first_month = _ex_monthly * 2
    _ex_term_total = _ex_monthly * 24

    st.markdown(
        f"""
        <div class="fl-timeline">
          <div class="fl-timeline-track">
            <div class="fl-timeline-node start">
              <div class="dot">M1</div>
              <div class="amount">${median_fee_per_rn * 2:,.0f}<span style="font-size:0.7rem; color:#475467; margin-left:3px;">/RN</span></div>
              <div class="label">At signing</div>
              <div class="caption">Deposit + first month</div>
            </div>
            <div class="fl-timeline-node">
              <div class="dot">M2 – 23</div>
              <div class="amount">${median_fee_per_rn:,.0f}<span style="font-size:0.7rem; color:#475467; margin-left:3px;">/RN/mo</span></div>
              <div class="label">Recurring</div>
              <div class="caption">Auto-charged monthly</div>
            </div>
            <div class="fl-timeline-node end">
              <div class="dot">M24</div>
              <div class="amount">$0</div>
              <div class="label">Final</div>
              <div class="caption">Deposit applied</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Worked example — compact, single line
    st.markdown(
        f"""
        <div style="margin-top:14px; padding:12px 18px; background:#F4F6F8;
                    border-left:3px solid #0ABAB5; border-radius:6px;
                    font-family:Inter,sans-serif; font-size:0.9rem; color:#101828;">
          <b>Example · 8-RN cohort:</b>
          <b>${_ex_first_month:,.0f}</b> at signing →
          <b>${_ex_monthly:,.0f}/mo</b> for 22 months →
          <b>${_ex_term_total:,.0f}</b> total.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        f"Median fee: **${median_fee_per_rn:,.0f}/RN/month** · sized to 40% offset of the "
        "customer's payroll tax savings (internal mechanic — say *monthly subscription* to the customer)."
    )

    # ── By-type breakdown ─────────────────────────────────────────────
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("03 · Coverage by setting")
    type_summary = (
        fr.groupby("facility_type")
        .agg(
            n=("ccn", "count"),
            rn_total=("rn_estimate", "sum"),
            fee_term=("account_term_florence_fee", "sum"),
            rev_term=("account_term_revenue_uplift", "sum"),
        )
        .reindex(["ASC", "HHA", "SNF", "HOSPICE", "DIALYSIS"])
        .dropna()
    )
    cols = st.columns(len(type_summary))
    for col, (ft, row) in zip(cols, type_summary.iterrows()):
        col.metric(
            ft,
            f"{int(row['n']):,}",
            f"{int(row['rn_total']):,} RNs · {_fmt_big(row['rev_term']/2)}/yr uplift",
        )

    # ── Per-facility table ────────────────────────────────────────────
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    florence_eyebrow("04 · Per-facility opportunity")
    fac_left, fac_right = st.columns([3, 1])
    with fac_left:
        florence_headline(
            "Highest-value targets first.",
            subhead=(
                "Sorted by 24-month incremental revenue uplift. "
                "Click any facility for the per-RN breakdown."
            ),
        )
    with fac_right:
        st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
        view_n = st.radio(
            "Show",
            ["Top 25", "Top 100", "All"],
            horizontal=True,
            label_visibility="collapsed",
            key="nh_view_n",
        )

    sort_map = {
        "Revenue uplift (highest)": ("account_term_revenue_uplift", False),
        "Florence fee (highest)": ("account_term_florence_fee", False),
        "RN headcount (largest)": ("rn_estimate", False),
        "Facility name (A–Z)": ("name", True),
    }
    sort_col, ascending = sort_map[sort_by]
    sorted_fr = fr.sort_values(sort_col, ascending=ascending)
    limit = {"Top 25": 25, "Top 100": 100, "All": len(sorted_fr)}[view_n]
    sorted_fr = sorted_fr.head(limit)

    display = sorted_fr[[
        "ccn", "name", "facility_type", "city", "state",
        "rn_estimate", "florence_fee_per_rn_month",
        "employer_net_cost_per_rn_month",
        "capacity_revenue_per_rn_month",
        "account_term_revenue_uplift",
        "roi_revenue_to_fee",
    ]].copy()
    display.columns = [
        "CCN", "Facility", "Type", "City", "ST", "RNs",
        "Florence fee/RN/mo", "Net cost/RN/mo",
        "Rev uplift/RN/mo", "24-mo total rev uplift", "ROI",
    ]
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Florence fee/RN/mo": st.column_config.NumberColumn(format="$%.0f"),
            "Net cost/RN/mo": st.column_config.NumberColumn(format="$%.0f"),
            "Rev uplift/RN/mo": st.column_config.NumberColumn(format="$%.0f"),
            "24-mo total rev uplift": st.column_config.NumberColumn(format="$%.0f"),
            "ROI": st.column_config.NumberColumn(format="%.1f×"),
        },
        height=460,
    )

    # ── Methodology ───────────────────────────────────────────────────
    with st.expander(":material/balance: Methodology & data sources", expanded=False):
        st.markdown(
            """
            **Data sources.**
            - Facility universe: CMS Provider Data Catalog (ASC, HHA, SNF, Hospice, Dialysis — May 2026 snapshots)
            - Prevailing RN wage: BLS OEWS state-level annual mean (rolling 12-month, RN SOC 29-1141)
            - RN headcounts: setting-specific operational benchmarks (ASCs by OR count, SNFs by certified beds, HHAs/Hospices/Dialysis by ADC)
            - Capacity revenue per RN: setting-specific gross-revenue benchmarks
              ($400K ASC, $300K HHA, $200K SNF, $250K Hospice, $280K Dialysis per RN per year)

            **Pricing model — monthly subscription.**
            Outpatient settings use a credit-card monthly subscription model —
            NOT the $50K flat placement fee used for hospital deals. The monthly
            fee per RN is sized as `FICA_savings / target_offset_pct` at a 40%
            target offset (so the customer's payroll-side tax savings on F-1 RN
            wages under IRC §3121(b)(19) cover ~40% of the subscription).
            Clamped to a $750 floor and $2,000 ceiling per RN per month so
            small-wage and high-wage settings stay in a defensible band.

            **Payment structure.** One-month deposit + first month's subscription
            charged at signing. Months 2 – 23 auto-charged to credit card on the
            same day each month. Month 24 covered by the deposit. 24-month total
            = 24 × monthly fee.

            **What the customer hears.** "Monthly subscription on your credit
            card. One-month deposit at signing. No long-term commitment beyond
            the 24-month service term." The FICA mechanics are internal — how WE
            size the fee, not how we explain it. The pitch leads with capacity
            expansion because non-hospital settings are revenue-ceiling-limited
            by labor supply, not cost-displacement opportunities.

            **What's not yet modeled.**
            - Chain ownership: NASHP doesn't cover non-hospital. The System Ownership
              tab + bulk CSV import is the path to add USPI, Encompass, Genesis,
              DaVita, Fresenius, etc.
            - MSA-level wage refinement (we use state-level today)
            - Per-facility RN headcount validation (using setting-specific defaults)
            """
        )
        st.info(REQUIRED_COMPLIANCE_SENTENCE, icon=":material/balance:")


# =====================================================================
# MARKET MAP — facility-level, market-adjusted rates (inpatient + outpatient)
# =====================================================================
if view == "market_map":
    florence_brand_strip("MARKET MAP · INTERNAL")
    try:
        import market_map_view as _mm
        _mm.render()
    except Exception as _e:
        st.error(f"Market map failed to load: {_e}")

# =====================================================================
# HEALTH SYSTEMS — aggregate pricing & financials by parent system
# =====================================================================
if view == "health_systems":
    st.subheader("Health-system rollup")
    st.caption(
        "Each row is a parent health system, with all owned/branded hospitals "
        "aggregated. Click into a system to see the breakdown and generate a "
        "system-level proposal."
    )

    sys_agg = priced.groupby("health_system", dropna=False).agg(
        hospitals=("ccn", "count"),
        feasible=("feasible", "sum"),
        states=("state", "nunique"),
        median_loaded_staff=("loaded_staff_cost_per_hr", "median"),
        median_agency_premium=("agency_premium_per_hr", "median"),
        median_florence_premium=("delta_chosen", "median"),
        median_fee=("f_total", "median"),
        median_monthly_fee=("monthly_fee_per_nurse", "median"),
        total_rn_need=("rn_need", "sum"),
        total_florence_fee=("total_florence_fee", "sum"),
        total_monthly_fee=("monthly_florence_fee", "sum"),
        florence_net=("florence_net_total", "sum"),
        partner_revenue=("partner_revenue_total", "sum"),
        net_savings=("net_savings_total", "sum"),
        gross_agency_savings=("gross_agency_savings_total", "sum"),
        median_cl_intensity=("contract_labor_intensity", "median"),
    ).reset_index().sort_values("florence_net", ascending=False)

    # Hide tiny systems for clarity
    min_hospitals = st.slider("Min hospitals per system to show", 1, 25, 1, 1)
    sys_view = sys_agg[sys_agg["hospitals"] >= min_hospitals]

    st.write(f"**{len(sys_view):,}** systems shown (of {len(sys_agg):,})")
    st.dataframe(
        sys_view,
        column_config={
            "median_loaded_staff": st.column_config.NumberColumn("Loaded staff $/hr", format="$%.2f"),
            "median_agency_premium": st.column_config.NumberColumn("Agency premium $/hr", format="$%.2f"),
            "median_florence_premium": st.column_config.NumberColumn("Median Florence prem $/hr", format="$%.2f"),
            "median_fee": st.column_config.NumberColumn("Median fee / nurse", format="$%d"),
            "median_monthly_fee": st.column_config.NumberColumn("Median monthly fee", format="$%d"),
            "total_rn_need": st.column_config.NumberColumn("Total RN need (FTE)", format="%d"),
            "total_florence_fee": st.column_config.NumberColumn("Total Florence fee", format="$%d"),
            "total_monthly_fee": st.column_config.NumberColumn("Total monthly fee", format="$%d"),
            "florence_net": st.column_config.NumberColumn("Florence net", format="$%d"),
            "partner_revenue": st.column_config.NumberColumn("Partner revenue", format="$%d"),
            "net_savings": st.column_config.NumberColumn("Hospital net savings", format="$%d"),
            "gross_agency_savings": st.column_config.NumberColumn("Gross agency savings", format="$%d"),
            "median_cl_intensity": st.column_config.NumberColumn("Median CL share", format="%.1f%%"),
        },
        height=500,
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader("System-level proposal")
    selected_system = st.selectbox(
        "Select a system to generate a proposal",
        sys_view[sys_view["health_system"] != "Independent / Unknown"]["health_system"].tolist(),
    )

    if selected_system:
        sys_hospitals = priced[priced["health_system"] == selected_system].copy()
        sys_feas = sys_hospitals[sys_hospitals["feasible"]]
        manual_n = int(sys_hospitals["manual_review_flag"].sum())
        proposal_lines = [
            f"# Florence Pricing Proposal — {selected_system}",
            f"_Generated {date.today().isoformat()} — Calibration: "
            f"premium capture rate {premium_capture_rate:.1%}, "
            f"floor ${premium_floor:.2f}, cap ${premium_cap:.2f}, "
            f"{amortization_months}-month amortization, η={eta:.2f}_",
            "",
            "## System overview",
            f"- **Hospitals in system:** {len(sys_hospitals)} "
            f"({len(sys_feas)} quotable, {manual_n} flagged for manual review)",
            f"- **States covered:** {sys_hospitals['state'].nunique()} "
            f"({', '.join(sorted(sys_hospitals['state'].unique())[:8])}"
            f"{'...' if sys_hospitals['state'].nunique() > 8 else ''})",
            f"- **Estimated RN need:** {sys_hospitals['rn_need'].sum():,.0f} FTE "
            f"(contracted-labor FTE × {rn_share:.0%} RN share × {coverage:.0%} coverage)",
            f"- **Median loaded staff cost:** ${sys_hospitals['loaded_staff_cost_per_hr'].median():.2f}/hr",
            f"- **Median agency premium:** ${sys_hospitals['agency_premium_per_hr'].median():.2f}/hr",
            f"- **Median Florence premium chosen:** ${sys_feas['delta_chosen'].median():.2f}/hr" if len(sys_feas) else "",
            f"- **Median contract labor share:** "
            f"{sys_hospitals['contract_labor_intensity'].median()*100 if sys_hospitals['contract_labor_intensity'].notna().any() else 0:.1f}% "
            "(HCRIS)",
            "",
            "## Financial picture",
            "",
            "| Party | 3-year total | Monthly (24mo amort) |",
            "|---|---:|---:|",
            f"| Hospital — pays Florence (gross) | ${sys_feas['total_florence_fee'].sum():,.0f} | "
            f"${sys_feas['monthly_florence_fee'].sum():,.0f} / mo |",
            f"| Hospital — gross agency savings (premium otherwise paid) | "
            f"${sys_feas['gross_agency_savings_total'].sum():,.0f} | — |",
            f"| **Hospital — net savings after Florence fee** | "
            f"**${sys_feas['net_savings_total'].sum():,.0f}** | — |",
            f"| Partner channel | ${sys_feas['partner_revenue_total'].sum():,.0f} | — |",
            f"| **Florence net revenue** | **${sys_feas['florence_net_total'].sum():,.0f}** | "
            f"**${sys_feas['florence_net_total'].sum() / amortization_months:,.0f} / mo** |",
            "",
            "## Per-hospital pricing summary",
            "",
            f"| Hospital | City, State | RN need | Loaded $/hr | Agency $/hr | Florence prem $/hr | Fee/nurse | Monthly | Net savings |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, h in sys_feas.sort_values("florence_net_total", ascending=False).head(50).iterrows():
            proposal_lines.append(
                f"| {h['name']} | {h['city']}, {h['state']} | "
                f"{h['rn_need']:,.0f} | "
                f"${h['loaded_staff_cost_per_hr']:.2f} | "
                f"${h['all_in_agency_per_hr']:.2f} | "
                f"${h['delta_chosen']:.2f} | "
                f"${h['f_total']:,.0f} | "
                f"${h['monthly_fee_per_nurse']:,.0f} | "
                f"${h['net_savings_per_nurse']:,.0f} |"
            )
        if len(sys_feas) > 50:
            proposal_lines.append(f"\n_… {len(sys_feas)-50} more hospitals not shown._")
        proposal_lines += [
            "",
            "## Tax assumption",
            "Pricing assumes the cohort visa-exempt share η specified above. FICA "
            "capture under IRC §3121(b)(19) applies only to F-1/J-1/M-1/Q-1/Q-2 "
            "nonresident aliens during their nonresident-alien tax period. EB-3/H-1B/"
            "TN/USC placements have η=0 with no FICA component. Florence does not "
            "provide tax, payroll, immigration, or legal advice; the hospital's tax/"
            "payroll/immigration/legal teams must independently verify status and "
            "applicability per-placement before relying on the projected FICA component.",
            "",
            "## Calibration parameters used",
            f"- Florence premium = min(${premium_cap:.2f}, max(${premium_floor:.2f}, "
            f"agency_premium × {premium_capture_rate:.1%}))",
            f"- RN need = contracted labor FTE × {rn_share:.0%} × {coverage:.0%}",
            f"- Commitment / benefit period: {commitment_years} years × 1,872 hrs/yr",
            f"- Amortization: {amortization_months} months",
            f"- Distribution-partner markup (atop core rate): {amn_partner_markup_pct:.0%}",
            f"- Direct partner markup (atop core rate): {direct_partner_markup_pct:.0%}",
        ]
        proposal_md = "\n".join(proposal_lines)
        st.markdown(proposal_md)

        # ── DOWNLOAD BUNDLE: Excel + 2-page Exec Summary (PDF) + Markdown ──
        st.markdown("---")
        st.subheader("Download proposal bundle for this system")
        st.caption(
            "Excel workbook (10 tabs per v2 §8) + 2-page executive summary (PDF) for "
            "the pitch-deck-builder workflow. Use these as the data + visual source "
            "for the system's PowerPoint deck."
        )

        col_xlsx, col_pdf, col_zip = st.columns(3)
        system_id_sel = sys_hospitals.iloc[0].get("health_system_id", selected_system)

        # Build the live calibration that matches current sidebar settings
        live_cal = Calibration(
            pricing_mode=PricingMode(pricing_mode),
            target_offset_pct=target_offset_pct,
            price_floor_monthly=price_floor_monthly,
            price_ceiling_monthly=price_ceiling_monthly,
            standard_monthly_fee=standard_monthly_fee,
            term_months=term_months,
            fica_eligible_months_default=fica_eligible_months,
            immigration_addon_enabled=immigration_addon_enabled,
            amn_partner_markup_pct=amn_partner_markup_pct,
            direct_partner_markup_pct=direct_partner_markup_pct,
            rn_share_of_contracted_labor=rn_share,
            coverage_fill_factor=coverage,
            agency_displacement_factor=agency_displacement_factor,
            placeholder_msp_markup_pct=placeholder_msp_markup_pct,
        )
        live_cohort = CohortMix(eta=eta, eligible_months=fica_eligible_months)

        safe = selected_system.replace(" ", "_").replace("/", "_")[:48]

        with col_xlsx:
            if st.button(":material/table_view: Generate Excel workbook", key="sys_xlsx_btn"):
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / f"{safe}_v2.xlsx"
                    write_system_workbook(system_id_sel, out, live_cal, live_cohort)
                    st.session_state[f"sys_xlsx_{safe}"] = out.read_bytes()
            if f"sys_xlsx_{safe}" in st.session_state:
                st.download_button(
                    ":material/download: Download .xlsx",
                    st.session_state[f"sys_xlsx_{safe}"],
                    file_name=f"{safe}_v2.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        with col_pdf:
            if st.button(":material/description: Generate 2-page Exec Summary (PDF)", key="sys_pdf_btn"):
                with tempfile.TemporaryDirectory() as tmp:
                    h, p = build_system_exec_summary(system_id_sel, Path(tmp), live_cal, live_cohort)
                    st.session_state[f"sys_pdf_{safe}"] = p.read_bytes()
                    st.session_state[f"sys_html_{safe}"] = h.read_bytes()
            if f"sys_pdf_{safe}" in st.session_state:
                st.download_button(
                    ":material/download: Download .pdf",
                    st.session_state[f"sys_pdf_{safe}"],
                    file_name=f"{safe}_exec_summary.pdf",
                    mime="application/pdf",
                )

        with col_zip:
            if st.button(":material/inventory_2: Generate full bundle (.zip)", key="sys_zip_btn"):
                with tempfile.TemporaryDirectory() as tmp:
                    tmp = Path(tmp)
                    xlsx = write_system_workbook(system_id_sel, tmp / f"{safe}.xlsx", live_cal, live_cohort)
                    h, p = build_system_exec_summary(system_id_sel, tmp, live_cal, live_cohort)
                    md_path = tmp / f"{safe}_proposal.md"
                    md_path.write_text(proposal_md, encoding="utf-8")
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        zf.write(xlsx, f"{safe}/{xlsx.name}")
                        zf.write(p, f"{safe}/{p.name}")
                        zf.write(h, f"{safe}/{h.name}")
                        zf.write(md_path, f"{safe}/{md_path.name}")
                    st.session_state[f"sys_zip_{safe}"] = buf.getvalue()
            if f"sys_zip_{safe}" in st.session_state:
                st.download_button(
                    ":material/download: Download bundle.zip",
                    st.session_state[f"sys_zip_{safe}"],
                    file_name=f"{safe}_florence_bundle.zip",
                    mime="application/zip",
                )

        st.download_button(
            "Markdown proposal (text only)",
            proposal_md.encode("utf-8"),
            file_name=f"florence_proposal_{safe.lower()}.md",
            mime="text/markdown",
        )

# =====================================================================
# SYSTEM OWNERSHIP — M&A scenario modeling, manual ownership overrides
# =====================================================================
if view == "system_ownership":
    florence_eyebrow("04 · System ownership")
    florence_headline(
        "Adjust hospital system assignments.",
        subhead=(
            "Hospitals get sold, systems merge, regional brands roll up. "
            "Override the default ownership mapping here — every proposal, "
            "recommendation, and report reflects your changes immediately. "
            "Use this to fix HCA coverage gaps or model an acquisition scenario."
        ),
    )

    current_universe = cached_universe(sysov.overrides_mtime())
    current_overrides = sysov.load_overrides()
    sys_summary = sysov.known_systems(current_universe)

    # Top-line stats
    s1, s2, s3, s4 = st.columns(4)
    s1.metric(
        "Total hospitals",
        f"{len(current_universe):,}",
    )
    s2.metric(
        "Assigned to a system",
        f"{(current_universe['health_system_id'] != 'independent').sum():,}",
        f"{(current_universe['health_system_id'] != 'independent').sum() / len(current_universe) * 100:.1f}% of universe",
    )
    s3.metric(
        "Independent / Unknown",
        f"{(current_universe['health_system_id'] == 'independent').sum():,}",
    )
    s4.metric(
        "Active overrides",
        f"{len(current_overrides):,}",
        f"updated {datetime.utcnow().date().isoformat()}" if current_overrides else "none",
    )

    # ─── Reassign hospitals ─────────────────────────────────────────
    st.divider()
    florence_eyebrow("Reassign hospitals")
    st.markdown("### Find hospitals to move")

    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        ownership_search = st.text_input(
            "Search by hospital name or CCN",
            placeholder="e.g. 'methodist', 'st francis', '100007'",
            key="own_search",
        )
    with f2:
        ownership_state = st.multiselect(
            "Filter by state",
            sorted(current_universe["state"].dropna().unique()),
            key="own_state",
        )
    with f3:
        ownership_current_system = st.multiselect(
            "Filter by current system",
            sorted(current_universe["health_system"].dropna().unique()),
            key="own_current_sys",
        )

    # Build filtered candidate list
    cand = current_universe.copy()
    if ownership_search.strip():
        q = ownership_search.strip().lower()
        cand = cand[
            cand["name"].str.lower().str.contains(q, na=False)
            | cand["ccn"].astype(str).str.contains(q)
        ]
    if ownership_state:
        cand = cand[cand["state"].isin(ownership_state)]
    if ownership_current_system:
        cand = cand[cand["health_system"].isin(ownership_current_system)]

    st.caption(f"**{len(cand):,}** hospitals match. Showing first 100; refine filters to narrow.")
    cand_show = cand.head(100)[["ccn", "name", "city", "state", "health_system"]].copy()
    cand_show["select"] = False
    edited = st.data_editor(
        cand_show,
        column_config={
            "select": st.column_config.CheckboxColumn("Select"),
            "ccn": st.column_config.TextColumn("CCN", disabled=True, width="small"),
            "name": st.column_config.TextColumn("Hospital", disabled=True),
            "city": st.column_config.TextColumn("City", disabled=True, width="small"),
            "state": st.column_config.TextColumn("ST", disabled=True, width="small"),
            "health_system": st.column_config.TextColumn("Current system", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        key="own_editor",
    )

    selected_ccns = edited.loc[edited["select"]]["ccn"].tolist()

    if selected_ccns:
        st.markdown("### Choose new system")
        target_options = ["── Pick one ──"] + sys_summary["health_system"].tolist() + [
            "[Add a new system not in this list]"
        ]
        sel_target = st.selectbox(
            "Move selected hospitals to",
            target_options,
            key="own_target",
        )
        if sel_target == "[Add a new system not in this list]":
            new_sys_name = st.text_input(
                "New system display name",
                placeholder="e.g. 'Banner Health System' or 'Adventist Health Florida'",
                key="own_new_name",
            )
            new_sys_id = st.text_input(
                "New system id (lowercase, underscores)",
                placeholder=(new_sys_name.lower().replace(" ", "_") if new_sys_name else "e.g. 'banner_health'"),
                key="own_new_id",
            )
        else:
            row = sys_summary[sys_summary["health_system"] == sel_target]
            if len(row):
                new_sys_id = row.iloc[0]["health_system_id"]
                new_sys_name = sel_target
            else:
                new_sys_id, new_sys_name = "", ""
        note_text = st.text_input(
            "Note (optional — e.g. 'HCA acquired Q1 2026')",
            key="own_note",
        )
        c_apply, c_clear = st.columns([1, 1])
        with c_apply:
            apply_disabled = (
                sel_target == "── Pick one ──"
                or not new_sys_id
                or not new_sys_name
            )
            if st.button(
                f":material/check_circle: Reassign {len(selected_ccns)} hospital(s)",
                type="primary",
                disabled=apply_disabled,
                use_container_width=True,
                key="own_apply",
            ):
                rows = [
                    {"ccn": ccn, "new_system_id": new_sys_id,
                     "new_system_name": new_sys_name, "note": note_text}
                    for ccn in selected_ccns
                ]
                n = sysov.append_overrides_bulk(rows)
                st.success(
                    f"Reassigned {n} hospital(s) to **{new_sys_name}**. "
                    "All proposals & recommendations now reflect this change."
                )
                st.cache_data.clear()
                st.rerun()
        with c_clear:
            st.caption(
                "Note: changes propagate immediately to the Build a customer proposal "
                "tab, Excel exports, and PDF summaries."
            )

    # ─── Active overrides table ─────────────────────────────────────
    st.divider()
    florence_eyebrow("Active overrides")
    if not current_overrides:
        st.info(
            "No overrides yet. Search above and reassign hospitals to start customizing "
            "system ownership for your sales territory or M&A scenarios.",
            icon=":material/info:",
        )
    else:
        # Show table of current overrides
        u_idx = current_universe.set_index("ccn")
        rows = []
        for r in current_overrides:
            name = u_idx.loc[r.ccn]["name"] if r.ccn in u_idx.index else "(unknown CCN)"
            state = u_idx.loc[r.ccn]["state"] if r.ccn in u_idx.index else ""
            rows.append({
                "ccn": r.ccn,
                "name": name,
                "state": state,
                "now_in": r.new_system_name or r.new_system_id,
                "note": r.note,
                "added": r.created_at[:10],
            })
        ov_df = pd.DataFrame(rows)
        st.dataframe(
            ov_df,
            column_config={
                "ccn": st.column_config.TextColumn("CCN", width="small"),
                "name": st.column_config.TextColumn("Hospital"),
                "state": st.column_config.TextColumn("ST", width="small"),
                "now_in": st.column_config.TextColumn("Now assigned to"),
                "note": st.column_config.TextColumn("Note"),
                "added": st.column_config.TextColumn("Added", width="small"),
            },
            hide_index=True,
            use_container_width=True,
        )
        d1, d2 = st.columns([1, 3])
        with d1:
            if st.button(
                ":material/delete_sweep: Clear ALL overrides",
                type="secondary",
                use_container_width=True,
                key="own_clear_all",
            ):
                n = sysov.delete_all_overrides()
                st.success(f"Cleared {n} override(s). Reverted to default ownership mapping.")
                st.cache_data.clear()
                st.rerun()
        with d2:
            st.caption(
                "Clearing all overrides reverts every reassigned hospital to its "
                "default `hospital_universe.csv` ownership. Cannot be undone."
            )

    # ─── Bulk CSV import ─────────────────────────────────────────────
    st.divider()
    florence_eyebrow("Bulk import / export")
    bi_l, bi_r = st.columns([1, 1])
    with bi_l:
        st.markdown("**Upload a CSV** with columns: `ccn`, `new_system_id`, `new_system_name`, `note` (optional)")
        upload = st.file_uploader(
            "Bulk override CSV",
            type=["csv"],
            label_visibility="collapsed",
            key="own_upload",
        )
        if upload is not None:
            try:
                bulk_df = pd.read_csv(upload, dtype={"ccn": str})
                bulk_df["ccn"] = bulk_df["ccn"].astype(str).str.zfill(6)
                st.write(f"Preview ({len(bulk_df)} rows):")
                st.dataframe(bulk_df.head(10), use_container_width=True, hide_index=True)
                if st.button(
                    f":material/upload: Apply {len(bulk_df)} override(s) from CSV",
                    type="primary",
                    key="own_apply_csv",
                ):
                    n = sysov.append_overrides_bulk(bulk_df.to_dict(orient="records"))
                    st.success(f"Applied {n} override(s) from CSV.")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"CSV parse error: {e}")
    with bi_r:
        st.markdown("**Download current overrides** for backup or sharing")
        if current_overrides:
            ov_export = pd.DataFrame([r.to_dict() for r in current_overrides])
            st.download_button(
                ":material/download: Download overrides as CSV",
                ov_export.to_csv(index=False).encode("utf-8"),
                file_name=f"florence_system_overrides_{datetime.utcnow().date().isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No active overrides to export.")

# =====================================================================
# PRICE A HOSPITAL — single-hospital evidence pack with proposal
# =====================================================================
if view == "price_hospital":
    st.subheader("Price a hospital")
    st.caption(
        "Pick any hospital, get the full CFO pricing breakdown — what the hospital "
        "pays, what they save vs agency, what splits to partner, what Florence nets."
    )

    # Honor a preselect from the Inpatient tile grid (Hospitals view → Open →)
    _preselect_ccn = st.session_state.pop("price_hospital_preselect_ccn", None)
    _preselect_row = None
    if _preselect_ccn:
        _hits = universe[universe["ccn"].astype(str).str.zfill(6) == str(_preselect_ccn).zfill(6)]
        if not _hits.empty:
            _preselect_row = _hits.iloc[0]
            st.success(
                f":material/local_hospital: Pre-selected **{_preselect_row['name']}** "
                f"from the Inpatient hospital tiles.",
                icon=":material/info:",
            )

    _states_list = sorted(universe["state"].unique())
    _default_state_idx = (
        _states_list.index(_preselect_row["state"]) if _preselect_row is not None
        else (_states_list.index("CA") if "CA" in _states_list else 0)
    )
    state_pick = st.selectbox(
        "State", _states_list,
        index=_default_state_idx,
    )
    hosp_list = universe[universe["state"] == state_pick].sort_values("name")
    _hosp_labels = hosp_list.apply(
        lambda r: f"{r['name']} — {r['city']}", axis=1).tolist()
    _default_hosp_idx = 0
    if _preselect_row is not None and _preselect_row["state"] == state_pick:
        _target_label = f"{_preselect_row['name']} — {_preselect_row['city']}"
        if _target_label in _hosp_labels:
            _default_hosp_idx = _hosp_labels.index(_target_label)
    hosp_label = st.selectbox(
        "Hospital", _hosp_labels, index=_default_hosp_idx,
    )
    row = hosp_list.iloc[_hosp_labels.index(hosp_label)]

    profile = row_to_profile(row)
    # Attach data provenance for manual-review decision
    profile.agency_rate_confidence = float(row.get("confidence", 0.85) or 0.85)
    profile.agency_rate_source = str(row.get("data_source", "unspecified"))
    cal = Calibration(
        pricing_mode=PricingMode(pricing_mode),
        target_offset_pct=target_offset_pct,
        price_floor_monthly=price_floor_monthly,
        price_ceiling_monthly=price_ceiling_monthly,
        standard_monthly_fee=standard_monthly_fee,
        term_months=term_months,
        fica_eligible_months_default=fica_eligible_months,
        immigration_addon_enabled=immigration_addon_enabled,
        amn_partner_markup_pct=amn_partner_markup_pct,
        direct_partner_markup_pct=direct_partner_markup_pct,
        rn_share_of_contracted_labor=rn_share,
        coverage_fill_factor=coverage,
        agency_displacement_factor=agency_displacement_factor,
    )
    cohort = CohortMix(eta=eta)
    result = price(profile, cohort, cal)

    # Pull product-plan RN need from priced row (matched by ccn)
    priced_row = priced[priced["ccn"] == row["ccn"]]
    rn_need = float(priced_row["rn_need"].iloc[0]) if len(priced_row) else 0.0

    if result.manual_review_flag:
        st.warning(f"⚠ MANUAL REVIEW REQUIRED — {result.manual_review_reason}")

    with st.expander(":material/contact_mail: Customer contact & direct mail", expanded=False):
        try:
            _ti = (float(priced_row["target_term_net_savings_account"].iloc[0])
                   if (len(priced_row) and "target_term_net_savings_account" in priced_row.columns)
                   else 0.0)
        except Exception:
            _ti = 0.0
        render_contact_panel("hospital", str(row["ccn"]).zfill(6), org_name=str(row["name"]),
                             monthly_fee=float(result.monthly_fee), term_impact=_ti)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric(
        "Florence fee / nurse",
        f"${result.f_total:,.0f}",
        f"${result.monthly_fee:,.0f} / mo for {amortization_months} mo",
    )
    s2.metric(
        "Hospital net saves / hr",
        f"${result.net_savings_per_hr:.2f}",
        f"${result.net_savings:,.0f} per nurse over commitment",
    )
    s3.metric(
        "Partner revenue / nurse",
        f"${result.partner_revenue:,.0f}",
        f"{result.partner_share:.0%} split",
    )
    s4.metric(
        "Florence net / nurse",
        f"${result.florence_net_revenue:,.0f}",
        f"${result.florence_net_monthly:,.0f} / mo",
    )

    st.text(render_evidence_pack(result))

    st.markdown("**Hospital context (from CMS + HCRIS)**")
    ctx_cols = st.columns(4)
    ctx_cols[0].metric("CCN", row["ccn"])
    ctx_cols[1].metric("Type", str(row["hospital_type"]).replace("Hospitals", "").strip())
    ctx_cols[2].metric("Health system", str(row["health_system"]))
    ctx_cols[3].metric("Data confidence", f"{float(row['confidence']):.2f}")

    ctx_cols2 = st.columns(4)
    ctx_cols2[0].metric("Estimated RN need (FTE)", f"{rn_need:,.0f}")
    cl = row.get("contract_labor_intensity")
    ctx_cols2[1].metric(
        "Contract labor share (HCRIS)",
        f"{float(cl)*100:.1f}%" if pd.notna(cl) else "—",
    )
    om = row.get("operating_margin")
    ctx_cols2[2].metric(
        "Operating margin (HCRIS)",
        f"{float(om)*100:.1f}%" if pd.notna(om) else "—",
    )
    ctx_cols2[3].metric(
        "Total FTE (HCRIS)",
        f"{float(row['hcris_total_fte']):,.0f}" if pd.notna(row.get("hcris_total_fte")) else "—",
    )

    if result.feasible and rn_need:
        gross = result.f_total * rn_need
        monthly = result.monthly_fee * rn_need
        fl_net = result.florence_net_revenue * rn_need
        ptr = result.partner_revenue * rn_need
        save = result.net_savings * rn_need
        st.info(
            f"**Account-level (at projected RN need of {rn_need:,.0f} FTE):**  \n"
            f"Total Florence fee: **${gross:,.0f}** (${monthly:,.0f}/mo over {amortization_months} mo)  \n"
            f"Florence net: **${fl_net:,.0f}** · Partner: ${ptr:,.0f}  \n"
            f"Hospital net savings (after Florence fee): **${save:,.0f}**"
        )

    # ---- Per-hospital proposal generator
    st.markdown("---")
    st.subheader("Generate proposal for this hospital")
    if st.button("Generate proposal", key="single_hospital_proposal"):
        lines = [
            f"# Florence Pricing Proposal — {row['name']}",
            f"_{row['city']}, {row['state']} · CCN {row['ccn']} · "
            f"Generated {date.today().isoformat()}_",
            "",
            "## Recommendation at a glance",
            f"- **Florence fee per nurse:** ${result.f_total:,.0f}",
            f"- **Monthly fee ({amortization_months}mo amort):** ${result.monthly_fee:,.0f}/mo",
            f"- **Hospital effective premium over staff:** "
            f"${result.hospital_premium_per_hr:.2f}/hr "
            f"(${result.hospital_premium_per_hr * result.commitment_hours:,.0f} over commitment)",
            f"- **Gross agency savings (premium otherwise paid):** "
            f"${result.gross_agency_savings:,.0f} over commitment",
            f"- **Net savings after Florence fee:** "
            f"${result.net_savings:,.0f} (${result.net_savings_per_hr:.2f}/hr)",
            f"- **Channel:** {result.channel.value}",
            f"- **Partner revenue (if applicable):** ${result.partner_revenue:,.0f}",
            f"- **Florence net revenue:** ${result.florence_net_revenue:,.0f} "
            f"(${result.florence_net_monthly:,.0f}/mo)",
            "",
            "## Market inputs",
            f"- Loaded staff cost (C): ${result.loaded_staff_cost_per_hr:.2f}/hr",
            f"- All-in agency cost (A): "
            f"${result.loaded_staff_cost_per_hr + result.agency_premium_per_hr:.2f}/hr",
            f"- Agency premium (M = A − C): ${result.agency_premium_per_hr:.2f}/hr",
            f"- Employer FICA per hour: ${result.employer_fica_per_hr:.2f}/hr",
            f"- Health system: {row.get('health_system', 'Independent / Unknown')}",
            f"- Estimated RN need: {rn_need:,.0f} FTE "
            f"(contracted-labor FTE × {rn_share:.0%} × {coverage:.0%})",
            "",
            "## Pricing math (product plan formula)",
            f"- Premium capture rate: {result.premium_capture_rate:.1%}",
            f"- Premium raw = M × capture_rate = ${result.delta_raw:.2f}/hr",
            f"- Premium floor / cap: ${result.premium_floor:.2f} / ${result.premium_cap:.2f}",
            f"- Florence premium chosen (clamped): ${result.delta_chosen:.2f}/hr",
            f"- F_base = H_c × premium = ${result.f_base:,.0f}",
            f"- F_fica = η × T_emp × H_exempt = ${result.f_fica:,.0f}",
            f"- F_total = ${result.f_total:,.0f}",
            f"- Monthly fee = F_total / {amortization_months} = ${result.monthly_fee:,.0f}",
            "",
            "## Tax assumption",
            "The FICA component assumes the cohort visa-exempt share η specified. "
            "Florence does not provide tax, payroll, immigration, or legal advice. "
            "The hospital's tax/payroll/immigration/legal teams must independently "
            "verify visa status, work authorization, tax residency, and applicability "
            "of IRC §3121(b)(19) to each placement.",
            "",
            f"_Calibration version: {result.calibration_version}_",
        ]
        proposal_md = "\n".join(lines)
        st.markdown(proposal_md)
        st.download_button(
            "Download proposal (Markdown)",
            proposal_md.encode("utf-8"),
            file_name=f"florence_proposal_{row['ccn']}.md",
            mime="text/markdown",
        )

    # ── Per-hospital download bundle ──
    st.markdown("---")
    st.subheader("Download proposal bundle for this hospital")
    safe_h = str(row['ccn']) + "_" + str(row['name']).replace(' ', '_').replace('/', '_')[:32]

    live_cal_h = Calibration(
        pricing_mode=PricingMode(pricing_mode),
        target_offset_pct=target_offset_pct,
        price_floor_monthly=price_floor_monthly,
        price_ceiling_monthly=price_ceiling_monthly,
        standard_monthly_fee=standard_monthly_fee,
        term_months=term_months,
        fica_eligible_months_default=fica_eligible_months,
        immigration_addon_enabled=immigration_addon_enabled,
        amn_partner_markup_pct=amn_partner_markup_pct,
        direct_partner_markup_pct=direct_partner_markup_pct,
        rn_share_of_contracted_labor=rn_share,
        coverage_fill_factor=coverage,
        agency_displacement_factor=agency_displacement_factor,
        placeholder_msp_markup_pct=placeholder_msp_markup_pct,
    )
    live_cohort_h = CohortMix(eta=eta, eligible_months=fica_eligible_months)

    h_col1, h_col2, h_col3 = st.columns(3)
    with h_col1:
        if st.button(":material/table_view: Generate Excel", key="hosp_xlsx_btn"):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / f"{safe_h}.xlsx"
                write_hospital_workbook(row['ccn'], out, live_cal_h, live_cohort_h)
                st.session_state[f"h_xlsx_{safe_h}"] = out.read_bytes()
        if f"h_xlsx_{safe_h}" in st.session_state:
            st.download_button(
                ":material/download: Download .xlsx",
                st.session_state[f"h_xlsx_{safe_h}"],
                file_name=f"{safe_h}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    with h_col2:
        if st.button(":material/description: Generate Exec Summary PDF", key="hosp_pdf_btn"):
            with tempfile.TemporaryDirectory() as tmp:
                hh, pp = build_hospital_exec_summary(row['ccn'], Path(tmp), live_cal_h, live_cohort_h)
                st.session_state[f"h_pdf_{safe_h}"] = pp.read_bytes()
        if f"h_pdf_{safe_h}" in st.session_state:
            st.download_button(
                ":material/download: Download .pdf",
                st.session_state[f"h_pdf_{safe_h}"],
                file_name=f"{safe_h}_exec.pdf",
                mime="application/pdf",
            )
    with h_col3:
        if st.button(":material/inventory_2: Generate bundle (.zip)", key="hosp_zip_btn"):
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                xlsx = write_hospital_workbook(row['ccn'], tmp / f"{safe_h}.xlsx", live_cal_h, live_cohort_h)
                hh, pp = build_hospital_exec_summary(row['ccn'], tmp, live_cal_h, live_cohort_h)
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(xlsx, f"{safe_h}/{xlsx.name}")
                    zf.write(pp, f"{safe_h}/{pp.name}")
                    zf.write(hh, f"{safe_h}/{hh.name}")
                st.session_state[f"h_zip_{safe_h}"] = buf.getvalue()
        if f"h_zip_{safe_h}" in st.session_state:
            st.download_button(
                ":material/download: Download bundle.zip",
                st.session_state[f"h_zip_{safe_h}"],
                file_name=f"{safe_h}_bundle.zip",
                mime="application/zip",
            )

# =====================================================================
# HOSPITAL TABLE — full universe filterable
# =====================================================================
if view == "hospital_table":
    st.subheader("Hospital pricing — full universe")
    f1, f2, f3, f4, f5 = st.columns(5)
    state_filter = f1.multiselect(
        "State", sorted(priced["state"].unique()), default=[], key="tbl_state",
    )
    system_filter = f2.multiselect(
        "Health system", sorted(priced["health_system"].unique()), default=[], key="tbl_system",
    )
    htype_filter = f3.multiselect(
        "Hospital type", sorted(priced["hospital_type"].dropna().unique()),
        default=[], key="tbl_htype",
    )
    feasible_only = f4.checkbox("Feasible only", value=True, key="tbl_feasible")
    min_confidence = f5.slider("Min data confidence", 0.0, 1.0, 0.0, 0.05, key="tbl_minconf")

    tbl = priced.copy()
    if state_filter:
        tbl = tbl[tbl["state"].isin(state_filter)]
    if system_filter:
        tbl = tbl[tbl["health_system"].isin(system_filter)]
    if htype_filter:
        tbl = tbl[tbl["hospital_type"].isin(htype_filter)]
    if feasible_only:
        tbl = tbl[tbl["feasible"]]
    tbl = tbl[tbl["confidence"] >= min_confidence]

    st.write(f"**{len(tbl):,}** hospitals match.")

    display_cols = [
        "ccn", "name", "city", "state", "health_system", "hospital_type",
        "loaded_staff_cost_per_hr", "all_in_agency_per_hr", "agency_premium_per_hr",
        "delta_chosen", "f_total", "monthly_fee_per_nurse",
        "partner_revenue_per_nurse", "florence_net_per_nurse",
        "net_savings_per_hr", "rn_need",
        "total_florence_fee", "monthly_florence_fee",
        "florence_net_total", "net_savings_total",
        "contract_labor_intensity", "operating_margin",
        "channel", "manual_review_flag", "confidence",
    ]
    st.dataframe(
        tbl[display_cols].round(2).sort_values("florence_net_total", ascending=False),
        column_config={
            "loaded_staff_cost_per_hr": st.column_config.NumberColumn("Loaded staff $/hr", format="$%.2f"),
            "all_in_agency_per_hr": st.column_config.NumberColumn("Agency $/hr", format="$%.2f"),
            "agency_premium_per_hr": st.column_config.NumberColumn("Agency premium $/hr", format="$%.2f"),
            "delta_chosen": st.column_config.NumberColumn("Florence prem $/hr", format="$%.2f"),
            "f_total": st.column_config.NumberColumn("Fee / nurse", format="$%d"),
            "monthly_fee_per_nurse": st.column_config.NumberColumn("Monthly / nurse", format="$%d"),
            "partner_revenue_per_nurse": st.column_config.NumberColumn("Partner / nurse", format="$%d"),
            "florence_net_per_nurse": st.column_config.NumberColumn("FL net / nurse", format="$%d"),
            "net_savings_per_hr": st.column_config.NumberColumn("Hosp save $/hr", format="$%.2f"),
            "rn_need": st.column_config.NumberColumn("RN need (FTE)", format="%d"),
            "total_florence_fee": st.column_config.NumberColumn("Total fee", format="$%d"),
            "monthly_florence_fee": st.column_config.NumberColumn("Total monthly", format="$%d"),
            "florence_net_total": st.column_config.NumberColumn("Florence net total", format="$%d"),
            "net_savings_total": st.column_config.NumberColumn("Hosp net savings", format="$%d"),
            "contract_labor_intensity": st.column_config.NumberColumn("CL share", format="%.1f%%"),
            "operating_margin": st.column_config.NumberColumn("Op margin", format="%.1f%%"),
        },
        height=600,
        use_container_width=True,
    )

    csv_bytes = tbl[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered view (CSV)",
        csv_bytes,
        file_name="florence_pricing_view.csv",
        mime="text/csv",
    )

# =====================================================================
# MARKET VIEW — price dispersion across states
# =====================================================================
if view == "market_view":
    st.subheader("How pricing varies across markets")
    st.caption(
        "Each row is a state. The engine quotes a different fee per hospital based "
        "on local wages and agency premium; the median fee per state is shown here."
    )
    by_state = market_aggregate(priced, "state")
    by_state["feasibility_rate"] = (
        by_state["feasibility_rate"] * 100
    ).round(1).astype(str) + "%"
    cols = ["state", "hospitals_total", "hospitals_feasible", "feasibility_rate",
            "median_loaded_staff_cost", "median_agency_rate", "median_agency_premium",
            "median_fee_per_nurse", "median_monthly_fee_per_nurse",
            "total_florence_net", "total_partner_revenue", "total_net_savings",
            "total_rn_need"]
    st.dataframe(
        by_state[cols].sort_values("median_fee_per_nurse", ascending=False),
        column_config={
            "median_loaded_staff_cost": st.column_config.NumberColumn("Loaded staff $/hr", format="$%.2f"),
            "median_agency_rate": st.column_config.NumberColumn("Agency $/hr", format="$%.2f"),
            "median_agency_premium": st.column_config.NumberColumn("Agency premium $/hr", format="$%.2f"),
            "median_fee_per_nurse": st.column_config.NumberColumn("Median fee / nurse", format="$%d"),
            "median_monthly_fee_per_nurse": st.column_config.NumberColumn("Median monthly / nurse", format="$%d"),
            "total_florence_net": st.column_config.NumberColumn("Florence net", format="$%d"),
            "total_partner_revenue": st.column_config.NumberColumn("Partner revenue", format="$%d"),
            "total_net_savings": st.column_config.NumberColumn("Hospital net savings", format="$%d"),
            "total_rn_need": st.column_config.NumberColumn("RN need (FTE)", format="%d"),
        },
        height=600,
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader("Median Florence fee by state")
    states_sorted = by_state.sort_values("median_fee_per_nurse", ascending=False)
    st.bar_chart(states_sorted.set_index("state")["median_fee_per_nurse"])

# =====================================================================
# PRICING ELASTICITY — contract labor bands
# =====================================================================
if view == "elasticity":
    st.subheader("Pricing elasticity — by contract labor share")
    st.caption(
        "Hospitals with higher contract labor share have larger structural agency "
        "premiums. The engine prices accordingly: δ scales with M, so high-CL "
        "hospitals get a higher per-hour spread."
    )
    has_cl = priced[priced["contract_labor_intensity"].notna()].copy()

    bins = [0, 0.05, 0.10, 0.15, 0.25, 0.50, 1.00]
    labels = ["0-5%", "5-10%", "10-15%", "15-25%", "25-50%", "50%+"]
    has_cl["cl_band"] = pd.cut(
        has_cl["contract_labor_intensity"],
        bins=bins, labels=labels, include_lowest=True,
    )
    band_agg = has_cl.groupby("cl_band", observed=True).agg(
        hospitals=("ccn", "count"),
        median_agency_premium=("agency_premium_per_hr", "median"),
        median_delta_chosen=("delta_chosen", "median"),
        median_fee=("f_total", "median"),
        median_florence_net=("florence_net_per_nurse", "median"),
        median_hospital_savings=("net_savings_per_hr", "median"),
    ).reset_index()
    st.dataframe(
        band_agg.round(2),
        column_config={
            "cl_band": "Contract labor share",
            "hospitals": st.column_config.NumberColumn("Hospitals", format="%d"),
            "median_agency_premium": st.column_config.NumberColumn("Agency premium $/hr", format="$%.2f"),
            "median_delta_chosen": st.column_config.NumberColumn("Median δ $/hr", format="$%.2f"),
            "median_fee": st.column_config.NumberColumn("Median fee / nurse", format="$%d"),
            "median_florence_net": st.column_config.NumberColumn("Florence net / nurse", format="$%d"),
            "median_hospital_savings": st.column_config.NumberColumn("Hospital save $/hr", format="$%.2f"),
        },
        use_container_width=True,
    )
    st.caption(
        "Reading the bands: the engine's market-sensitive δ rises with agency premium. "
        "High-CL-share hospitals see a higher fee — and at the same α, hospitals in those "
        "bands still capture (1 − α) of their agency premium as savings."
    )

# =====================================================================
# CALIBRATION SWEEP — α × η
# =====================================================================
if view == "calibration_sweep":
    st.subheader("Calibration sweep — Target FICA offset % × η")
    st.caption(
        "Pre-computed sweep over target_offset_pct (the v2 FICA-offset target) "
        "and η (FICA-exempt cohort share). Use this to size the tradeoff between "
        "Florence net revenue and hospital savings at different target offsets."
    )
    sweep = cached_sweep()

    chart_net = sweep.pivot(
        index="target_offset_pct", columns="eta", values="total_term_florence_net"
    )
    st.markdown("**Total Florence net revenue (term) by target offset × η**")
    st.line_chart(chart_net)

    chart_save = sweep.pivot(
        index="target_offset_pct", columns="eta", values="total_term_net_savings"
    )
    st.markdown("**Total hospital net savings (term) by target offset × η**")
    st.line_chart(chart_save)

    chart_monthly = sweep.pivot(
        index="target_offset_pct", columns="eta", values="total_monthly_florence_fee"
    )
    st.markdown("**Total monthly Florence fee by target offset × η**")
    st.line_chart(chart_monthly)

    st.markdown("**Full sweep data**")
    st.dataframe(sweep.round(2), use_container_width=True, height=400)

    sweep_csv = sweep.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download sweep (CSV)", sweep_csv,
        file_name="florence_calibration_sweep.csv", mime="text/csv",
    )

# =====================================================================
# DATA QUALITY
# =====================================================================
if view == "data_quality":
    st.subheader("Data confidence breakdown")
    conf_summary = priced.groupby("data_source").agg(
        n_hospitals=("ccn", "count"),
        median_confidence=("confidence", "median"),
        median_loaded_staff_cost=("loaded_staff_cost_per_hr", "median"),
        median_agency_rate=("all_in_agency_per_hr", "median"),
        median_fee=("f_total", "median"),
    ).round(2).reset_index()
    st.dataframe(conf_summary, use_container_width=True)

    st.markdown("""
**Confidence tiers:**
- `commonspirit_demo` (1.00): direct match to FlorenceOS demo dataset (real customer/HCRIS-derived rates).
- `hcris_derived_with_state_agency` (0.85): HCRIS gives per-hospital salaries, FTE, contract labor; state-level agency rate imputed.
- `state_imputed_with_commonspirit_anchor` (0.60): state has CS data; this hospital imputed from state median.
- `national_imputed` (0.40): no state CS data; uses national median × state wage.

**Geocoding:** 100% of hospitals geocoded (exact ZIP centroid + 3-digit ZIP prefix fallback).
**Health system inference:** 15% of hospitals matched by name keyword; production version needs AHA parent-system mapping.

**To increase confidence further** — see [HCRIS_NMRC_NEXT.md](HCRIS_NMRC_NEXT.md) for the agency-hours ingest scope.
""")

# =====================================================================
# DATA PROVENANCE — per-source tracking (v2 §3)
# =====================================================================
if view == "data_provenance":
    st.subheader("Per-rate source provenance (v2 §3 source governance)")
    st.caption(
        "Every rate observation tracked with source, as_of_date, and confidence tier. "
        "This is the audit trail that backs the pricing engine."
    )

    # market_rate_observations table
    obs_path = DATA_DIR / "market_rate_observations.csv"
    if obs_path.exists():
        obs = pd.read_csv(obs_path)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total observations", f"{len(obs):,}")
        c2.metric("High confidence", f"{(obs['confidence_tier']=='High').sum():,}")
        c3.metric("Medium confidence", f"{(obs['confidence_tier']=='Medium').sum():,}")
        c4.metric("Low confidence", f"{(obs['confidence_tier']=='Low').sum():,}")

        st.markdown("**By source type:**")
        src_summary = obs.groupby(["source_type", "rate_type"]).agg(
            n=("observation_id", "count"),
            median_hourly=("hourly_pay", "median"),
            median_confidence=("confidence_score", "median"),
        ).reset_index()
        st.dataframe(src_summary.round(2), use_container_width=True)

        st.markdown("**Sample observations (first 50):**")
        st.dataframe(
            obs[["as_of_date", "source_type", "geography_type", "geography",
                 "rate_type", "hourly_pay", "confidence_tier"]].head(50),
            use_container_width=True, height=400,
        )

        csv_obs = obs.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download all observations (CSV)", csv_obs,
            file_name="florence_market_rate_observations.csv", mime="text/csv",
        )

    # System overlays — split into real-disclosed and placeholder
    st.markdown("---")
    st.subheader("Documented system-level MSP overlays (v2 §5.2)")

    st.markdown("**Real-disclosed (verified data):**")
    overlays_path = DATA_DIR / "system_level_overlays.csv"
    if overlays_path.exists():
        overlays = pd.read_csv(overlays_path, dtype={"ccn": str})
        st.markdown(f"_{overlays['health_system_id'].nunique()} system(s) with disclosed overlays "
                    f"applied to {len(overlays):,} facilities._")
        ov_summary = overlays.groupby("health_system_name").agg(
            n_facilities=("ccn", "count"),
            overlay_per_hour=("overlay_per_hour", "first"),
            total_allocated=("additional_agency_fee_allocated", "sum"),
            source=("overlay_source", "first"),
        ).reset_index()
        st.dataframe(ov_summary, use_container_width=True)

    st.markdown(f"**Placeholder ({placeholder_msp_markup_pct:.0%} markup, slider-controlled):**")
    placeholder_priced = priced[priced.get("is_placeholder_system", False) == True]
    if len(placeholder_priced):
        ph_summary = placeholder_priced.groupby("health_system").agg(
            n_facilities=("ccn", "count"),
            median_overlay_per_hour=("placeholder_msp_overlay_per_hour", "median"),
            median_base_agency=("all_in_agency_per_hour_pre_overlay", "median"),
            total_24mo_fee=("term_florence_fee_account", "sum"),
        ).reset_index().sort_values("total_24mo_fee", ascending=False)
        ph_summary["markup_pct_applied"] = f"{placeholder_msp_markup_pct:.0%}"
        st.dataframe(
            ph_summary.round(2),
            column_config={
                "median_overlay_per_hour": st.column_config.NumberColumn(
                    "Median overlay $/hr", format="$%.2f"),
                "median_base_agency": st.column_config.NumberColumn(
                    "Median base HCRIS $/hr", format="$%.2f"),
                "total_24mo_fee": st.column_config.NumberColumn(
                    "Total 24-mo Florence fee", format="$%d"),
            },
            use_container_width=True,
        )
        st.caption(
            f"As you adjust the sidebar slider, the overlay rate scales linearly. "
            f"Current setting: {placeholder_msp_markup_pct:.0%} of base HCRIS agency rate. "
            f"Industry-standard MSP markups are 15-30%; Kaiser's actual is 17.6%."
        )
    else:
        st.info("No placeholder-system hospitals in current filtered view.")

    # Snapshots
    st.markdown("---")
    st.subheader("Pricing snapshots — point-in-time reproducibility")
    st.caption(
        "Each pricing batch run is archived as a daily snapshot. Use to reproduce "
        "historical proposals, compare pricing across dates, audit calibration changes."
    )
    try:
        from snapshots import list_snapshots
        snapshots_avail = list_snapshots()
        if snapshots_avail:
            st.write(f"**{len(snapshots_avail)} snapshot(s) available:** "
                     f"{', '.join(d.isoformat() for d in snapshots_avail)}")
        else:
            st.info("No snapshots yet — run `python3 snapshots.py` to generate today's snapshot.")
    except Exception as e:
        st.warning(f"Snapshot listing unavailable: {e}")


# =====================================================================
# Bottom-of-page: collapsed national aggregates + methodology footer
# (Internal numbers. Behind an expander so they don't dominate the tabs.)
# =====================================================================
st.markdown("<div style='height:60px;'></div>", unsafe_allow_html=True)

with st.expander(":material/bar_chart: National calibration aggregates · Florence internal", expanded=False):
    st.caption(
        f"Five primary v2 buyer-facing numbers (median across {len(feas):,} quotable hospitals "
        f"of {total:,} total; {manual_review_count} flagged for manual review)."
    )
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "①  Florence Monthly Fee / RN",
        f"${median_monthly_fee:,.0f}/mo",
        f"Target: {target_offset_pct:.0%} FICA offset",
    )
    k2.metric(
        "②  Employer FICA Savings / RN",
        f"${median_fica:,.0f}/mo",
        help="What the hospital saves in employer payroll tax for the F-1 cohort.",
    )
    k3.metric(
        "③  FICA-Adjusted Effective Cost",
        f"${median_effective:,.0f}/mo",
        help="Florence fee minus the FICA offset; the CFO's net Florence cost.",
    )
    k4.metric(
        "④  Actual FICA Offset %",
        f"{median_offset_pct:.1%}",
        f"vs {target_offset_pct:.0%} target",
    )
    k5.metric(
        "⑤  Net Monthly Savings / RN",
        f"${median_net:,.0f}/mo",
        "= agency avoided + FICA − fee",
    )

    st.markdown("**National aggregates at current calibration**")
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric(
        "Total RN need (FTE)",
        f"{addressable_rn:,.0f}",
        help="Contracted Labor FTE × RN share × coverage",
    )
    a2.metric(
        "Total monthly Florence billings",
        f"${total_monthly_fee/1e6:,.0f}M/mo",
        f"${term_florence_fee/1e9:.2f}B over {term_months} mo",
    )
    a3.metric(
        "Total monthly FICA offset",
        f"${total_monthly_fica/1e6:,.0f}M/mo",
        "to hospitals",
    )
    a4.metric(
        "Total monthly net savings",
        f"${total_monthly_net_savings/1e6:,.0f}M/mo",
        f"${term_net_savings/1e9:.2f}B over {term_months} mo",
    )
    a5.metric(
        "Savings : Fee ratio",
        f"{term_net_savings/term_florence_fee:.1f}×" if term_florence_fee > 0 else "—",
        help="Hospital net savings ÷ Florence fee (term basis).",
    )
    st.info(REQUIRED_COMPLIANCE_SENTENCE, icon=":material/balance:")

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="font-family:'Inter',sans-serif; font-size:0.78rem; color:#475467;
                line-height:1.55; padding-top:10px; border-top:1px solid #E5E8EE;">
      <strong style="color:#101828;">Cohort assumption.</strong>
      All quotes assume Florence's confirmed F-1 student pipeline (η = 1.0) with 24 FICA-exempt
      months per nurse. The F-1 student FICA exemption applies during the nonresident-alien
      period under
      <a href="https://www.irs.gov/individuals/international-taxpayers/foreign-student-liability-for-social-security-and-medicare-taxes"
         style="color:#067F7B; text-decoration:none; border-bottom:1px solid #0ABAB5;"
         target="_blank">
        IRC §3121(b)(19) (IRS — Foreign Student Liability for SS/Medicare Taxes)
      </a>
      · IRS Pub 519. Eligibility must be confirmed by payroll, tax counsel, and immigration counsel
      per the compliance disclosure above.
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
st.caption(
    f"Calibration version: {Calibration().version} · "
    f"Universe: {total:,} CMS-registered hospitals · "
    "Wage data: BLS OEWS May 2024 MSA-level (top 60 MSAs) + HCRIS-derived per-hospital + state fallback · "
    "Agency rates: HCRIS NMRC per-hospital (3,011 hospitals) + Kaiser MSP overlay (+$17.39/hr) · "
    "Geocoding: Census 2024 ZCTA centroids · "
    "ZIP→CBSA: Census 2023 delineation."
)
