"""
System tile grid — Inpatient landing page.

Renders ranked tiles for U.S. health systems sorted by scale
(largest systems first). Each tile shows the system's logo (via Clearbit's free logo API),
quick stats (facilities, RN need, savings), and an "Open →" button that
drills the rep into the full proposal-building flow for that system.

═══════════════════════════════════════════════════════════════════════════
DATA FILES
═══════════════════════════════════════════════════════════════════════════
data/system_directory.csv  — system_rank, florence_system_id,
                              display_name, domain, notes

To update the rankings, edit the CSV. Rows without a system_rank
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

import html
import re
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    from workbench import STAGE_LABEL, STAGE_COLOR
except Exception:  # import-safe fallback if the pipeline module is unavailable
    STAGE_LABEL, STAGE_COLOR = {}, {}

DATA_DIR = Path(__file__).parent / "data"
DIRECTORY_FILE = DATA_DIR / "system_directory.csv"


def _name_matches(query: str, name: str) -> bool:
    """Space/punctuation-insensitive substring match, so 'Honor Health',
    'honorhealth', and 'honor-health' all find the system 'HonorHealth'."""
    q = re.sub(r"[^a-z0-9]", "", str(query or "").lower())
    if not q:
        return True
    return q in re.sub(r"[^a-z0-9]", "", str(name or "").lower())


# ─── Loading ────────────────────────────────────────────────────────
def load_directory() -> pd.DataFrame:
    if not DIRECTORY_FILE.exists():
        return pd.DataFrame(columns=[
            "system_rank", "florence_system_id",
            "display_name", "domain", "notes",
        ])
    df = pd.read_csv(DIRECTORY_FILE, dtype=str).fillna("")
    df["system_rank"] = pd.to_numeric(
        df["system_rank"], errors="coerce"
    )
    return df


def merged_systems(sys_agg: pd.DataFrame,
                   directory: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Join the Florence system aggregation with the ranked system directory.

    Adds: system_rank, display_name (override), domain, child_domains.
    Sorts by system rank ASC, then by RN need DESC for unranked rows.
    """
    if directory is None:
        directory = load_directory()
    # Backwards-compat: child_domains column may be missing in older CSVs
    dir_cols = ["florence_system_id", "system_rank",
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
    merged["_rank_or_inf"] = merged["system_rank"].fillna(99999)
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


def _safe(s) -> str:
    """HTML-escape arbitrary text AND neutralize the `$` LaTeX trigger.

    Streamlit's markdown pipeline runs *before* unsafe HTML is emitted, so a
    literal `$...$` anywhere in a card — even inside a <div> — gets rendered as
    LaTeX math (the deployed-tile bug). Escaping `$` to its HTML entity prevents
    that. html.escape() runs first (handling &, <, >), so there are no `&#...`
    entities for the `$` swap to clobber.
    """
    return html.escape(str(s)).replace("$", "&#36;")


def _fmt_big_html(v: float) -> str:
    """Money formatter for HTML cards — same as _fmt_big but with `$` rendered
    as its HTML entity so Streamlit never parses it as LaTeX math mode."""
    return _fmt_big(v).replace("$", "&#36;")


def _accent_for(idx: int) -> str:
    """Alternate the deck's two brand accents (teal / indigo) across the grid."""
    return "indigo" if idx % 2 else "teal"


def _tile_html(row: dict, idx: int = 0, status: Optional[str] = None) -> str:
    """Build the HTML card for one inpatient system tile.

    Deck-styled (Avila×Florence): white card with a colored accent rail + a
    serif initials badge in one of the two brand colors (teal / indigo,
    alternating across the grid), a Newsreader serif name, an uppercase tracked
    rank pill, and a 2×2 stat grid whose 24-month-impact number is
    rendered in the accent color. A multi-badge strip replaces the single badge
    for consortium tiles (child_domains populated, e.g. UC Health).

    Every `$` is emitted as &#36; so Streamlit's markdown pass never parses the
    card as LaTeX math — the root cause of the deployed tile bug.
    """
    accent = _accent_for(idx)
    name = row.get("display_name") or row.get("health_system") or "Unknown"
    name_s = _safe(name)
    child_domains_raw = (row.get("child_domains") or "").strip()
    child_domains = [
        d.strip() for d in child_domains_raw.replace(",", ";").split(";")
        if d.strip()
    ]
    rank = row.get("system_rank")
    rank_html = ""
    if rank == rank and rank is not None:  # not NaN
        try:
            rank_html = (
                f"<div class='fl-tile-rank'><span class='dot'></span>"
                f"#{int(rank)} · by scale</div>"
            )
        except Exception:
            pass

    status_html = ""
    if status:
        _lbl = STAGE_LABEL.get(status, status)
        _clr = STAGE_COLOR.get(status, "#5B6675")
        status_html = (
            f"<div style='display:inline-block;margin-top:6px;padding:2px 9px;"
            f"border-radius:999px;font-size:0.62rem;font-weight:700;"
            f"letter-spacing:0.04em;text-transform:uppercase;"
            f"background:{_clr}1A;color:{_clr};'>&#9679; {_safe(_lbl)}</div>"
        )

    inits = _safe(_initials(name))
    n_fac = int(row.get("n_facilities", 0) or 0)
    rn_need = int(row.get("rn_need", 0) or 0)
    monthly_fee = float(row.get("monthly_fee_target", 0) or 0)
    term_savings = float(row.get("term_savings_target", 0) or 0)

    # ─── Multi-logo consortium variant ────────────────────────────────
    # Styled initials badges for each child brand instead of remote logos
    # (Clearbit's free logo API is dead; favicon services only return tiny
    # images). Initials badges look intentional and stay reliable.
    if child_domains:
        child_badges = "".join(
            f"<div class='fl-tile-logo-fallback' style='font-size:0.74rem;'>"
            f"{_safe(_domain_to_brand_label(d))}</div>"
            for d in child_domains
        )
        head_html = (
            f"<div class='fl-tile-logo-strip'>{child_badges}</div>"
            f"<div class='fl-tile-name'>{name_s}</div>"
            f"{rank_html}{status_html}"
            f"<div class='fl-tile-tag'>Multi-campus consortium</div>"
        )
    else:
        logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"
        head_html = (
            f"<div class='fl-tile-head'>{logo_html}"
            f"<div class='fl-tile-headtext'>"
            f"<div class='fl-tile-name'>{name_s}</div>{rank_html}{status_html}</div>"
            f"</div>"
        )

    stats_html = (
        f"<div class='fl-tile-stats'>"
        f"<div class='fl-tile-stat'><div class='v'>{n_fac:,}</div>"
        f"<div class='l'>Facilities</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{rn_need:,}</div>"
        f"<div class='l'>RN need</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big_html(monthly_fee)}"
        f"<span class='u'>/mo</span></div>"
        f"<div class='l'>Florence fee</div></div>"
        f"<div class='fl-tile-stat'><div class='v hero'>{_fmt_big_html(term_savings)}</div>"
        f"<div class='l'>24-mo impact</div></div>"
        f"</div>"
    )
    return f"<div class='fl-tile fl-accent-{accent}'>{head_html}{stats_html}</div>"


# ─── Streamlit grid renderer ────────────────────────────────────────
def render_inpatient_tile_grid(st, sys_agg: pd.DataFrame,
                               max_tiles: int = 30,
                               search: str = "",
                               status_map: Optional[dict] = None) -> Optional[tuple]:
    """Render the tile grid for the Inpatient landing page.

    `search` filters by system name (case-insensitive); `status_map` maps
    health_system_id → deal stage, rendered as a chip on each tile.

    Returns (action, system_id) where action is 'open' (deep-dive proposal) or
    'docs' (generate the document bundle), else None.
    """
    merged = merged_systems(sys_agg)
    status_map = status_map or {}
    if (search or "").strip():
        merged = merged[merged.apply(
            lambda r: _name_matches(search, r.get("display_name") or r.get("health_system") or ""),
            axis=1,
        )]
    if merged.empty:
        st.info("No systems match your search." if q else "No systems match the current filter.")
        return None

    visible = merged.head(max_tiles)
    n_columns = 3
    clicked: Optional[tuple] = None
    rows_count = (len(visible) + n_columns - 1) // n_columns
    for r in range(rows_count):
        cols = st.columns(n_columns)
        for c in range(n_columns):
            idx = r * n_columns + c
            if idx >= len(visible):
                continue
            row = visible.iloc[idx]
            with cols[c]:
                sys_id = row["health_system_id"]
                st.markdown(_tile_html(row.to_dict(), idx,
                                       status=status_map.get(str(sys_id))),
                            unsafe_allow_html=True)
                name = row.get("display_name") or row.get("health_system")
                ba, bb = st.columns(2)
                with ba:
                    if st.button("Open system →", key=f"tile_open_{sys_id}",
                                 type="primary", use_container_width=True,
                                 help=f"Open the {name} proposal"):
                        clicked = ("open", sys_id)
                with bb:
                    if st.button("Generate documents", key=f"tile_docs_{sys_id}",
                                 use_container_width=True,
                                 help=f"Generate the {name} document bundle"):
                        clicked = ("docs", sys_id)
    return clicked


# ─── Hospital-level tiles (the "Biggest hospitals" toggle) ──────────
def _hospital_tile_html(row: dict, idx: int = 0) -> str:
    """Deck-styled card for an individual hospital.

    Brand accent (teal / indigo) alternates across the grid; the 24-month
    impact is the accent-colored hero stat. All `$` are emitted as &#36; so
    Streamlit never parses the card as LaTeX math.
    """
    accent = _accent_for(idx)
    name = _safe(row.get("name", "Unknown"))
    sys_name = row.get("health_system", "Independent")
    city = row.get("city", "")
    state = row.get("state", "")
    rn_need = int(row.get("rn_need", 0) or 0)
    agency_premium = float(row.get("signal_agency_premium", 0) or 0)
    term_savings = float(row.get("target_term_net_savings_account", 0) or 0)
    deal_score = float(row.get("target_deal_score", 0) or 0) * 100

    # Initials badge using parent-system name (Clearbit logo API is dead)
    inits = _safe(_initials(sys_name) if sys_name else _initials(
        row.get("name", "?")))
    logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"
    sub = _safe(f"{sys_name} · {city}, {state}")

    return (
        f"<div class='fl-tile fl-accent-{accent}'>"
        f"<div class='fl-tile-head'>{logo_html}"
        f"<div class='fl-tile-headtext'><div class='fl-tile-name'>{name}</div>"
        f"<div class='fl-tile-sub'>{sub}</div>"
        f"</div></div>"
        f"<div class='fl-tile-stats'>"
        f"<div class='fl-tile-stat'><div class='v'>{rn_need:,}</div>"
        f"<div class='l'>RN need</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>&#36;{agency_premium:,.0f}"
        f"<span class='u'>/hr</span></div>"
        f"<div class='l'>Agency rate</div></div>"
        f"<div class='fl-tile-stat'><div class='v hero'>{_fmt_big_html(term_savings)}</div>"
        f"<div class='l'>24-mo impact</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{deal_score:.0f}"
        f"<span class='u'>/100</span></div>"
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
                ccn = str(row["ccn"])
                st.markdown(_hospital_tile_html(row.to_dict(), idx),
                            unsafe_allow_html=True)
                if st.button(
                    "Open →",
                    key=f"hosp_tile_open_{ccn}",
                    use_container_width=True,
                    help=f"Open {row.get('name')}",
                ):
                    clicked_ccn = ccn
    return clicked_ccn


# ─── Outpatient chain tiles (sorted by state) ───────────────────────
def _outpatient_tile_html(row: dict, idx: int = 0) -> str:
    """Deck-styled card for an outpatient chain. Brand accent alternates across
    the grid; 24-month uplift is the accent hero stat; every `$` is emitted as
    &#36; so Streamlit never parses the card as LaTeX math."""
    accent = _accent_for(idx)
    name = _safe(row.get("health_system", "Unknown"))
    n_facilities = int(row.get("n", 0) or 0)
    rn = int(row.get("rn", 0) or 0)
    term_rev = float(row.get("rev", 0) or 0)
    inits = _safe(_initials(row.get("health_system", "?")))
    logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"

    return (
        f"<div class='fl-tile fl-accent-{accent}'>"
        f"<div class='fl-tile-head'>{logo_html}"
        f"<div class='fl-tile-headtext'><div class='fl-tile-name'>{name}</div>"
        f"</div></div>"
        f"<div class='fl-tile-stats'>"
        f"<div class='fl-tile-stat'><div class='v'>{n_facilities:,}</div>"
        f"<div class='l'>Facilities</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{rn:,}</div>"
        f"<div class='l'>RNs placeable</div></div>"
        f"<div class='fl-tile-stat'><div class='v hero'>{_fmt_big_html(term_rev)}</div>"
        f"<div class='l'>24-mo uplift</div></div>"
        f"<div class='fl-tile-stat'><div class='v'>{_fmt_big_html(term_rev/2)}"
        f"<span class='u'>/yr</span></div>"
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
    tile_idx = 0  # running counter so the teal/indigo accent alternates
    while i < len(rows_to_render):
        if rows_to_render[i][0] == "HEADER":
            state = _safe(rows_to_render[i][1])
            st.markdown(
                f"<div class='florence-eyebrow' style='margin:20px 0 8px 0;'>"
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
                hsid = row["health_system_id"]
                st.markdown(_outpatient_tile_html(row.to_dict(), tile_idx),
                            unsafe_allow_html=True)
                tile_idx += 1
                if st.button(
                    "Open →",
                    key=f"out_tile_open_{hsid}",
                    use_container_width=True,
                    help=f"Open {row.get('health_system')}",
                ):
                    clicked_id = hsid
    return clicked_id


def render_unranked_count(st, sys_agg: pd.DataFrame) -> int:
    """Return the count of systems not in the ranked directory."""
    merged = merged_systems(sys_agg)
    unranked = merged["system_rank"].isna().sum()
    return int(unranked)


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- system_tiles smoke test ---")
    d = load_directory()
    print(f"Directory: {len(d)} rows")
    print(d[["system_rank", "florence_system_id", "display_name"]]
          .head(10).to_string(index=False))


if __name__ == "__main__":
    main()
