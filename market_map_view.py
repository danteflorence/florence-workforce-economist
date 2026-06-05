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
LAYER_COL = {"Florence rate": "florence", "+20% distribution partner": "partner",
             "FICA-effective (net)": "effective"}


@st.cache_data(show_spinner=False)
def _facilities() -> pd.DataFrame:
    return FD.load_facilities()


def _map_figure(d: pd.DataFrame, view: str, col: str, color_col: str,
                label: str, spread: bool) -> go.Figure:
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

    fig = go.Figure(go.Scattergeo(
        lat=lat, lon=lon, mode="markers", customdata=custom, hovertemplate=hover,
        marker=dict(size=size, sizemode="area", sizeref=sizeref, sizemin=3,
                    color=color_vals, colorscale=scale, cmin=cmin, cmax=cmax,
                    opacity=0.9, line=dict(width=0.3, color="rgba(255,255,255,0.55)"),
                    colorbar=dict(title=dict(text=cbar_title, side="right"),
                                  thickness=14, len=0.7, tickprefix="$"))))
    fig.update_layout(
        geo=dict(scope="usa", projection_type="albers usa", bgcolor="rgba(0,0,0,0)",
                 landcolor="#F7FAFC", lakecolor="#EAF3F8", subunitcolor="#D7DEE6",
                 countrycolor="#C2CCD6", showlakes=True, showland=True, showsubunits=True),
        margin=dict(l=0, r=0, t=0, b=0), height=640, paper_bgcolor="white")
    return fig


def render() -> None:
    st.markdown(f"<h2 style='color:{NAVY};font-family:Georgia,serif;margin-bottom:2px'>"
                "Market Map — Nationwide RN Rates</h2>"
                "<div style='color:#475467;margin-bottom:10px'>Market-adjusted Florence pricing across "
                "every U.S. metro, down to the individual facility — inpatient and outpatient.</div>",
                unsafe_allow_html=True)
    df = _facilities()

    if st.session_state.get("mm_demo"):
        _render_demo(df)
        return
    st.button("🎬  Launch demo mode — scripted walkthrough (Kaiser Permanente)",
              key="mm_demo_enter", type="primary",
              on_click=lambda: st.session_state.update(mm_demo=True, mm_demo_step=0))

    c1, c2, c3 = st.columns([1.1, 1, 1.4])
    layer = c1.radio("Rate layer", list(LAYER_COL), index=0, key="mm_layer")
    view = c2.radio("View", ["MSA bubbles", "Individual facilities"], index=0, key="mm_view")
    kinds = c3.multiselect("Setting", ["Inpatient", "Outpatient"],
                           default=["Inpatient", "Outpatient"], key="mm_kinds")

    # Health-system search: searchable dropdown of real system names (type to filter)
    _counts = df["health_system"].fillna("").value_counts()
    _sys_opts = [s for s in _counts.index if s and s != "Independent / Unknown"]
    SYS_ALL = "— All systems —"
    system = st.selectbox(
        "Health system — type to find one (e.g. Kaiser Permanente, Tenet, Advocate)",
        [SYS_ALL] + _sys_opts,
        format_func=lambda s: s if s == SYS_ALL else f"{s}   ·   {_counts[s]:,} facilities",
        key="mm_system")

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
    metro_q = f3.text_input("Find a metro (filters to it)", "", key="mm_metro")

    spread = st.checkbox("Color by savings vs current agency spend (inpatient only)",
                         value=False, key="mm_spread")

    # Quote channel — does a distribution partner sit between Florence and the employer?
    via_partner = st.radio(
        "Quote channel — price to the health-system employer",
        ["Direct — Florence rate", f"Via distribution partner (+{int(markup * 100)}% atop)"],
        index=0, horizontal=True, key="mm_channel").startswith("Via")

    # ---- filter + reprice ----
    d = df
    if kinds:
        d = d[d["kind"].isin(kinds)]
    if ftypes:
        d = d[d["ftype"].isin(ftypes)]
    if states:
        d = d[d["state"].isin(states)]
    if metro_q:
        d = d[d["cbsa_title"].fillna("").str.contains(metro_q.strip(), case=False, regex=False)]
    if system != SYS_ALL:
        d = d[d["health_system"] == system]
    if spread:
        d = d[d["agency_prem_hr"].notna()]
    d = FD.reprice(d, offset, markup, floor, ceiling)
    # employer-facing price = wholesale Florence rate, or +partner markup if a partner is in the channel
    d["employer_price"] = d["partner"] if via_partner else d["florence"]
    d["employer_effective"] = (d["employer_price"] - d["fica_savings"]).clip(lower=0)
    col = LAYER_COL[layer]
    color_col = "spread_vs_agency" if spread else col

    if not len(d):
        st.warning("No facilities match these filters. Loosen the setting, type or state filters.")
        return

    # rate-band slider — default spans the full range so nothing is hidden up front
    lo = int(np.floor(d[col].min())); hi = int(np.ceil(d[col].max()))
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

    if system != SYS_ALL:
        chan = "via partner" if via_partner else "direct"
        st.markdown(f"**{system}** — {len(d):,} facilities across {d['state'].nunique()} states "
                    f"· median quote (${chan}) ${d['employer_price'].median():,.0f}/RN/mo. "
                    "Switch **View** to *Individual facilities* to see each site.")
        e1, e2 = st.columns([1, 3])
        if e1.button("Generate pitch PDF", key="mm_pdf_btn"):
            import system_pitch_pdf as _spp
            st.session_state["mm_pdf"] = _spp.render(system, d, via_partner, markup)
            st.session_state["mm_pdf_name"] = f"Florence - {system} pitch.pdf"
        if st.session_state.get("mm_pdf"):
            e2.download_button("⬇ Download pitch PDF", st.session_state["mm_pdf"],
                               file_name=st.session_state.get("mm_pdf_name", "pitch.pdf"),
                               mime="application/pdf", key="mm_pdf_dl")

    st.plotly_chart(_map_figure(d_plot, view, col, color_col, layer, spread),
                    use_container_width=True, key="mm_chart",
                    config={"scrollZoom": True, "displayModeBar": True})
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

    # ---- compare health systems side by side ----
    with st.expander("Compare health systems side by side", expanded=False):
        cmp = st.multiselect("Pick 2–4 systems (e.g. Kaiser Permanente vs Providence)",
                             _sys_opts, default=[], max_selections=4, key="mm_cmp")
        st.caption(f"Quotes shown {'via distribution partner (+'+str(int(markup*100))+'%)' if via_partner else 'direct from Florence'}.")
        if len(cmp) >= 2:
            rows = []
            for s in cmp:
                ds = FD.reprice(df[df["health_system"] == s], offset, markup, floor, ceiling)
                g = ds["partner"] if via_partner else ds["florence"]
                rows.append({"System": s, "Facilities": len(ds), "States": ds["state"].nunique(),
                             "RN need": int(ds["rn_need"].sum()),
                             "Quoted $/RN/mo": int(g.median()),
                             "FICA-effective $/RN/mo": int((g - ds["fica_savings"]).clip(lower=0).median())})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            palette = ["#0ABAB5", "#7340C4", "#F2994A", "#0B2545"]
            cfig = go.Figure()
            for i, s in enumerate(cmp):
                ds = df[df["health_system"] == s]
                cfig.add_trace(go.Scattergeo(
                    lat=ds["lat"], lon=ds["lon"], name=s[:26], mode="markers",
                    marker=dict(size=7, color=palette[i % len(palette)], opacity=0.82,
                                line=dict(width=0.3, color="rgba(255,255,255,0.55)")),
                    hovertext=ds["name"], hoverinfo="text+name"))
            cfig.update_layout(
                geo=dict(scope="usa", projection_type="albers usa", bgcolor="rgba(0,0,0,0)",
                         landcolor="#F7FAFC", lakecolor="#EAF3F8", subunitcolor="#D7DEE6",
                         countrycolor="#C2CCD6", showlakes=True, showland=True, showsubunits=True),
                margin=dict(l=0, r=0, t=0, b=0), height=520,
                legend=dict(orientation="h", y=0.99, x=0.01, bgcolor="rgba(255,255,255,0.75)"))
            st.plotly_chart(cfig, use_container_width=True, key="mm_cmp_map",
                            config={"scrollZoom": True})
        else:
            st.caption("Pick at least two systems to compare their footprints and rates.")


def _render_demo(df: pd.DataFrame) -> None:
    """Scripted, audience-aware walkthrough with Kaiser Permanente as the hero."""
    import system_pitch_pdf as _spp
    allp = FD.reprice(df)
    nat_fac, nat_states = len(df), df["state"].nunique()
    nat_med = float(allp["florence"].median())

    HEROES = ["Kaiser Permanente", "Tenet Healthcare", "Sutter Health", "CommonSpirit Health",
              "Advocate Health", "HCA", "Banner Health", "HonorHealth",
              "Cedars Sinai Health System", "Providence", "Trinity Health", "CHRISTUS Health"]
    HERO_DISP = {"HCA": "HCA Healthcare", "Cedars Sinai Health System": "Cedars-Sinai"}
    hc = st.columns([2, 2])
    hero = hc[0].selectbox("Hero account", HEROES,
                           format_func=lambda s: HERO_DISP.get(s, s), key="mm_demo_hero")
    hd = HERO_DISP.get(hero, hero)
    partner = hc[1].radio("Audience", ["Distribution partner", "Investors"],
                          horizontal=True, key="mm_demo_aud").startswith("Distribution")

    kd = FD.reprice(df[df["health_system"] == hero])
    k_fac, k_st = len(kd), kd["state"].nunique()
    k_flor, k_part, k_eff = (float(kd["florence"].median()), float(kd["partner"].median()),
                             float(kd["effective"].median()))
    _sp = (kd["agency_monthly"] - kd["florence"]).dropna()
    k_spread = float(_sp.median()) if len(_sp) else 0.0

    NAT = [("Facilities priced", f"{nat_fac:,}"), ("States", str(nat_states)),
           ("Median Florence rate", f"${nat_med:,.0f}/RN/mo")]
    K = [(f"{hd} facilities", str(k_fac)), ("States", str(k_st)),
         ("Median Florence rate", f"${k_flor:,.0f}/RN/mo")]
    P = [("Direct — Florence", f"${k_flor:,.0f}"), ("+20% partner", f"${k_part:,.0f}"),
         ("Partner margin / RN / mo", f"${k_part - k_flor:,.0f}")]
    S = [("Florence permanent rate", f"${k_flor:,.0f}/RN/mo"),
         ("Saved vs agency premium", f"${k_spread:,.0f}/RN/mo")]
    E = [("Florence rate", f"${k_flor:,.0f}/RN/mo"),
         ("Effective after FICA offset", f"${k_eff:,.0f}/RN/mo")]
    KP, IND, FLO, PART, EFF = hero, "Individual facilities", "Florence rate", "+20% distribution partner", "FICA-effective (net)"

    if partner:
        beats = [
            dict(system=None, view="MSA bubbles", layer=FLO, spread=False, stat=NAT,
                 headline="Market-adjusted rates in every metro you serve",
                 say="Florence prices RN labor in every U.S. metro — 48,870 facilities, inpatient and outpatient. "
                     "Each rate is calibrated to the local wage and agency market, so you can quote anywhere you already operate."),
            dict(system=KP, view=IND, layer=FLO, spread=False, stat=K,
                 headline="Your account — already priced",
                 say=f"Type any system you serve and its facilities light up. {hd}: {k_fac} sites across {k_st} states, each priced to its local market."),
            dict(system=KP, view=IND, layer=PART, spread=False, stat=P,
                 headline="Your margin, built into every nurse",
                 say=f"Through the partner channel it is +20% atop the Florence rate — ${k_part:,.0f} per RN per month. "
                     "That spread is your recurring margin, in every market, every month."),
            dict(system=KP, view=IND, layer=FLO, spread=True, stat=S,
                 headline="The conversion you can sell",
                 say="Here is the gap vs. what these hospitals pay for travelers today. That delta is the permanent-conversion "
                     "opportunity — you monetize the account instead of losing it when they cut travel."),
            dict(system=KP, view=IND, layer=PART, spread=False, stat=P, export=True,
                 headline="A co-branded pitch in one click",
                 say="Generate a leave-behind for the account in seconds — quoted at your partner rate, ready to hand over."),
        ]
    else:
        beats = [
            dict(system=None, view="MSA bubbles", layer=FLO, spread=False, stat=NAT,
                 headline="The agency-labor crisis, priced facility by facility",
                 say="This is U.S. nurse-staffing spend, priced facility by facility — 48,870 facilities across every metro. "
                     "The displaceable agency premium is the market we attack."),
            dict(system=KP, view=IND, layer=EFF, spread=False, stat=E,
                 headline="Structurally cheaper — the unit-economics moat",
                 say=f"Permanent international RNs land below agency cost because of the F-1 payroll-tax offset. The employer's "
                     f"effective net is about ${k_eff:,.0f} per RN per month — that structural advantage is the moat."),
            dict(system=KP, view=IND, layer=FLO, spread=False, stat=K,
                 headline="Proprietary, market-by-market pricing",
                 say="Every rate is calibrated from CMS HCRIS agency filings and BLS wages, per facility. No one else prices "
                     "this product market-by-market — this engine is the defensible asset."),
            dict(system=KP, view=IND, layer=PART, spread=False, stat=P,
                 headline="Distribution = the largest staffing partner in the country",
                 say="We don't build a national sales force — we plug into established national distribution partners. The +20% "
                     "partner channel is instant national reach and recurring, high-margin revenue."),
            dict(system=KP, view=IND, layer=FLO, spread=False, stat=K, export=True,
                 headline="Automated go-to-market",
                 say="Pricing, outreach, and these account pitches are all automated in one platform — operating leverage as we scale supply."),
        ]

    n = len(beats)
    i = min(max(int(st.session_state.get("mm_demo_step", 0)), 0), n - 1)
    b = beats[i]

    t = st.columns([1, 1, 4, 1.3, 1])
    t[0].button("◀ Back", key="mm_db", disabled=(i == 0),
                on_click=lambda: st.session_state.update(mm_demo_step=i - 1))
    t[1].button("Next ▶", key="mm_dn", disabled=(i == n - 1),
                on_click=lambda: st.session_state.update(mm_demo_step=i + 1))
    t[3].markdown(f"<div style='text-align:right;color:#667085;padding-top:7px'>Step {i+1} of {n}</div>",
                  unsafe_allow_html=True)
    t[4].button("✕ Exit", key="mm_dx",
                on_click=lambda: st.session_state.update(mm_demo=False, mm_demo_step=0))

    st.markdown(f"<h3 style='color:{NAVY};font-family:Georgia,serif;margin:8px 0 4px'>{b['headline']}</h3>",
                unsafe_allow_html=True)
    st.markdown(f"<div style='background:#F2F4F7;border-left:4px solid #0ABAB5;padding:11px 15px;"
                f"border-radius:6px;color:#101828;font-size:1.05rem;line-height:1.5;margin-bottom:8px'>"
                f"🗣&nbsp; {b['say']}</div>", unsafe_allow_html=True)
    sc = st.columns(len(b["stat"]))
    for c, (lab, val) in zip(sc, b["stat"]):
        c.metric(lab, val)

    d = FD.reprice(df if b["system"] is None else df[df["health_system"] == b["system"]])
    if b["spread"]:
        d = d[d["agency_prem_hr"].notna()]
    if not len(d):
        st.warning("No facilities for this step.")
        return
    cc = LAYER_COL[b["layer"]]
    color_col = "spread_vs_agency" if b["spread"] else cc
    st.plotly_chart(_map_figure(d, b["view"], cc, color_col, b["layer"], b["spread"]),
                    use_container_width=True, key="mm_demo_map",
                    config={"scrollZoom": True})

    if b.get("export"):
        if st.button(f"⬇ Generate {hd} pitch PDF", key="mm_demo_pdf_btn"):
            st.session_state["mm_demo_pdf"] = _spp.render(hero, kd, via_partner=partner, markup=0.20)
            st.session_state["mm_demo_pdf_name"] = f"Florence - {hd} pitch.pdf"
        if st.session_state.get("mm_demo_pdf"):
            st.download_button("Download pitch PDF", st.session_state["mm_demo_pdf"],
                               file_name=st.session_state.get("mm_demo_pdf_name", "pitch.pdf"),
                               mime="application/pdf", key="mm_demo_pdf_dl")
