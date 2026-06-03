"""
PDF report generator for customer-facing leads.

Produces a 2-page Florence-branded PDF customized to the visitor's inputs
(state + facility type + RN count). Sent to leads after email gate.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, SimpleDocTemplate,
)

TEAL = colors.HexColor("#0ABAB5")
TEAL_DARK = colors.HexColor("#067F7B")
NAVY = colors.HexColor("#101828")
GRAY = colors.HexColor("#F4F6F8")
BORDER = colors.HexColor("#E5E8EE")
INK = colors.HexColor("#101828")
MUTED = colors.HexColor("#475467")


def _fmt_big(v: float) -> str:
    v = float(v or 0)
    if abs(v) >= 1e9: return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6: return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3: return f"${v/1e3:,.2f}K"
    return f"${v:,.2f}"


def build_report(
    email: str,
    state: str,
    facility_type: str,
    n_rns: int,
    result: dict,
) -> BytesIO:
    """Return the 2-page PDF as BytesIO."""
    buf = BytesIO()

    def draw_brand_strip(c: canvas.Canvas, page_num: int):
        c.saveState()
        # Teal F square
        c.setFillColor(TEAL)
        c.roundRect(0.5*inch, 10.3*inch, 0.32*inch, 0.32*inch, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(0.66*inch, 10.39*inch, "F")
        # Wordmark
        c.setFillColor(NAVY)
        c.setFont("Times-Bold", 14)
        c.drawString(0.92*inch, 10.4*inch, "Florence Workforce Calculator")
        # Page tag (right)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 7)
        c.drawRightString(
            8*inch, 10.43*inch,
            f"CONFIDENTIAL  ·  PERSONALIZED SAVINGS ANALYSIS  ·  PAGE {page_num}",
        )
        # Divider
        c.setStrokeColor(BORDER)
        c.line(0.5*inch, 10.25*inch, 8*inch, 10.25*inch)
        c.restoreState()

    c = canvas.Canvas(buf, pagesize=LETTER)

    # ─────── PAGE 1 ───────
    draw_brand_strip(c, 1)

    # Eyebrow
    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(0.5*inch, 9.85*inch, "PERSONALIZED FOR YOUR BUSINESS")

    # Main headline
    c.setFillColor(NAVY)
    c.setFont("Times-Bold", 26)
    c.drawString(0.5*inch, 9.4*inch, "Your savings analysis,")
    c.drawString(0.5*inch, 8.95*inch, f"{facility_type} in {state}.")

    # Intro paragraph
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    intro_lines = [
        f"This report is generated from your {date.today().isoformat()} session at florence.com/calculator.",
        f"Inputs: {n_rns} permanent RN{'s' if n_rns != 1 else ''}  ·  {state} BLS prevailing RN wage of ${result['wage']:,.2f}/hour",
        f"  ·  {facility_type}  ·  Flat $50K placement fee per RN  ·  36-month amortization",
    ]
    y = 8.55*inch
    for ln in intro_lines:
        c.drawString(0.5*inch, y, ln)
        y -= 0.18*inch

    # Big result tile (teal)
    c.setFillColor(TEAL)
    c.roundRect(0.5*inch, 7.0*inch, 7.5*inch, 0.95*inch, 8, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(0.7*inch, 7.78*inch, "ANNUAL REVENUE YOU CAN UNLOCK")
    c.setFont("Times-Bold", 30)
    c.drawString(0.7*inch, 7.27*inch, _fmt_big(result["annual_revenue_uplift"]))
    c.setFont("Helvetica", 10)
    c.drawString(3.5*inch, 7.4*inch,
                 f"{n_rns} permanent RN{'s' if n_rns != 1 else ''}")
    c.drawString(3.5*inch, 7.22*inch,
                 f"× ${result['rev_per_rn_year']:,.0f} / RN / yr incremental")

    # Per-RN economics (FICA-free public version)
    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(0.5*inch, 6.65*inch, "PER-RN ECONOMICS")

    net_benefit_per_rn = (
        result["rev_per_rn_month"] - result["florence_fee_per_rn_month"]
    )
    economics_rows = [
        ("Florence placement fee (flat $50K amortized over 36 months)",
         f"${result['florence_fee_per_rn_month']:,.0f}/mo"),
        (f"Incremental revenue per RN per month ({facility_type})",
         f"${result['rev_per_rn_month']:,.0f}/mo"),
        ("Net benefit per RN per month",
         f"${net_benefit_per_rn:,.0f}/mo"),
        (f"Total Florence investment ({n_rns} RN{'s' if n_rns != 1 else ''} × $50,000)",
         f"${50_000 * n_rns:,.0f}"),
        ("Total revenue unlocked over the 36-month term",
         f"{_fmt_big(result['annual_revenue_uplift'] * 3)}"),
    ]
    y = 6.35*inch
    for i, (label, value) in enumerate(economics_rows):
        # Highlight the bottom row
        if i == len(economics_rows) - 1:
            c.setFillColor(TEAL_DARK)
        else:
            c.setFillColor(INK)
        c.setFont("Helvetica", 10)
        c.drawString(0.5*inch, y, label)
        c.setFont("Times-Bold", 11)
        c.drawRightString(8*inch, y, value)
        # Divider line
        c.setStrokeColor(BORDER)
        c.line(0.5*inch, y - 0.05*inch, 8*inch, y - 0.05*inch)
        y -= 0.32*inch

    # Big payoff sentence
    c.setFillColor(NAVY)
    c.setFont("Times-Bold", 14)
    c.drawString(0.5*inch, 4.4*inch,
                 f"36-month total net benefit: {_fmt_big(result['term_savings_total'])}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(0.5*inch, 4.15*inch,
                 f"Your business unlocks {_fmt_big(result['annual_revenue_uplift'] * 3)} in incremental "
                 f"revenue over a 3-year cohort term.")

    # CTA box at bottom of page 1
    c.setFillColor(NAVY)
    c.roundRect(0.5*inch, 1.5*inch, 7.5*inch, 1.55*inch, 8, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(0.7*inch, 2.85*inch, "NEXT STEPS")
    c.setFillColor(colors.white)
    c.setFont("Times-Bold", 18)
    c.drawString(0.7*inch, 2.45*inch, "Two ways to start with Florence.")
    c.setFont("Helvetica", 10)
    c.drawString(0.7*inch, 2.15*inch,
                 "1.  $99/mo  ·  Florence Workforce Intelligence — ongoing labor analysis for your business.")
    c.drawString(0.7*inch, 1.95*inch,
                 "2.  $50K / RN  ·  Begin a Florence cohort placement — first RN delivered in 9–12 months.")
    c.setFillColor(colors.HexColor("#7DCBB4"))
    c.setFont("Helvetica", 8)
    c.drawString(0.7*inch, 1.7*inch,
                 "Visit florence.com/calculator and use the email-gated buttons to begin checkout.")

    # Footer (page 1)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(0.5*inch, 1.2*inch, f"Report delivered to: {email}  ·  Generated {date.today().isoformat()}  ·  Methodology continues on page 2.")

    c.showPage()

    # ─────── PAGE 2 — Methodology ───────
    draw_brand_strip(c, 2)

    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(0.5*inch, 9.85*inch, "METHODOLOGY & DISCLOSURES")
    c.setFillColor(NAVY)
    c.setFont("Times-Bold", 22)
    c.drawString(0.5*inch, 9.45*inch, "How we calculated these numbers.")

    methodology_text = [
        ("Wage data",
         f"U.S. Bureau of Labor Statistics, Occupational Employment and Wage "
         f"Statistics (OEWS), May 2024, Registered Nurses (SOC 29-1141), "
         f"state-level annual mean ÷ 2,080 hours. For {state}: "
         f"${result['wage']:,.2f}/hour."),
        ("Florence fee structure",
         "Flat $50,000 per RN placement fee, amortized over 36-month placement "
         "term ($1,389/RN/mo equivalent). Fee is payable on successful "
         "employment start with replacement protection for early attrition."),
        ("Incremental revenue assumption",
         f"For {facility_type}, we use ${result['rev_per_rn_year']:,.0f} per RN per "
         "year as a setting-specific incremental gross revenue benchmark. "
         "Actual revenue uplift depends on your case mix, payor mix, "
         "operational scale, and your existing capacity utilization. "
         "Florence does not warrant a specific dollar outcome."),
        ("How Florence places permanent RNs",
         "Florence operates a complete RN production pipeline — exam preparation, "
         "higher education, and bedside practice — preparing internationally-trained "
         "RNs for permanent U.S. clinical practice. Each placement is a full-time "
         "employee of your business, hired through your standard HR processes."),
        ("Disclosure",
         "This analysis is illustrative and based on inputs you provided. Actual "
         "results vary by facility size, payor mix, regulatory environment, and "
         "Florence onboarding capacity. Florence is not a financial, tax, or legal "
         "advisor. Engage your own counsel before contracting."),
    ]
    y = 9.05*inch
    for title, body in methodology_text:
        c.setFillColor(TEAL_DARK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(0.5*inch, y, title.upper())
        y -= 0.18*inch
        c.setFillColor(INK)
        c.setFont("Helvetica", 10)
        # Word-wrap manually for long body
        from reportlab.lib.utils import simpleSplit
        for line in simpleSplit(body, "Helvetica", 10, 7.4*inch):
            c.drawString(0.5*inch, y, line)
            y -= 0.16*inch
        y -= 0.16*inch  # paragraph gap

    # Disclaimer at bottom
    c.setStrokeColor(BORDER)
    c.line(0.5*inch, 1.2*inch, 8*inch, 1.2*inch)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(0.5*inch, 1.05*inch,
                 "This analysis is illustrative and based on inputs you provided. Actual results vary by")
    c.drawString(0.5*inch, 0.9*inch,
                 "facility size, payor mix, regulatory environment, and Florence onboarding capacity.")
    c.drawString(0.5*inch, 0.75*inch,
                 "Florence is not a financial, tax, or legal advisor. Engage your own counsel before contracting.")

    c.save()
    buf.seek(0)
    return buf


if __name__ == "__main__":
    # CLI smoke test
    test_result = {
        "wage": 137.69,
        "monthly_wage": 21479,
        "florence_fee_per_rn_month": 1389,
        "fica_savings_per_rn_month": 1643,
        "net_cost_per_rn_month": -254,
        "rev_per_rn_month": 25000,
        "rev_per_rn_year": 300_000,
        "annual_revenue_uplift": 3_000_000,
        "annual_net_cost": -30_480,
        "annual_net_benefit": 3_030_480,
        "term_savings_total": 9_091_440,
        "roi_multiple": 180,
        "fica_covers_fee": True,
    }
    buf = build_report("test@example.com", "CA", "Home Health Agency (HHA)", 10, test_result)
    out = Path("data/test_customer_report.pdf")
    out.write_bytes(buf.getvalue())
    print(f"✓ Wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
