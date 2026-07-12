"""
Cross-system comparison report — top 10 systems side-by-side, single page.

Generates PDF + HTML for executive review showing the relative Florence opportunity
across the largest US health systems.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

from pricing_engine import Calibration, CohortMix, REQUIRED_COMPLIANCE_SENTENCE
from pricing_batch import load_universe, price_batch

NAVY = colors.HexColor("#0B2545")
TEAL = colors.HexColor("#1E6091")
ACCENT = colors.HexColor("#2DB8A3")
LIGHT_BG = colors.HexColor("#F0F5FA")
MUTED = colors.HexColor("#6B7280")
BORDER = colors.HexColor("#E2E6EE")


def build_data(n_top: int = 12) -> pd.DataFrame:
    u = load_universe()
    cal = Calibration()
    priced = price_batch(u, CohortMix(eta=1.0), cal)
    feas = priced[priced["feasible"]]
    sys_summary = feas.groupby(["health_system_id", "health_system"]).agg(
        n_facilities=("ccn", "count"),
        states=("state", "nunique"),
        rn_need=("rn_need", "sum"),
        median_agency_premium=("agency_premium_per_hr", "median"),
        median_florence_fee=("florence_monthly_fee_per_rn", "median"),
        median_fica_savings=("employer_fica_savings_per_rn_per_month", "median"),
        median_net_savings=("net_monthly_savings_per_rn", "median"),
        monthly_florence_fee=("monthly_florence_fee_account", "sum"),
        term_florence_fee=("term_florence_fee_account", "sum"),
        term_net_savings=("term_net_savings_account", "sum"),
    ).reset_index().sort_values("term_florence_fee", ascending=False)
    sys_summary = sys_summary[sys_summary["health_system_id"] != "independent"]
    return sys_summary.head(n_top)


def fmt_money(v: float) -> str:
    if v >= 1e9: return f"${v/1e9:,.2f}B"
    if v >= 1e6: return f"${v/1e6:,.2f}M"
    if v >= 1e3: return f"${v/1e3:,.2f}K"
    return f"${v:,.2f}"


def render_html(df: pd.DataFrame, output: Path) -> Path:
    rows = ""
    for i, (_, r) in enumerate(df.iterrows(), 1):
        ratio = (r["term_net_savings"] / r["term_florence_fee"]) if r["term_florence_fee"] > 0 else 0
        rows += f"""
        <tr>
          <td class="num">{i}</td>
          <td><b>{r['health_system']}</b></td>
          <td class="num">{r['n_facilities']}</td>
          <td class="num">{r['states']}</td>
          <td class="num">{r['rn_need']:,.0f}</td>
          <td class="num">${r['median_agency_premium']:,.0f}/hr</td>
          <td class="num">${r['median_florence_fee']:,.0f}/mo</td>
          <td class="num">${r['median_fica_savings']:,.0f}/mo</td>
          <td class="num">${r['median_net_savings']:,.0f}/mo</td>
          <td class="num"><b>{fmt_money(r['monthly_florence_fee'])}/mo</b></td>
          <td class="num"><b>{fmt_money(r['term_florence_fee'])}</b></td>
          <td class="num">{fmt_money(r['term_net_savings'])}</td>
          <td class="num"><b>{ratio:.1f}×</b></td>
        </tr>
        """
    html = f"""<!DOCTYPE html><html><head>
<title>Florence Cross-System Comparison</title>
<style>
@page {{ size: landscape; margin: 0.4in; }}
body {{ font-family: -apple-system, "Inter", sans-serif; font-size: 11px;
       margin: 0; padding: 0.4in; color: #1A2230; }}
h1 {{ color: #0B2545; margin: 0 0 4px; font-size: 22px; }}
.subtitle {{ color: #6B7280; font-size: 11px; margin-bottom: 16px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
th, td {{ padding: 6px 8px; border-bottom: 1px solid #E2E6EE; }}
th {{ background: #F0F5FA; color: #0B2545; text-align: left;
      font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.compliance {{ background: #FFF8E6; border-left: 3px solid #C97A3B;
              padding: 10px 14px; font-size: 9px; color: #6B5824;
              margin-top: 16px; line-height: 1.5; }}
.footer {{ font-size: 8px; color: #6B7280; margin-top: 12px; border-top: 1px solid #E2E6EE; padding-top: 8px; }}
</style></head><body>

<h1>Florence Cross-System Comparison — Top {len(df)} Health Systems</h1>
<div class="subtitle">Pricing under Florence Workforce Restoration Economics v2 (F-1 cohort, η=1.0, 50% FICA offset target, 24-month term). Generated {date.today().isoformat()}.</div>

<table>
  <thead>
    <tr>
      <th class="num">#</th>
      <th>Health System</th>
      <th class="num">Facilities</th>
      <th class="num">States</th>
      <th class="num">RN Need (FTE)</th>
      <th class="num">Median Agency Premium</th>
      <th class="num">Median Fee / RN / mo</th>
      <th class="num">Median FICA / RN / mo</th>
      <th class="num">Median Net Savings / RN / mo</th>
      <th class="num">Total Monthly Florence</th>
      <th class="num">Total 24-mo Florence Fee</th>
      <th class="num">24-mo Hospital Net Savings</th>
      <th class="num">Savings : Fee Ratio</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<div class="compliance">
  <b>Required compliance statement:</b> {REQUIRED_COMPLIANCE_SENTENCE}
</div>

<div class="footer">
  Data sources: CMS HCRIS Hospital 2552-10 NMRC line 01100 (per-hospital agency rates) + BLS OEWS May 2025 MSA wages +
  Kaiser-specific AMN $622M MSP overlay (other systems' overlays pending disclosure).
  Engine v0.5-methodology-v2-2026-05. Data layer v0.6.
</div>

</body></html>"""
    output.write_text(html, encoding="utf-8")
    return output


def render_pdf(df: pd.DataFrame, output: Path) -> Path:
    doc = BaseDocTemplate(str(output), pagesize=landscape(letter),
                          leftMargin=0.4*inch, rightMargin=0.4*inch,
                          topMargin=0.4*inch, bottomMargin=0.4*inch,
                          title="Florence Cross-System Comparison")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame])])
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18,
                        textColor=NAVY, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10,
                         textColor=MUTED, spaceAfter=10)
    comp = ParagraphStyle("c", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#6B5824"))

    story = [
        Paragraph(f"Florence Cross-System Comparison — Top {len(df)} Health Systems", h1),
        Paragraph(
            f"Pricing under v2 (F-1 cohort, η=1.0, 50% FICA target, 24-month). "
            f"Generated {date.today().isoformat()}.", sub
        ),
    ]

    # Table
    header = ["#", "Health System", "Facil", "States", "RN Need", "Med Agency Prem",
              "Med Fee/RN/mo", "Med FICA/RN/mo", "Med Net Sav/RN/mo",
              "Mo Florence", "24-mo Fee", "24-mo Net Save", "Ratio"]
    data = [header]
    for i, (_, r) in enumerate(df.iterrows(), 1):
        ratio = (r["term_net_savings"] / r["term_florence_fee"]) if r["term_florence_fee"] > 0 else 0
        data.append([
            i, r["health_system"][:30], r["n_facilities"], r["states"],
            f"{r['rn_need']:,.0f}",
            f"${r['median_agency_premium']:,.0f}",
            f"${r['median_florence_fee']:,.0f}",
            f"${r['median_fica_savings']:,.0f}",
            f"${r['median_net_savings']:,.0f}",
            fmt_money(r["monthly_florence_fee"]),
            fmt_money(r["term_florence_fee"]),
            fmt_money(r["term_net_savings"]),
            f"{ratio:.1f}×",
        ])
    col_widths = [0.25*inch, 1.6*inch, 0.45*inch, 0.45*inch, 0.7*inch,
                  0.85*inch, 0.85*inch, 0.85*inch, 0.95*inch,
                  0.85*inch, 0.85*inch, 0.85*inch, 0.5*inch]
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), LIGHT_BG),
        ("TEXTCOLOR", (0,0), (-1,0), NAVY),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (0,-1), "RIGHT"),
        ("ALIGN", (2,0), (-1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ("LINEBELOW", (0,0), (-1,0), 1, NAVY),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"<b>Required compliance:</b> {REQUIRED_COMPLIANCE_SENTENCE}", comp
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Data sources: CMS HCRIS Hospital 2552-10 NMRC line 01100 + BLS OEWS May 2025 MSA + Kaiser AMN $622M MSP overlay. "
        "Engine v0.5-methodology-v2-2026-05. Data layer v0.6.",
        ParagraphStyle("foot", parent=styles["Normal"], fontSize=7, textColor=MUTED)
    ))
    doc.build(story)
    return output


def main() -> None:
    print("Building cross-system comparison report...")
    df = build_data(n_top=12)
    out_dir = Path("proposals")
    html_path = render_html(df, out_dir / "Cross_System_Comparison_v0.6.html")
    pdf_path = render_pdf(df, out_dir / "Cross_System_Comparison_v0.6.pdf")
    print(f"  HTML: {html_path}")
    print(f"  PDF:  {pdf_path}")
    print(f"  Top {len(df)} systems by 24-month Florence fee:")
    for _, r in df.iterrows():
        print(f"    {r['health_system'][:40]:40} fee={fmt_money(r['term_florence_fee']):>7}  "
              f"savings={fmt_money(r['term_net_savings']):>7}")


if __name__ == "__main__":
    main()
