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

    Adds: becker_rank_2026, display_name (override), domain.
    Sorts by Becker rank ASC, then by RN need DESC for unranked rows.
    """
    if directory is None:
        directory = load_directory()
    merged = sys_agg.merge(
        directory[["florence_system_id", "becker_rank_2026",
                   "display_name", "domain"]],
        left_on="health_system_id", right_on="florence_system_id",
        how="left",
    )
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
    """Short initials for the logo-fallback badge."""
    tokens = [w for w in name.replace("/", " ").split() if w[:1].isalpha()]
    if not tokens:
        return "?"
    if len(tokens) == 1:
        return tokens[0][:2].upper()
    return (tokens[0][:1] + tokens[1][:1]).upper()


def _fmt_big(v: float) -> str:
    if v is None or v != v:
        return "—"
    v = float(v)
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:,.0f}M"
    if v >= 1e3:  return f"${v/1e3:,.0f}K"
    return f"${v:,.0f}"


def _tile_html(row: dict) -> str:
    """Build the HTML for one tile (logo + name + stats). No button — the
    button is rendered by Streamlit alongside the HTML for click handling."""
    name = row.get("display_name") or row.get("health_system") or "Unknown"
    domain = (row.get("domain") or "").strip()
    rank = row.get("becker_rank_2026")
    rank_html = ""
    if rank == rank and rank is not None:  # not NaN
        try:
            rank_html = f"<div class='fl-tile-rank'>#{int(rank)} · BECKER 2026</div>"
        except Exception:
            pass

    inits = _initials(name)
    if domain:
        logo_html = (
            f"<img class='fl-tile-logo-img' "
            f"src='https://logo.clearbit.com/{domain}' "
            f"alt='{name} logo' "
            f"onerror=\"this.style.display='none'; "
            f"this.nextElementSibling.style.display='flex';\">"
            f"<div class='fl-tile-logo-fallback' style='display:none;'>{inits}</div>"
        )
    else:
        logo_html = f"<div class='fl-tile-logo-fallback'>{inits}</div>"

    n_fac = int(row.get("n_facilities", 0) or 0)
    rn_need = int(row.get("rn_need", 0) or 0)
    monthly_fee = float(row.get("monthly_fee_target", 0) or 0)
    term_savings = float(row.get("term_savings_target", 0) or 0)

    return f"""
    <div class='fl-tile'>
      <div class='fl-tile-head'>
        {logo_html}
        <div>
          <div class='fl-tile-name'>{name}</div>
          {rank_html}
        </div>
      </div>
      <div class='fl-tile-stats'>
        <div class='fl-tile-stat'>
          <div class='v'>{n_fac:,}</div>
          <div class='l'>Facilities</div>
        </div>
        <div class='fl-tile-stat'>
          <div class='v'>{rn_need:,}</div>
          <div class='l'>RN need</div>
        </div>
        <div class='fl-tile-stat'>
          <div class='v'>{_fmt_big(monthly_fee)}/mo</div>
          <div class='l'>Florence fee</div>
        </div>
        <div class='fl-tile-stat'>
          <div class='v'>{_fmt_big(term_savings)}</div>
          <div class='l'>24-mo savings</div>
        </div>
      </div>
    </div>
    """


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
