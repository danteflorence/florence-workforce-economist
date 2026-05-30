"""
System tile grid — Inpatient landing page.

Renders ranked tiles for U.S. health systems sorted by Becker's annual
ranking. Each tile shows the system's logo (via Clearbit's free logo API),
quick stats (facilities, RN need, savings), and an "Open →" button that
drills the rep into the full proposal-building flow for that system.

═══════════════════════════════════════════════════════════════════════════
DATA FILES
═══════════════════════════════════════════════════════════════════════════
data/system_directory.csv  — becker_rank_2026, florence_system_id,
                              display_name, domain, notes

To update the rankings, edit the CSV. Rows without a becker_rank_2026
fall to the end of the grid (sorted by Florence RN need).

═══════════════════════════════════════════════════════════════════════════
LOGOS
═══════════════════════════════════════════════════════════════════════════
Logos are served via Clearbit's free Logo API:
    https://logo.clearbit.com/{domain}

No API key required. If the domain doesn't match a Clearbit-indexed brand,
the tile falls back to a teal initials badge (handled in CSS).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DIRECTORY_FILE = DATA_DIR / "system_directory.csv"


# ─── Loading ────────────────────────────────────────────────────────
def load_directory() -> pd.DataFrame:
    if not DIRECTORY_FILE.exists():
        return pd.DataFrame(columns=[
            "becker_rank_2026", "florence_system_id",
            "display_name", "domain", "notes",
        ])
    df = pd.read_csv(DIRECTORY_FILE, dtype=str).fillna("")
    df["becker_rank_2026"] = pd.to_numeric(
        df["becker_rank_2026"], errors="coerce"
    )
    return df


def merged_systems(sys_agg: pd.DataFrame,
                   directory: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Join the Florence system aggregation with the Becker directory.

    Adds: becker_rank_2026, display_name (override), domain, child_domains.
    Sorts by Becker rank ASC, then by RN need DESC for unranked rows.
    """
    if directory is None:
        directory = load_directory()
    # Backwards-compat: child_domains column may be missing in older CSVs
    dir_cols = ["florence_system_id", "becker_rank_2026",
                "display_name", "domain"]
    if "child_domains" in directory.columns:
        dir_cols.append("child_domains")
    merged = sys_agg.merge(
        directory[dir_cols],
        left_on="health_system_id", right_on="florence_system_id",
        how="left",
    )
    if "child_domains" not in merged.columns:
        merged["child_domains"] = ""
    # Defensive: ensure stat columns the tiles will read exist
    for col, default in [
        ("rn_need", 0),
        ("n_facilities", 0),
        ("monthly_fee_target", 0),
        ("term_savings_target", 0),
    ]:
        if col not in merged.columns:
            merged[col] = default
    # Drop the "independent" bucket from the tiles — it's not a system
    merged = merged[merged["health_system_id"] != "independent"]
    # Sort: ranked systems first (by rank), then unranked by RN need desc
    merged["_rank_or_inf"] = merged["becker_rank_2026"].fillna(99999)
    merged = merged.sort_values(
        ["_rank_or_inf", "rn_need"],
        ascending=[True, False],
    ).drop(columns=["_rank_or_inf"])
    return merged


# ─── HTML rendering ─────────────────────────────────────────────────
def _initials(name: str) -> str:
    """Short initials for the brand badge.

    If the first word is already an ALLCAPS short acronym (HCA, UPMC, UCSF,
    UCLA, SSM, etc.), use it as-is. Otherwise use first letters of the
    first two words.
    """
    tokens = [w for w in name.replace("/", " ").split() if w[:1].isalpha()]
    if not tokens:
        return "?"
    # First token is already a short uppercase acronym?
    if 2 <= len(tokens[0]) <= 5 and tokens[0].isupper():
        return tokens[0]
    if len(tokens) == 1:
        return tokens[0][:2].upper()
    return (tokens[0][:1] + tokens[1][:1]).upper()


def _domain_to_brand_label(domain: str) -> str:
    """Extract a short brand label from a domain for the multi-logo strip.

    Examples:
        ucsf.edu               → 'UCSF'
        health.ucdavis.edu     → 'UCDAVIS'  (4-5 chars max)
        health.ucsd.edu        → 'UCSD'
        ucihealth.org          → 'UCI'  (strips 'HEALTH' suffix)
        uclahealth.org         → 'UCLA'
    """
    parts = domain.lower().split(".")
    if parts and parts[0] in ("health", "www", "my", "secure"):
        parts = parts[1:]
    if not parts:
        return "?"
    sld = parts[0].upper()
    # Strip common "HEALTH" suffix so ucihealth → UCI
    if sld.endswith("HEALTH") and len(sld) > 6:
        sld = sld[:-6]
    return sld[:6]


def _fmt_big(v: float) -> str:
    if v is None or v != v:
        return "—"
    v = float(v)
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:,.0f}M"
    if v >= 1e3:  return f"${v/1e3:,.0f}K"
    return f"${v:,.0f}"


def _tile_html(row: dict) -> str:
    """Build the HTML for one tile. Renders multi-logo strip if child_domains
    is populated (for consortium tiles like UC Health), otherwise single logo."""
    name = row.get("display_name") or row.get("health_system") or "Unknown"
    domain = (row.get("domain") or "").strip()
    child_domains_raw = (row.get("child_domains") or "").strip()
    child_domains = [
        d.strip() for d in child_domains_raw.replace(",", ";").split(";")
        if d.strip()
    ]
    rank = row.get("becker_rank_2026")
    rank_html = ""
    if rank == rank and rank is not None:  # not NaN
        try:
            rank_html = f"<div class='fl-tile-rank'>#{int(rank)} · BECKER 2026</div>"
        except Exception:
            pass

    inits = _initials(name)

    n_fac = int(row.get("n_facilities", 0) or 0)
    rn_need = int(row.get("rn_need", 0) or 0)
    monthly_fee = float(row.get("monthly_fee_target", 0) or 0)
    term_savings = float(row.get("term_savings_target", 0) or 0)

    # ─── Multi-logo consortium variant ────────────────────────────────
    # We render styled initials badges for each child brand instead of
    # remote logos. Clearbit's free logo API was shut down after the HubSpot
    # acquisition; free favicon services only return 16-25px images. Initials
    # badges look intentional (B2B SaaS standard) and stay reliable.
    if child_domains:
        child_badges = "".join(
            f"<div class='fl-tile-logo-fallback' "
            f"style='font-size:0.78rem;'>{_domain_to_brand_label(d)}</div>"
            for d in child_domains
        )
        head_html = (
            f"<div class='fl-tile-logo-strip'>{child_badges}</div>"
            f"<div class='fl-tile-consortium-name'>{name}</div>"
            f"{rank_html}"
            f"<div class='fl-tile-consortium-tag' "
            f"style='font-family:Inter,sans-serif; font-size:0.7rem; "
            f"color:#5B6675; letter-spacing:0.06em; text-transform:uppercase; "
            f"margin-top:2px; font-weight:600;'>Multi-campus consortium</div>"
        )
    else:
        # ─── Single-logo standard tile (initials badge) ────────────────
        logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"
        head_html = (
            f"<div class='fl-tile-head'>{logo_html}"
            f"<div><div class='fl-tile-name'>{name}</div>{rank_html}</div>"
            f"</div>"
        )

    stats_html = (
        f"<div class='fl-tile-stats'>"
        f"<div class='fl-tile-stat'><div class='v'>{n_fac:,}</div>"
        f"<div class='l'>Facilities</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{rn_need:,}</div>"
        f"<div class='l'>RN need</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big(monthly_fee)}/mo</div>"
        f"<div class='l'>Florence fee</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big(term_savings)}</div>"
        f"<div class='l'>24-mo savings</div></div>"
        f"</div>"
    )
    return f"<div class='fl-tile'>{head_html}{stats_html}</div>"


# ─── Streamlit grid renderer ────────────────────────────────────────
def render_inpatient_tile_grid(st, sys_agg: pd.DataFrame,
                               max_tiles: int = 30) -> Optional[str]:
    """Render the tile grid for the Inpatient landing page.

    Returns the clicked system_id if a tile's button was pressed this rerun,
    else None.
    """
    merged = merged_systems(sys_agg)
    if merged.empty:
        st.info("No systems match the current filter.")
        return None

    visible = merged.head(max_tiles)
    n_columns = 3   # 3-wide grid; CSS responsive auto-wraps on narrow screens
    clicked_id: Optional[str] = None

    # Render in rows of n_columns
    rows_count = (len(visible) + n_columns - 1) // n_columns
    for r in range(rows_count):
        cols = st.columns(n_columns)
        for c in range(n_columns):
            idx = r * n_columns + c
            if idx >= len(visible):
                continue
            row = visible.iloc[idx]
            with cols[c]:
                st.markdown(_tile_html(row.to_dict()),
                            unsafe_allow_html=True)
                sys_id = row["health_system_id"]
                if st.button(
                    "Open →",
                    key=f"tile_open_{sys_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    clicked_id = sys_id

    return clicked_id


# ─── Hospital-level tiles (the "Biggest hospitals" toggle) ──────────
def _hospital_tile_html(row: dict, sys_logo_lookup: dict) -> str:
    """Tile for an individual hospital. Uses parent system's logo if known."""
    name = row.get("name", "Unknown")
    sys_id = row.get("health_system_id", "")
    sys_name = row.get("health_system", "Independent")
    city = row.get("city", "")
    state = row.get("state", "")
    rn_need = int(row.get("rn_need", 0) or 0)
    agency_premium = float(row.get("signal_agency_premium", 0) or 0)
    term_savings = float(row.get("target_term_net_savings_account", 0) or 0)
    deal_score = float(row.get("target_deal_score", 0) or 0) * 100

    # Initials badge using parent-system name (Clearbit logo API is dead)
    inits = _initials(sys_name) if sys_name else _initials(name)
    logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"

    # Single-line HTML to avoid Streamlit markdown parsing nested indentation
    # as code blocks.
    return (
        f"<div class='fl-tile'>"
        f"<div class='fl-tile-head'>{logo_html}"
        f"<div><div class='fl-tile-name'>{name}</div>"
        f"<div style='font-family:Inter,sans-serif; font-size:0.78rem; "
        f"color:#5B6675; margin-top:3px;'>{sys_name} · {city}, {state}</div>"
        f"</div></div>"
        f"<div class='fl-tile-stats'>"
        f"<div class='fl-tile-stat'><div class='v'>{rn_need:,}</div>"
        f"<div class='l'>RN need</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>${agency_premium:,.0f}/hr</div>"
        f"<div class='l'>Agency rate</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big(term_savings)}</div>"
        f"<div class='l'>24-mo savings</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{deal_score:.0f}/100</div>"
        f"<div class='l'>Deal score</div></div>"
        f"</div></div>"
    )


def render_hospital_tile_grid(st, recs_df: pd.DataFrame,
                              max_tiles: int = 30) -> Optional[str]:
    """Render top hospitals as tiles, sorted by RN need.

    Returns the clicked hospital CCN if a tile button was pressed.
    """
    # Drop NA + sort by RN need
    visible = (recs_df.dropna(subset=["rn_need"])
               .sort_values("rn_need", ascending=False)
               .head(max_tiles))
    if visible.empty:
        st.info("No hospitals match the current filter.")
        return None

    # Build parent-system logo lookup
    directory = load_directory()
    sys_logo_lookup = {
        row["florence_system_id"]: {"domain": row.get("domain", "")}
        for _, row in directory.iterrows()
        if row.get("florence_system_id")
    }

    n_columns = 3
    clicked_ccn: Optional[str] = None
    rows_count = (len(visible) + n_columns - 1) // n_columns
    for r in range(rows_count):
        cols = st.columns(n_columns)
        for c in range(n_columns):
            idx = r * n_columns + c
            if idx >= len(visible):
                continue
            row = visible.iloc[idx]
            with cols[c]:
                st.markdown(_hospital_tile_html(row.to_dict(), sys_logo_lookup),
                            unsafe_allow_html=True)
                ccn = str(row["ccn"])
                if st.button(
                    "Open →",
                    key=f"hosp_tile_open_{ccn}",
                    type="primary",
                    use_container_width=True,
                ):
                    clicked_ccn = ccn
    return clicked_ccn


# ─── Outpatient chain tiles (sorted by state) ───────────────────────
def _outpatient_tile_html(row: dict) -> str:
    name = row.get("health_system", "Unknown")
    primary_state = row.get("primary_state", "—")
    n_facilities = int(row.get("n", 0) or 0)
    rn = int(row.get("rn", 0) or 0)
    term_rev = float(row.get("rev", 0) or 0)
    inits = _initials(name)

    # Initials badge (no remote logo dependency)
    logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"

    # Single-line HTML to avoid Streamlit markdown code-block treatment.
    return (
        f"<div class='fl-tile'>"
        f"<div class='fl-tile-head'>{logo_html}"
        f"<div><div class='fl-tile-name'>{name}</div>"
        f"<div class='fl-tile-rank'>{primary_state}</div></div></div>"
        f"<div class='fl-tile-stats'>"
        f"<div class='fl-tile-stat'><div class='v'>{n_facilities:,}</div>"
        f"<div class='l'>Facilities</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{rn:,}</div>"
        f"<div class='l'>RNs placeable</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big(term_rev)}</div>"
        f"<div class='l'>24-mo uplift</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big(term_rev/2)}/yr</div>"
        f"<div class='l'>Annual</div></div>"
        f"</div></div>"
    )


def render_outpatient_tile_grid(st, nh_df: pd.DataFrame,
                                max_tiles: int = 30) -> Optional[str]:
    """Render outpatient chain tiles, grouped by primary state.

    Returns the clicked health_system_id if a tile was pressed.
    """
    # Compute chain-level aggregation with primary state
    grouped = nh_df.dropna(subset=["health_system_id"]).copy()
    grouped = grouped[grouped["health_system_id"] != "independent"]
    if grouped.empty:
        st.info("No outpatient chains match the current filter.")
        return None

    # Compute primary state per chain (mode/most-common)
    primary_state = (grouped.groupby("health_system_id")["state"]
                     .agg(lambda s: s.value_counts().idxmax())
                     .rename("primary_state").reset_index())
    chain_summary = (grouped.groupby(["health_system_id", "health_system"])
                     .agg(n=("ccn", "count"),
                          rn=("rn_estimate", "sum"),
                          rev=("account_term_revenue_uplift", "sum"))
                     .reset_index()
                     .merge(primary_state, on="health_system_id", how="left"))
    chain_summary = chain_summary.sort_values(
        ["primary_state", "rev"], ascending=[True, False]
    ).head(max_tiles)

    n_columns = 3
    clicked_id: Optional[str] = None
    current_state = None
    rows_to_render = []
    for _, row in chain_summary.iterrows():
        if row["primary_state"] != current_state:
            rows_to_render.append(("HEADER", row["primary_state"]))
            current_state = row["primary_state"]
        rows_to_render.append(("TILE", row))

    i = 0
    while i < len(rows_to_render):
        if rows_to_render[i][0] == "HEADER":
            state = rows_to_render[i][1]
            st.markdown(
                f"<div style='font-family:Inter,sans-serif; font-size:0.8rem; "
                f"font-weight:600; letter-spacing:0.18em; color:#5B6675; "
                f"text-transform:uppercase; margin:18px 0 8px 0;'>"
                f"{state}</div>",
                unsafe_allow_html=True,
            )
            i += 1
            continue
        # Take up to n_columns consecutive TILE entries
        batch = []
        while i < len(rows_to_render) and rows_to_render[i][0] == "TILE" and len(batch) < n_columns:
            batch.append(rows_to_render[i][1])
            i += 1
        cols = st.columns(n_columns)
        for c, row in enumerate(batch):
            with cols[c]:
                st.markdown(_outpatient_tile_html(row.to_dict()),
                            unsafe_allow_html=True)
                hsid = row["health_system_id"]
                if st.button(
                    "Open →",
                    key=f"out_tile_open_{hsid}",
                    type="primary",
                    use_container_width=True,
                ):
                    clicked_id = hsid
    return clicked_id


def render_unranked_count(st, sys_agg: pd.DataFrame) -> int:
    """Return the count of systems not in the Becker directory."""
    merged = merged_systems(sys_agg)
    unranked = merged["becker_rank_2026"].isna().sum()
    return int(unranked)


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- system_tiles smoke test ---")
    d = load_directory()
    print(f"Directory: {len(d)} rows")
    print(d[["becker_rank_2026", "florence_system_id", "display_name"]]
          .head(10).to_string(index=False))


if __name__ == "__main__":
    main()
