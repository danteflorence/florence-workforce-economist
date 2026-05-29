"""
Two-page executive summary generator.

Produces:
  - HTML (browser-viewable, print-to-PDF works cleanly)
  - PDF (programmatically generated via reportlab; works headless / batch)

Per user request: "killer numbers prominently featured to facilitate decision making."

Public API:
    build_hospital_exec_summary(ccn, ...) -> (html_path, pdf_path)
    build_system_exec_summary(health_system_id, ...) -> (html_path, pdf_path)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak, KeepInFrame, NextPageTemplate
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from pricing_engine import (
    Calibration, CohortMix, REQUIRED_COMPLIANCE_SENTENCE,
)
from pricing_batch import load_universe, price_batch

# Brand palette
NAVY = colors.HexColor("#0B2545")
TEAL = colors.HexColor("#1E6091")
ACCENT = colors.HexColor("#2DB8A3")
LIGHT_BG = colors.HexColor("#F0F5FA")
WARN_BG = colors.HexColor("#FFF8E6")
MUTED = colors.HexColor("#6B7280")
BORDER = colors.HexColor("#E2E6EE")


def _fmt_money(v: float) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "—"
    if abs(v) >= 1e9: return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
    if abs(v) >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def _fmt_money_full(v: float) -> str:
    if v is None: return "—"
    return f"${v:,.0f}"


def _fmt_pct(v: float) -> str:
    if v is None: return "—"
    return f"{v*100:.1f}%"


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def _gather(target_rows: pd.DataFrame, cal: Calibration, cohort: CohortMix) -> dict:
    priced = price_batch(target_rows, cohort, cal)
    feas = priced[priced["feasible"]]

    if len(feas) == 0:
        return {"empty": True, "priced": priced, "feas": feas}

    return {
        "empty": False,
        "priced": priced,
        "feas": feas,
        "n_hospitals": len(priced),
        "n_quotable": len(feas),
        "n_manual_review": int(priced["manual_review_flag"].sum()),
        "rn_need_total": float(feas["rn_need"].sum()),
        "median_monthly_fee": float(feas["florence_monthly_fee_per_rn"].median()),
        "median_fica_savings": float(feas["employer_fica_savings_per_rn_per_month"].median()),
        "median_effective_cost": float(feas["fica_adjusted_effective_cost_per_rn_month"].median()),
        "median_offset_pct": float(feas["actual_fica_offset_pct"].median()),
        "median_net_savings": float(feas["net_monthly_savings_per_rn"].median()),
        "total_monthly_fee": float(feas["monthly_florence_fee_account"].sum()),
        "total_monthly_fica": float(feas["monthly_fica_offset_account"].sum()),
        "total_monthly_net_savings": float(feas["monthly_net_savings_account"].sum()),
        "total_monthly_agency_avoided": float(feas["monthly_agency_avoided_account"].sum()),
        "term_florence_fee": float(feas["term_florence_fee_account"].sum()),
        "term_net_savings": float(feas["term_net_savings_account"].sum()),
        "states": sorted(target_rows["state"].unique().tolist()),
        "term_months": cal.term_months,
    }


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _render_html(target_name: str, target_type: str, scope_desc: str,
                 cal: Calibration, cohort: CohortMix, m: dict) -> str:
    today = date.today().isoformat()
    if m.get("empty"):
        return f"<html><body><h1>No quotable hospitals for {target_name}</h1></body></html>"

    # Build hospital-detail rows for page 2 (top 20 by Florence net term)
    feas = m["feas"].sort_values("florence_net_term_account", ascending=False).head(20)
    detail_rows = ""
    for _, h in feas.iterrows():
        detail_rows += f"""
        <tr>
          <td><strong>{h['name']}</strong><br/><span class="muted">{h['city']}, {h['state']}</span></td>
          <td class="num">{h['rn_need']:,.0f}</td>
          <td class="num">${h['florence_monthly_fee_per_rn']:,.0f}</td>
          <td class="num">${h['employer_fica_savings_per_rn_per_month']:,.0f}</td>
          <td class="num">{h['actual_fica_offset_pct']*100:.0f}%</td>
          <td class="num">${h['net_monthly_savings_per_rn']:,.0f}</td>
          <td class="num">${h['monthly_florence_fee_account']/1e6:,.2f}M</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Florence Executive Summary — {target_name}</title>
<style>
@page {{ size: letter; margin: 0.5in; }}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
       margin: 0; padding: 0.5in; color: #1A2230; line-height: 1.4; font-size: 11px; }}
h1 {{ color: #0B2545; font-size: 22px; margin: 0 0 6px 0; letter-spacing: -0.01em; }}
h2 {{ color: #0B2545; font-size: 14px; margin: 18px 0 6px 0; }}
.subtitle {{ color: #6B7280; font-size: 11px; margin-bottom: 14px; }}
.tagline {{ background: linear-gradient(135deg,#0B2545,#1E6091); color:white;
            border-radius:6px; padding:12px 16px; margin:12px 0 18px; font-size:13px; }}
.kpi-grid {{ display:grid; grid-template-columns: repeat(5,1fr); gap:8px; margin:8px 0 16px; }}
.kpi {{ border:1px solid #E2E6EE; border-radius:6px; padding:10px 12px; background:#F7F8FB; }}
.kpi-label {{ font-size:9px; color:#6B7280; text-transform:uppercase; letter-spacing:.5px; }}
.kpi-value {{ font-size:20px; font-weight:700; color:#0B2545; margin-top:4px; }}
.kpi-sub {{ font-size:9px; color:#6B7280; margin-top:2px; }}
.split-grid {{ display:grid; grid-template-columns: repeat(4,1fr); gap:8px; margin:8px 0 18px; }}
.split {{ border-top:3px solid #1E6091; border-radius:6px; padding:12px;
          background:white; border-left:1px solid #E2E6EE; border-right:1px solid #E2E6EE;
          border-bottom:1px solid #E2E6EE; }}
.split.fica {{ border-top-color:#2DB8A3; }}
.split.agency {{ border-top-color:#C97A3B; }}
.split.net {{ border-top-color:#0B2545; background:#F0F5FA; }}
.split-label {{ font-size:10px; color:#6B7280; text-transform:uppercase; letter-spacing:.5px; }}
.split-value {{ font-size:18px; font-weight:700; color:#0B2545; margin-top:6px; }}
.split-sub {{ font-size:10px; color:#6B7280; margin-top:4px; }}
table {{ width:100%; border-collapse:collapse; margin-top:6px; font-size:10px; }}
th, td {{ padding:6px 8px; text-align:left; border-bottom:1px solid #E2E6EE; }}
th {{ background:#F0F5FA; font-weight:600; color:#0B2545; font-size:9px;
      text-transform:uppercase; letter-spacing:.5px; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.muted {{ color:#6B7280; font-size:9px; }}
.compliance {{ background:#FFF8E6; border-left:3px solid #C97A3B; border-radius:4px;
               padding:10px 14px; font-size:9px; color:#6B5824; margin-top:14px; line-height:1.5; }}
.footer {{ font-size:8px; color:#6B7280; border-top:1px solid #E2E6EE;
           padding-top:6px; margin-top:14px; }}
.page-break {{ page-break-before: always; }}
</style>
</head>
<body>

<!-- ─── PAGE 1: HEADLINE NUMBERS ─── -->
<h1>{target_name}</h1>
<div class="subtitle">{target_type} · {scope_desc} · Generated {today}</div>

<div class="tagline">
  <strong>Florence Workforce Restoration Economics v2 — FICA-Offset Target Pricing.</strong><br/>
  At {cal.target_offset_pct:.0%} FICA offset target on an F-1 cohort 24-month term, Florence delivers
  <strong>{_fmt_money(m['term_net_savings'])}</strong> in hospital net savings against
  <strong>{_fmt_money(m['term_florence_fee'])}</strong> in Florence fees — a
  <strong>{m['term_net_savings']/m['term_florence_fee']:.1f}× return</strong> for the customer.
</div>

<h2>The five primary buyer-facing numbers (median per quotable hospital)</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">①  Florence Fee / RN</div>
    <div class="kpi-value">${m['median_monthly_fee']:,.0f}</div>
    <div class="kpi-sub">per RN per month</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">②  Employer FICA Savings</div>
    <div class="kpi-value">${m['median_fica_savings']:,.0f}</div>
    <div class="kpi-sub">per RN per month (F-1 cohort)</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">③  Effective Florence Cost</div>
    <div class="kpi-value">${m['median_effective_cost']:,.0f}</div>
    <div class="kpi-sub">fee minus FICA offset</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">④  Actual FICA Offset</div>
    <div class="kpi-value">{m['median_offset_pct']*100:.1f}%</div>
    <div class="kpi-sub">target {cal.target_offset_pct*100:.0f}%</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">⑤  Net Monthly Savings / RN</div>
    <div class="kpi-value">${m['median_net_savings']:,.0f}</div>
    <div class="kpi-sub">agency avoided + FICA − fee</div>
  </div>
</div>

<h2>Aggregate financial picture — what each party gets</h2>
<div class="split-grid">
  <div class="split">
    <div class="split-label">Hospital pays Florence (gross)</div>
    <div class="split-value">{_fmt_money(m['total_monthly_fee'])} / mo</div>
    <div class="split-sub">{_fmt_money(m['term_florence_fee'])} over {m['term_months']} mo</div>
  </div>
  <div class="split fica">
    <div class="split-label">Hospital captures FICA offset</div>
    <div class="split-value">{_fmt_money(m['total_monthly_fica'])} / mo</div>
    <div class="split-sub">visible on payroll-tax line</div>
  </div>
  <div class="split agency">
    <div class="split-label">Hospital avoids agency premium</div>
    <div class="split-value">{_fmt_money(m['total_monthly_agency_avoided'])} / mo</div>
    <div class="split-sub">contracted-labor displacement</div>
  </div>
  <div class="split net">
    <div class="split-label">Hospital net monthly savings</div>
    <div class="split-value">{_fmt_money(m['total_monthly_net_savings'])} / mo</div>
    <div class="split-sub">{_fmt_money(m['term_net_savings'])} over {m['term_months']} mo</div>
  </div>
</div>

<h2>Scope</h2>
<table>
<tr><th style="width:50%">Item</th><th>Value</th></tr>
<tr><td>Hospitals in scope</td><td class="num">{m['n_hospitals']:,}</td></tr>
<tr><td>Quotable at current calibration</td><td class="num">{m['n_quotable']:,}</td></tr>
<tr><td>Total Covered RN Need (FTE)</td><td class="num">{m['rn_need_total']:,.0f}</td></tr>
<tr><td>States covered</td><td class="num">{len(m['states'])} ({', '.join(m['states'][:5])}{'...' if len(m['states'])>5 else ''})</td></tr>
<tr><td>Cohort visa-exempt share (η)</td><td class="num">{cohort.eta:.2f}</td></tr>
<tr><td>FICA-eligible months / nurse</td><td class="num">{cohort.eligible_months or cal.fica_eligible_months_default}</td></tr>
<tr><td>Contract term</td><td class="num">{cal.term_months} months</td></tr>
</table>

<!-- ─── PAGE 2: PER-HOSPITAL DETAIL + COMPLIANCE ─── -->
<div class="page-break"></div>

<h1>Per-hospital detail — top {min(len(feas),20)} by Florence revenue</h1>
<div class="subtitle">Each hospital priced at its local labor economics. Sorted by total monthly Florence billings.</div>

<table>
  <thead>
    <tr>
      <th>Hospital</th>
      <th class="num">RN Need (FTE)</th>
      <th class="num">Fee / RN / mo</th>
      <th class="num">FICA / RN / mo</th>
      <th class="num">Offset %</th>
      <th class="num">Net Savings / RN / mo</th>
      <th class="num">Total Monthly Fee</th>
    </tr>
  </thead>
  <tbody>
    {detail_rows}
  </tbody>
</table>

<h2>Methodology</h2>
<p style="font-size:10px;">
  Florence Workforce Restoration Economics v2 (May 28, 2026).
  <strong>Florence Monthly Fee per RN = Suggested Fee, clamped to floor/ceiling</strong>, where
  <strong>Suggested Fee = Employer FICA Savings ÷ {cal.target_offset_pct:.0%} target</strong>.
  Employer FICA savings calculated under IRC §3121(b)(19) for F-1 nonresident-alien RNs during their
  nonresident-alien tax period. Guardrails: ${cal.price_floor_monthly:,.0f} ≤ fee ≤ ${cal.price_ceiling_monthly:,.0f}.
</p>

<h2>Data sources</h2>
<p style="font-size:10px;">
  Hospital roster: CMS Hospital General Information (data.cms.gov).
  Per-hospital salaries, FTE, contract labor: CMS HCRIS Hospital Provider Cost Report 2023.
  RN wage benchmarks: BLS OEWS state-level. Agency rate benchmarks: hybrid (customer-disclosed
  where available, CommonSpirit anchor, state median).
</p>

<div class="compliance">
  <strong>Required compliance statement:</strong>  {REQUIRED_COMPLIANCE_SENTENCE}
</div>

<div class="footer">
  IRS sources:
  <a href="https://www.irs.gov/individuals/international-taxpayers/foreign-student-liability-for-social-security-and-medicare-taxes">
    Foreign Student Liability for Social Security and Medicare Taxes
  </a>; IRC §3121(b)(19); IRS Publication 519; IRS Publication 15 (Circular E).
  Calibration: {cal.version} · Pricing mode: {cal.pricing_mode.value} ·
  Florence does not provide tax, payroll, immigration, or legal advice.
</div>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# PDF renderer (reportlab — no external deps)
# ---------------------------------------------------------------------------

def _render_pdf(output_path: Path, target_name: str, target_type: str,
                scope_desc: str, cal: Calibration, cohort: CohortMix,
                m: dict) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(output_path), pagesize=letter,
        leftMargin=0.5*inch, rightMargin=0.5*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch,
        title=f"Florence Executive Summary — {target_name}",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame])])

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20,
                        textColor=NAVY, spaceAfter=4, leading=24)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10,
                         textColor=MUTED, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13,
                        textColor=NAVY, spaceAfter=4, spaceBefore=10)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10,
                          spaceAfter=6, leading=13)
    body_small = ParagraphStyle("body_small", parent=styles["Normal"],
                                 fontSize=9, leading=12)
    tagline = ParagraphStyle("tag", parent=styles["Normal"], fontSize=11,
                              textColor=colors.white, leading=15)
    compliance = ParagraphStyle("comp", parent=styles["Normal"], fontSize=8,
                                 textColor=colors.HexColor("#6B5824"),
                                 leading=11, spaceBefore=4)

    story = []
    if m.get("empty"):
        story.append(Paragraph(f"No quotable hospitals for {target_name}", h1))
        doc.build(story)
        return output_path

    # ---- PAGE 1 ----
    story.append(Paragraph(target_name, h1))
    story.append(Paragraph(
        f"{target_type} · {scope_desc} · Generated {date.today().isoformat()}", sub
    ))

    # Tagline box
    tag_text = (
        f"<b>Florence Workforce Restoration Economics v2 — FICA-Offset Target Pricing.</b><br/>"
        f"At {cal.target_offset_pct:.0%} FICA offset target on an F-1 cohort {cal.term_months}-month term, "
        f"Florence delivers <b>{_fmt_money(m['term_net_savings'])}</b> in hospital net savings "
        f"against <b>{_fmt_money(m['term_florence_fee'])}</b> in Florence fees — a "
        f"<b>{m['term_net_savings']/m['term_florence_fee']:.1f}× return</b> for the customer."
    )
    tag_table = Table(
        [[Paragraph(tag_text, tagline)]],
        colWidths=[doc.width],
    )
    tag_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("BOX", (0,0), (-1,-1), 1, NAVY),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
    ]))
    story.append(tag_table)
    story.append(Spacer(1, 14))

    # KPI strip (5 numbers)
    story.append(Paragraph("The five primary buyer-facing numbers (median per quotable hospital)", h2))
    kpi_data = [
        [
            Paragraph("①  Florence Fee / RN", body_small),
            Paragraph("②  FICA Savings", body_small),
            Paragraph("③  Effective Cost", body_small),
            Paragraph("④  Actual Offset %", body_small),
            Paragraph("⑤  Net Mo Savings / RN", body_small),
        ],
        [
            Paragraph(f"<b>${m['median_monthly_fee']:,.0f}</b><br/><font size=8 color='#6B7280'>per RN per month</font>", body),
            Paragraph(f"<b>${m['median_fica_savings']:,.0f}</b><br/><font size=8 color='#6B7280'>per RN per month</font>", body),
            Paragraph(f"<b>${m['median_effective_cost']:,.0f}</b><br/><font size=8 color='#6B7280'>fee − FICA offset</font>", body),
            Paragraph(f"<b>{m['median_offset_pct']*100:.1f}%</b><br/><font size=8 color='#6B7280'>target {cal.target_offset_pct*100:.0f}%</font>", body),
            Paragraph(f"<b>${m['median_net_savings']:,.0f}</b><br/><font size=8 color='#6B7280'>agency + FICA − fee</font>", body),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[doc.width/5]*5, rowHeights=[18, 50])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), LIGHT_BG),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TEXTCOLOR", (0,1), (-1,1), NAVY),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # Financial picture (4-split)
    story.append(Paragraph("Aggregate financial picture — what each party gets", h2))
    split_data = [
        [
            Paragraph("<font size=8 color='#6B7280'><b>HOSPITAL PAYS FLORENCE</b></font>", body_small),
            Paragraph("<font size=8 color='#6B7280'><b>HOSPITAL FICA OFFSET</b></font>", body_small),
            Paragraph("<font size=8 color='#6B7280'><b>AGENCY PREMIUM AVOIDED</b></font>", body_small),
            Paragraph("<font size=8 color='#6B7280'><b>HOSPITAL NET SAVINGS</b></font>", body_small),
        ],
        [
            Paragraph(f"<b>{_fmt_money(m['total_monthly_fee'])}</b> / mo<br/><font size=8 color='#6B7280'>{_fmt_money(m['term_florence_fee'])} over {m['term_months']}mo</font>", body),
            Paragraph(f"<b>{_fmt_money(m['total_monthly_fica'])}</b> / mo<br/><font size=8 color='#6B7280'>visible on payroll tax</font>", body),
            Paragraph(f"<b>{_fmt_money(m['total_monthly_agency_avoided'])}</b> / mo<br/><font size=8 color='#6B7280'>contracted-labor displacement</font>", body),
            Paragraph(f"<b>{_fmt_money(m['total_monthly_net_savings'])}</b> / mo<br/><font size=8 color='#6B7280'>{_fmt_money(m['term_net_savings'])} over {m['term_months']}mo</font>", body),
        ],
    ]
    split_table = Table(split_data, colWidths=[doc.width/4]*4, rowHeights=[18, 50])
    split_table.setStyle(TableStyle([
        ("LINEABOVE", (0,1), (0,1), 3, TEAL),
        ("LINEABOVE", (1,1), (1,1), 3, ACCENT),
        ("LINEABOVE", (2,1), (2,1), 3, colors.HexColor("#C97A3B")),
        ("LINEABOVE", (3,1), (3,1), 3, NAVY),
        ("BACKGROUND", (3,1), (3,1), LIGHT_BG),
        ("BOX", (0,0), (-1,-1), 0.5, BORDER),
        ("LINEBELOW", (0,0), (-1,0), 0.5, BORDER),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(split_table)
    story.append(Spacer(1, 14))

    # Scope table
    story.append(Paragraph("Scope", h2))
    scope_data = [
        ["Hospitals in scope", f"{m['n_hospitals']:,}"],
        ["Quotable at current calibration", f"{m['n_quotable']:,}"],
        ["Total Covered RN Need (FTE)", f"{m['rn_need_total']:,.0f}"],
        ["States covered", f"{len(m['states'])} ({', '.join(m['states'][:6])}{'...' if len(m['states'])>6 else ''})"],
        ["Cohort visa-exempt share (η)", f"{cohort.eta:.2f}  (F-1, IRC §3121(b)(19))"],
        ["FICA-eligible months / nurse", f"{cohort.eligible_months or cal.fica_eligible_months_default}"],
        ["Contract term", f"{cal.term_months} months"],
    ]
    scope_table = Table(scope_data, colWidths=[2.8*inch, doc.width - 2.8*inch])
    scope_table.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,0), (0,-1), MUTED),
        ("ALIGN", (1,0), (1,-1), "LEFT"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, LIGHT_BG]),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(scope_table)

    # ---- PAGE 2 ----
    story.append(PageBreak())
    story.append(Paragraph(f"Per-hospital detail — top {min(len(m['feas']), 20)} by Florence revenue", h1))
    story.append(Paragraph(
        "Each hospital priced at its local labor economics. Sorted by total monthly Florence billings.",
        sub
    ))

    feas = m["feas"].sort_values("florence_net_term_account", ascending=False).head(20)
    rows = [["Hospital", "RN Need", "Fee/RN/mo", "FICA/RN/mo", "Offset %", "Net Sav/RN/mo", "Total Mo Fee"]]
    for _, h in feas.iterrows():
        rows.append([
            Paragraph(f"<b>{h['name'][:38]}</b><br/><font size=7 color='#6B7280'>{h['city']}, {h['state']}</font>", body_small),
            f"{h['rn_need']:,.0f}",
            f"${h['florence_monthly_fee_per_rn']:,.0f}",
            f"${h['employer_fica_savings_per_rn_per_month']:,.0f}",
            f"{h['actual_fica_offset_pct']*100:.0f}%",
            f"${h['net_monthly_savings_per_rn']:,.0f}",
            f"${h['monthly_florence_fee_account']/1e6:,.2f}M",
        ])
    detail_table = Table(rows, colWidths=[2.5*inch, 0.6*inch, 0.75*inch, 0.8*inch, 0.6*inch, 0.85*inch, 0.85*inch])
    detail_table.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("BACKGROUND", (0,0), (-1,0), LIGHT_BG),
        ("TEXTCOLOR", (0,0), (-1,0), NAVY),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ("LINEBELOW", (0,0), (-1,0), 0.5, NAVY),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 12))

    # Methodology + sources
    story.append(Paragraph("Methodology", h2))
    story.append(Paragraph(
        f"Florence Workforce Restoration Economics v2 (May 28, 2026). "
        f"<b>Florence Monthly Fee per RN</b> = Suggested Fee, clamped to floor/ceiling, where "
        f"<b>Suggested Fee = Employer FICA Savings ÷ {cal.target_offset_pct:.0%} target</b>. "
        f"Employer FICA savings calculated under IRC §3121(b)(19) for F-1 nonresident-alien RNs during their "
        f"nonresident-alien tax period. Guardrails: ${cal.price_floor_monthly:,.0f} ≤ fee ≤ ${cal.price_ceiling_monthly:,.0f}.",
        body_small
    ))

    story.append(Paragraph("Data sources", h2))
    story.append(Paragraph(
        "Hospital roster: CMS Hospital General Information. Per-hospital salaries, FTE, contract labor: "
        "CMS HCRIS Hospital Provider Cost Report 2023. RN wage benchmarks: BLS OEWS state-level. "
        "Agency rate benchmarks: hybrid (customer-disclosed where available, CommonSpirit anchor, state median).",
        body_small
    ))

    # Compliance block
    story.append(Spacer(1, 8))
    comp_table = Table(
        [[Paragraph(f"<b>Required compliance statement:</b>  {REQUIRED_COMPLIANCE_SENTENCE}", compliance)]],
        colWidths=[doc.width],
    )
    comp_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), WARN_BG),
        ("LINEBEFORE", (0,0), (-1,-1), 3, colors.HexColor("#C97A3B")),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(comp_table)

    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "IRS sources: <a href='https://www.irs.gov/individuals/international-taxpayers/foreign-student-liability-for-social-security-and-medicare-taxes'>Foreign Student Liability for Social Security and Medicare Taxes</a>; "
        "IRC §3121(b)(19); IRS Publication 519; IRS Publication 15 (Circular E). "
        f"Calibration {cal.version} · Mode: {cal.pricing_mode.value} · "
        "Florence does not provide tax, payroll, immigration, or legal advice.",
        ParagraphStyle("foot", parent=body_small, fontSize=7, textColor=MUTED)
    ))

    doc.build(story)
    return output_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_hospital_exec_summary(
    ccn: str, output_dir: Path,
    cal: Optional[Calibration] = None, cohort: Optional[CohortMix] = None,
) -> tuple[Path, Path]:
    cal = cal or Calibration()
    cohort = cohort or CohortMix(eta=1.0)
    u = load_universe()
    u["ccn"] = u["ccn"].astype(str).str.zfill(6)
    ccn = str(ccn).zfill(6)
    rows = u[u["ccn"] == ccn]
    if rows.empty:
        raise ValueError(f"CCN {ccn} not found")
    target_name = rows.iloc[0]["name"]
    scope = f"{rows.iloc[0]['city']}, {rows.iloc[0]['state']} · CCN {ccn}"
    m = _gather(rows, cal, cohort)

    safe = target_name.replace(" ", "_").replace("/", "_")[:48]
    html_path = Path(output_dir) / f"{safe}_exec_summary.html"
    pdf_path = Path(output_dir) / f"{safe}_exec_summary.pdf"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(_render_html(target_name, "Hospital", scope, cal, cohort, m), encoding="utf-8")
    _render_pdf(pdf_path, target_name, "Hospital", scope, cal, cohort, m)
    return html_path, pdf_path


def build_system_exec_summary(
    health_system_id: str, output_dir: Path,
    cal: Optional[Calibration] = None, cohort: Optional[CohortMix] = None,
) -> tuple[Path, Path]:
    cal = cal or Calibration()
    cohort = cohort or CohortMix(eta=1.0)
    u = load_universe()
    rows = u[u["health_system_id"] == health_system_id]
    if rows.empty:
        rows = u[u["health_system"] == health_system_id]
        if rows.empty:
            raise ValueError(f"System {health_system_id!r} not found")
    target_name = rows.iloc[0]["health_system"]
    states = sorted(rows["state"].unique())
    scope = (f"{len(rows)} hospitals across {len(states)} states "
             f"({', '.join(states[:5])}{'...' if len(states) > 5 else ''})")
    m = _gather(rows, cal, cohort)

    safe = target_name.replace(" ", "_").replace("/", "_")[:48]
    html_path = Path(output_dir) / f"{safe}_exec_summary.html"
    pdf_path = Path(output_dir) / f"{safe}_exec_summary.pdf"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(_render_html(target_name, "Health System", scope, cal, cohort, m), encoding="utf-8")
    _render_pdf(pdf_path, target_name, "Health System", scope, cal, cohort, m)
    return html_path, pdf_path


if __name__ == "__main__":
    out = Path("proposals")
    print("Generating Kaiser 2-page exec summary...")
    h, p = build_system_exec_summary("kaiser_permanente", out)
    print(f"  HTML: {h}")
    print(f"  PDF:  {p}")
