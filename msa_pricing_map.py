"""
Florence — Nationwide Market-Adjusted RN Rates, MSA by MSA.

Interactive choropleth-style bubble map for the AMN conversation. Three layers:
  1. Florence rate            — target monthly fee per RN (the wholesale rate)
  2. +20% partner (AMN)       — Florence rate x 1.20 (AMN wholesale channel)
  3. FICA-effective (net)     — employer's effective cost after the FICA offset

Each MSA (CBSA) is one bubble at its facility centroid, colored by the selected
layer's rate (heat scale) and sized by modeled RN need. Toggle layers with the
buttons. Renders a standalone, self-contained HTML (opens offline).
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go

AMN_MARKUP = 0.20  # pricing_engine.Calibration.amn_partner_markup_pct

# Florence brand heat scale: light teal -> teal -> purple -> deep purple
HEAT = [[0.0, "#CFF5F3"], [0.35, "#0ABAB5"], [0.70, "#7340C4"], [1.0, "#5B2DA8"]]
NAVY, INK = "#0B2545", "#101828"


def build_msa_table(recs_path="data/recommendations.parquet",
                    universe_path="data/hospital_universe.csv") -> pd.DataFrame:
    r = pd.read_parquet(recs_path)
    u = pd.read_csv(universe_path, dtype={"ccn": str})
    r["ccn"] = r["ccn"].astype(str).str.zfill(6)
    u["ccn"] = u["ccn"].astype(str).str.zfill(6)
    f = r[r["feasible"] == True].merge(
        u[["ccn", "cbsa_code", "cbsa_title", "lat", "lon", "agency_premium_per_hour"]],
        on="ccn", how="left")
    # MSA only: real CBSA code, has coords + price, drop the rural catch-all
    f = f[f["cbsa_code"].notna() & f["lat"].notna() & f["lon"].notna()
          & f["target_monthly_fee"].notna()
          & (f["cbsa_title"].fillna("") != "Rural / Nonmetro")].copy()
    f["lat"] = f["lat"].astype(float); f["lon"] = f["lon"].astype(float)

    g = f.groupby("cbsa_code").agg(
        msa=("cbsa_title", "first"),
        lat=("lat", "mean"), lon=("lon", "mean"),
        florence=("target_monthly_fee", "median"),
        effective=("target_fica_adjusted_effective_cost", "median"),
        agency_prem=("agency_premium_per_hour", "median"),
        n_fac=("ccn", "count"),
        rn_need=("rn_need", "sum"),
    ).reset_index()
    g["partner"] = g["florence"] * (1 + AMN_MARKUP)
    g = g[(g["lat"].between(18, 72)) & (g["lon"].between(-180, -65))]  # CONUS+AK/HI
    return g.sort_values("rn_need", ascending=False).reset_index(drop=True)


def build_figure(g: pd.DataFrame) -> go.Figure:
    LAYERS = [
        ("florence",  "Florence rate", "Florence rate&nbsp;($/RN/mo)"),
        ("partner",   "+20% partner channel (AMN)", "AMN partner rate&nbsp;($/RN/mo)"),
        ("effective", "FICA-effective (net to hospital)", "FICA-effective&nbsp;($/RN/mo)"),
    ]
    # bubble size by RN need (area-scaled)
    size = np.sqrt(g["rn_need"].clip(lower=1))
    sizeref = 2.0 * size.max() / (38.0 ** 2)

    custom = np.stack([g["msa"], g["florence"], g["effective"], g["partner"],
                       g["n_fac"], g["rn_need"], g["agency_prem"]], axis=-1)
    hover = ("<b>%{customdata[0]}</b><br>"
             "Florence rate: <b>$%{customdata[1]:,.0f}</b>/RN/mo<br>"
             "+20% partner (AMN): $%{customdata[3]:,.0f}/RN/mo<br>"
             "FICA-effective (net): $%{customdata[2]:,.0f}/RN/mo<br>"
             "<span style='color:#667085'>%{customdata[4]} facilities · "
             "%{customdata[5]:,.0f} RN need · agency premium $%{customdata[6]:,.2f}/hr</span>"
             "<extra></extra>")

    fig = go.Figure()
    for col, _, cbar in LAYERS:
        vals = g[col]
        fig.add_trace(go.Scattermapbox(
            lon=g["lon"], lat=g["lat"], customdata=custom, hovertemplate=hover,
            marker=dict(
                size=size, sizemode="area", sizeref=sizeref, sizemin=3,
                color=vals, colorscale=HEAT,
                cmin=float(np.percentile(vals, 4)), cmax=float(np.percentile(vals, 96)),
                colorbar=dict(title=dict(text=cbar, side="right", font=dict(size=12)),
                              thickness=14, len=0.55, x=0.99, tickprefix="$",
                              tickfont=dict(size=10)),
                opacity=0.9),
            visible=(col == "florence"),
        ))

    n_msa = len(g)
    med_f, med_p, med_e = g["florence"].median(), g["partner"].median(), g["effective"].median()
    buttons = []
    for i, (col, label, _) in enumerate(LAYERS):
        vis = [j == i for j in range(len(LAYERS))]
        buttons.append(dict(label=label, method="update", args=[{"visible": vis}]))

    fig.update_layout(
        title=dict(text=f"<b>Florence — Market-Adjusted RN Rates · {n_msa} U.S. Metro Areas</b>",
                   x=0.015, xanchor="left",
                   font=dict(family="Georgia, serif", size=19, color=NAVY)),
        updatemenus=[dict(type="buttons", direction="right", x=0.015, xanchor="left",
                          y=1.0, yanchor="bottom", showactive=True, borderwidth=1,
                          bgcolor="#F2F4F7", bordercolor="#D0D5DD",
                          font=dict(size=11, color=INK), pad=dict(t=3, b=3, l=4, r=4),
                          buttons=buttons)],
        mapbox=dict(style="carto-positron", center=dict(lat=39.5, lon=-98.5), zoom=3.05),
        paper_bgcolor="white", margin=dict(l=10, r=10, t=104, b=74), height=720,
        annotations=[dict(
            x=0.015, y=-0.05, xref="paper", yref="paper", showarrow=False,
            xanchor="left", align="left", font=dict(size=11, color="#475467"),
            text=(f"<b>National medians</b> — Florence ${med_f:,.0f} &nbsp;·&nbsp; +20% AMN partner "
                  f"${med_p:,.0f} &nbsp;·&nbsp; FICA-effective ${med_e:,.0f} &nbsp;(per RN / month) "
                  f"&nbsp;·&nbsp; bubble size = modeled RN need<br>"
                  "<span style='color:#667085'>Each bubble is one metro area (CBSA), priced from local "
                  "agency-premium and wage data. Florence rate = wholesale monthly fee per RN · "
                  "AMN partner channel = +20% atop · FICA-effective = employer net after the F-1 "
                  "payroll-tax offset. Source: Florence Workforce Economist · per-RN / month, 24-month term.</span>"))],
    )
    return fig


def write_html(out_path: str,
               recs_path="data/recommendations.parquet",
               universe_path="data/hospital_universe.csv") -> dict:
    g = build_msa_table(recs_path, universe_path)
    fig = build_figure(g)
    fig.write_html(out_path, include_plotlyjs=True, full_html=True,
                   config={"displayModeBar": True, "scrollZoom": True,
                           "toImageButtonOptions": {"format": "png", "scale": 2,
                                                    "filename": "florence-msa-rates"}})
    return {"msas": len(g), "median_florence": float(g["florence"].median()),
            "median_partner": float(g["partner"].median()),
            "median_effective": float(g["effective"].median()),
            "out": out_path}


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "Florence - MSA Pricing Map.html"
    info = write_html(out)
    print(f"WROTE {info['out']}")
    print(f"  MSAs: {info['msas']}")
    print(f"  national medians  —  Florence ${info['median_florence']:,.0f}  ·  "
          f"+20% partner ${info['median_partner']:,.0f}  ·  "
          f"FICA-effective ${info['median_effective']:,.0f}  (per RN/mo)")
