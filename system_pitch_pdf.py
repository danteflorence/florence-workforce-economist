"""
One-page branded pitch PDF for a single health system, generated from the
Market Map's facility set. Customer-facing → leads with the QUOTED price at the
chosen channel (direct Florence vs +partner markup) and the agency comparison.
No FICA / visa / tax mechanism on this surface (that stays internal).
"""
from __future__ import annotations
import io
import numpy as np
import pandas as pd

NAVY = "#0B2545"; TEAL = "#0ABAB5"; PURPLE = "#5B2DA8"; INK = "#101828"; MUTE = "#667085"


def _footprint(d: pd.DataFrame, width: float = 446, height: float = 176):
    """Native reportlab dot-map of the system's facilities (no matplotlib dep)."""
    from reportlab.graphics.shapes import Drawing, Circle, Rect
    from reportlab.lib import colors
    LON0, LON1, LAT0, LAT1 = -162.0, -66.0, 17.0, 50.0
    dr = Drawing(width, height)
    dr.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#F4F8FB"),
                strokeColor=colors.HexColor("#E4E7EC"), strokeWidth=0.6))
    q = d["_quote"]
    qlo, qhi = float(q.quantile(0.05)), float(q.quantile(0.95))
    span = max(qhi - qlo, 1.0)
    c0, c1 = (0x0A, 0xBA, 0xB5), (0x5B, 0x2D, 0xA8)  # teal -> purple
    sizes = np.sqrt(d["rn_need"].clip(lower=1))
    smax = float(sizes.max()) or 1.0
    for _, r in d.iterrows():
        x = (float(r["lon"]) - LON0) / (LON1 - LON0) * width
        y = (float(r["lat"]) - LAT0) / (LAT1 - LAT0) * height
        if not (0 <= x <= width and 0 <= y <= height):
            continue
        t = max(0.0, min(1.0, (float(r["_quote"]) - qlo) / span))
        col = colors.Color(*[(c0[i] + (c1[i] - c0[i]) * t) / 255.0 for i in range(3)])
        rad = 1.8 + 6.0 * (np.sqrt(max(float(r["rn_need"]), 1.0)) / smax)
        dr.add(Circle(x, y, rad, fillColor=col, fillOpacity=0.82,
                      strokeColor=colors.white, strokeWidth=0.4))
    return dr


def render(system: str, d: pd.DataFrame, via_partner: bool, markup: float) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image)
    from reportlab.lib.styles import ParagraphStyle

    d = d.copy()
    gross = d["partner"] if via_partner else d["florence"]
    d["_quote"] = gross
    channel = (f"via distribution partner (+{markup:.0%} atop the Florence rate)"
               if via_partner else "direct from Florence")
    n = len(d); states = d["state"].nunique(); rn = float(d["rn_need"].sum())
    med = float(gross.median())
    agency = d["agency_monthly"].dropna() if "agency_monthly" in d else pd.Series(dtype=float)
    save_line = ""
    if len(agency):
        sav = (d["agency_monthly"] - gross).dropna()
        if len(sav):
            save_line = (f"At hospital sites, that is about ${sav.median():,.0f}/RN/month below the "
                         f"current agency premium — permanent staff, not rotating travelers.")

    def P(t, s): return Paragraph(t, s)
    H = ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=20, leading=24,
                       textColor=colors.HexColor(NAVY), spaceBefore=6, spaceAfter=6)
    SUB = ParagraphStyle("SUB", fontName="Helvetica", fontSize=11, leading=14,
                         textColor=colors.HexColor(MUTE), spaceAfter=12)
    BODY = ParagraphStyle("B", fontName="Helvetica", fontSize=10.5, textColor=colors.HexColor(INK), spaceAfter=8, leading=14)
    SMALL = ParagraphStyle("S", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor(MUTE), leading=11)
    KN = ParagraphStyle("KN", fontName="Helvetica-Bold", fontSize=18, leading=22,
                        textColor=colors.HexColor(PURPLE), alignment=1)
    KL = ParagraphStyle("KL", fontName="Helvetica", fontSize=8, leading=11,
                        textColor=colors.HexColor(MUTE), alignment=1)

    story = [
        P("Florence", ParagraphStyle("logo", fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor(TEAL))),
        P(f"Permanent RN capacity for {system}", H),
        P(f"{n:,} facilities · {states} states · pricing shown {channel}.", SUB),
    ]

    def kpi(v, l):
        return Table([[P(v, KN)], [P(l, KL)]], colWidths=[2.0 * inch],
                     style=TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    kpis = Table([[kpi(f"{n:,}", "FACILITIES"), kpi(f"{states}", "STATES"),
                   kpi(f"${med:,.0f}", "QUOTED $/RN/MONTH"), kpi(f"{rn:,.0f}", "RN OPPORTUNITY")]],
                 colWidths=[2.0 * inch] * 4)
    kpis.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E4E7EC")),
                              ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E4E7EC")),
                              ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [kpis, Spacer(1, 10)]

    story += [P(f"Florence places permanent, U.S.-licensed registered nurses directly onto "
                f"{system}'s payroll at a market-adjusted <b>${med:,.0f} per RN per month</b> "
                f"({channel}). {save_line}", BODY)]

    story += [_footprint(d), Spacer(1, 8)]

    top = d.sort_values("rn_need", ascending=False).head(12)
    rows = [[P("<b>Facility</b>", SMALL), P("<b>City</b>", SMALL), P("<b>State</b>", SMALL),
             P("<b>Quoted $/RN/mo</b>", SMALL)]]
    for _, r in top.iterrows():
        rows.append([P(str(r["name"])[:42], SMALL), P(str(r["city"])[:18], SMALL),
                     P(str(r["state"]), SMALL), P(f"${r['_quote']:,.0f}", SMALL)])
    tbl = Table(rows, colWidths=[3.3 * inch, 1.7 * inch, 0.7 * inch, 1.3 * inch])
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E4E7EC")),
                             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
                             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                             ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
    story += [tbl]
    if n > 12:
        story += [Spacer(1, 3), P(f"… and {n - 12:,} more facilities.", SMALL)]
    story += [Spacer(1, 10),
              P("Florence Workforce Economist · market-adjusted RN pricing, per RN / month, 24-month term. "
                "Final per-facility pricing confirmed at proposal.", SMALL)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.5 * inch,
                      leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                      title=f"Florence — {system} pitch").build(story)
    return buf.getvalue()
