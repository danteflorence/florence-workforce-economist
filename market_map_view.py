"""
Market Map — interactive nationwide RN-rate map for the internal app.

Capabilities (all live):
  • Facility drill-down + city zoom  — MSA bubbles or individual facilities,
    inpatient + outpatient, on a zoomable Carto base.
  • Live pricing sliders             — FICA-offset %, partner markup %, fee
    floor/ceiling recolor the map instantly.
  • Filters & metro search           — setting, facility type, state, rate band,
    type-a-metro-to-fly-there.
  • Agency-spread + detail/export    — color by savings vs agency, browse the
    facility table, download the current view as CSV.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import facility_map_data as FD

HEAT = [[0.0, "#CFF5F3"], [0.35, "#0ABAB5"], [0.70, "#7340C4"], [1.0, "#5B2DA8"]]
SPREAD_SCALE = [[0.0, "#F2C9C2"], [0.5, "#CFF5F3"], [1.0, "#067F7B"]]
NAVY = "#0B2545"
LAYER_COL = {"Florence rate": "florence", "+20% partner (AMN)": "partner",
             "FICA-effective (net)": "effective"}


@st.cache_data(show_spinner=False)
def _facilities() -> pd.DataFrame:
    return FD.load_facilities()


def _focus(d: pd.DataFrame, metro_q: str):
    """Return (center dict, zoom) — fly to a searched metro, else fit the data."""
    if metro_q:
        hit = d[d["cbsa_title"].fillna("").str.contains(metro_q.strip(), case=False, regex=False)]
        if len(hit):
            return dict(lat=float(hit["lat"].mean()), lon=float(hit["lon"].mean())), 8.0
    if not len(d):
        return dict(lat=39.5, lon=-98.5), 3.1
    lat0, lon0 = float(d["lat"].mean()), float(d["lon"].mean())
    span = max(float(d["lat"].max() - d["lat"].min()), float(d["lon"].max() - d["lon"].min()), 0.5)
    zoom = 3.1 if span > 35 else 4.2 if span > 18 else 5.6 if span > 7 else 7.0
    return dict(lat=lat0, lon=lon0), zoom


def _map_figure(d: pd.DataFrame, view: str, col: str, color_col: str,
                label: str, spread: bool, metro_q: str) -> go.Figure:
    diverging = spread and color_col == "spread_vs_agency"
    scale = SPREAD_SCALE if diverging else HEAT
    cbar_title = ("Savings vs agency&nbsp;($/RN/mo)" if diverging
                  else f"{label}&nbsp;($/RN/mo)")

    if view == "MSA bubbles":
        g = FD.msa_rollup(d)
        if not len(g):
            g = pd.DataFrame(columns=["lat", "lon", "florence", "partner", "effective",
                                      "msa", "n_fac", "rn_need", "agency_prem"])
        cc = col if col in g.columns else "florence"
        color_vals = g[cc]
        size = np.sqrt(g["rn_need"].clip(lower=1)) if len(g) else pd.Series(dtype=float)
        custom = (np.stack([g["msa"], g["florence"], g["partner"], g["effective"],
                            g["n_fac"], g["rn_need"]], axis=-1) if len(g) else None)
        hover = ("<b>%{customdata[0]}</b><br>"
                 "Florence $%{customdata[1]:,.0f} · +20% $%{customdata[2]:,.0f} · "
                 "FICA-eff $%{customdata[3]:,.0f} /RN/mo<br>"
                 "%{customdata[4]} facilities · %{customdata[5]:,.0f} RN need<extra></extra>")
        lat, lon, mx = g["lat"], g["lon"], 42.0
    else:
        g = d
        color_vals = g[color_col]
        size = np.sqrt(g["rn_need"].clip(lower=1)) if len(g) else pd.Series(dtype=float)
        custom = (np.stack([g["name"], g["city"], g["state"], g["ftype"],
                            g["florence"], g["partner"], g["effective"]], axis=-1) if len(g) else None)
        hover = ("<b>%{customdata[0]}</b><br>%{customdata[1]}, %{customdata[2]} · %{customdata[3]}<br>"
                 "Florence $%{customdata[4]:,.0f} · +20% $%{customdata[5]:,.0f} · "
                 "FICA-eff $%{customdata[6]:,.0f} /RN/mo<extra></extra>")
        lat, lon, mx = g["lat"], g["lon"], 26.0

    sizeref = (2.0 * float(size.max()) / (mx ** 2)) if len(size) and size.max() > 0 else 1.0
    cmin = float(np.nanpercentile(color_vals, 3)) if len(color_vals) else 0.0
    cmax = float(np.nanpercentile(color_vals, 97)) if len(color_vals) else 1.0

    fig = go.Figure(go.Scattermapbox(
        lat=lat, lon=lon, mode="markers", customdata=custom, hovertemplate=hover,
        marker=dict(size=size, sizemode="area", sizeref=sizeref, sizemin=3,
                    color=color_vals, colorscale=scale, cmin=cmin, cmax=cmax,
                    opacity=0.85,
                    colorbar=dict(title=dict(text=cbar_title, side="right"),
                                  thickness=14, len=0.7, tickprefix="$"))))
    center, zoom = _focus(d, metro_q)
    fig.update_layout(mapbox=dict(style="carto-positron", center=center, zoom=zoom),
                      margin=dict(l=0, r=0, t=0, b=0), height=620,
                      paper_bgcolor="white")
    return fig


def render() -> None:
    st.markdown(f"<h2 style='color:{NAVY};font-family:Georgia,serif;margin-bottom:2px'>"
                "Market Map — Nationwide RN Rates</h2>"
                "<div style='color:#475467;margin-bottom:10px'>Market-adjusted Florence pricing across "
                "every U.S. metro, down to the individual facility — inpatient and outpatient.</div>",
                unsafe_allow_html=True)
    df = _facilities()

    c1, c2, c3 = st.columns([1.1, 1, 1.4])
    layer = c1.radio("Rate layer", list(LAYER_COL), index=0, key="mm_layer")
    view = c2.radio("View", ["MSA bubbles", "Individual facilities"], index=0, key="mm_view")
    kinds = c3.multiselect("Setting", ["Inpatient", "Outpatient"],
                           default=["Inpatient", "Outpatient"], key="mm_kinds")

    with st.expander("Pricing assumptions — drag to model a different deal", expanded=False):
        s1, s2, s3, s4 = st.columns(4)
        offset = s1.slider("FICA-offset target %", 20, 80, 40, 5, key="mm_offset") / 100.0
        markup = s2.slider("Partner markup %", 0, 50, 20, 5, key="mm_markup") / 100.0
        floor = float(s3.slider("Fee floor $/RN/mo", 500, 1500, 750, 50, key="mm_floor"))
        ceiling = float(s4.slider("Fee ceiling $/RN/mo", 1500, 4000, 2000, 100, key="mm_ceiling"))
        if (offset, markup, floor, ceiling) != (0.40, 0.20, 750.0, 2000.0):
            st.caption("⚙️ What-if mode — rates recomputed uniformly from local FICA savings "
                       "(default calibration shows the engine's per-facility rates).")

    f1, f2, f3 = st.columns([1.4, 1.4, 1.6])
    ftypes = f1.multiselect("Facility type", sorted(df["ftype"].dropna().unique()),
                            default=[], key="mm_ftype")
    states = f2.multiselect("State", sorted(df["state"].dropna().unique()),
                            default=[], key="mm_states")
    metro_q = f3.text_input("Find a metro (flies the map there)", "", key="mm_metro")

    spread = st.checkbox("Color by savings vs current agency spend (inpatient only)",
                         value=False, key="mm_spread")

    # ---- filter + reprice ----
    d = df
    if kinds:
        d = d[d["kind"].isin(kinds)]
    if ftypes:
        d = d[d["ftype"].isin(ftypes)]
    if states:
        d = d[d["state"].isin(states)]
    if spread:
        d = d[d["agency_prem_hr"].notna()]
    d = FD.reprice(d, offset, markup, floor, ceiling)
    col = LAYER_COL[layer]
    color_col = "spread_vs_agency" if spread else col

    if not len(d):
        st.warning("No facilities match these filters. Loosen the setting, type or state filters.")
        return

    # rate-band slider
    lo = int(np.nanpercentile(d[col], 1)); hi = int(np.nanpercentile(d[col], 99))
    if hi > lo:
        band = st.slider(f"{layer} band ($/RN/mo)", lo, hi, (lo, hi), key="mm_band")
        d = d[(d[col] >= band[0]) & (d[col] <= band[1])]
    if not len(d):
        st.warning("No facilities in that rate band.")
        return

    # cap individual-facility rendering for performance
    note = ""
    if view == "Individual facilities" and len(d) > 20000:
        d_plot = d.nlargest(20000, "rn_need")
        note = f"Showing the 20,000 largest of {len(d):,} facilities — filter by state/type to see all."
    else:
        d_plot = d

    # ---- KPIs ----
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Facilities in view", f"{len(d):,}")
    k2.metric("MSAs", f"{d['cbsa_title'].nunique():,}")
    k3.metric(f"Median {layer.lower()}", f"${d[col].median():,.0f}/RN/mo")
    k4.metric("Total modeled RN need", f"{d['rn_need'].sum():,.0f}")

    st.plotly_chart(_map_figure(d_plot, view, col, color_col, layer, spread, metro_q),
                    use_container_width=True, key="mm_chart")
    if note:
        st.caption(note)

    # ---- detail table + CSV export ----
    with st.expander(f"Facility detail & export ({len(d):,} rows)", expanded=False):
        cols = ["name", "city", "state", "kind", "ftype", "cbsa_title",
                "florence", "partner", "effective", "rn_need"]
        tbl = d[cols].rename(columns={
            "name": "Facility", "city": "City", "state": "State", "kind": "Setting",
            "ftype": "Type", "cbsa_title": "Metro", "florence": "Florence $/RN/mo",
            "partner": "+20% partner", "effective": "FICA-effective", "rn_need": "RN need"
        }).sort_values("RN need", ascending=False)
        st.dataframe(tbl.head(500), use_container_width=True, hide_index=True)
        st.download_button("Download this view (CSV)", tbl.to_csv(index=False).encode(),
                           file_name="florence_market_rates.csv", mime="text/csv",
                           key="mm_csv")
