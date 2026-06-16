"""
Florence Sales Playbook — loader + Streamlit tab + coaching-tip helpers.

The playbook content lives in /playbook/ as one JSON index + N markdown files.
This module reads them and renders the in-app tab. Other modules (app.py,
workbench.py) import coach_tip() to surface the same content as inline
tooltips so methodology stays in one place.

═══════════════════════════════════════════════════════════════════════════
HOW TO EDIT THE PLAYBOOK
═══════════════════════════════════════════════════════════════════════════
  - Change a section's text         → edit the matching .md file
  - Reorder or hide a section       → edit playbook/00_index.json
  - Add a new section               → drop a new .md file in /playbook/ and
                                       add an entry to 00_index.json
  - Change a coaching tooltip       → edit the "coaching" block in
                                       00_index.json

The tab in app.py picks up changes on the next reload (cache clears on
file mtime).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

PLAYBOOK_DIR = Path(__file__).parent / "playbook"
INDEX_PATH = PLAYBOOK_DIR / "00_index.json"


# ─── Loading ────────────────────────────────────────────────────────
def _load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"sections": [], "coaching": {}}
    return json.loads(INDEX_PATH.read_text())


def _load_section_text(filename: str) -> str:
    path = PLAYBOOK_DIR / filename
    if not path.exists():
        return f"_(missing: {filename})_"
    return path.read_text()


def list_sections(role: str = "rep") -> list[dict]:
    """Return all sections visible to a given role."""
    idx = _load_index()
    out = []
    for s in idx.get("sections", []):
        if role in s.get("visible_to", []):
            out.append(s)
    return out


def get_section(section_id: str) -> Optional[dict]:
    """Return a section dict (with 'body' populated from the .md file)."""
    idx = _load_index()
    for s in idx.get("sections", []):
        if s["id"] == section_id:
            return {**s, "body": _load_section_text(s["file"])}
    return None


# ─── Search ─────────────────────────────────────────────────────────
def search(query: str, role: str = "rep",
           max_results: int = 10) -> list[dict]:
    """Search section bodies for a query string. Returns list of hits with
    snippets around the first match per section."""
    q = query.strip().lower()
    if not q:
        return []
    hits: list[dict] = []
    for s in list_sections(role=role):
        body = _load_section_text(s["file"])
        idx_pos = body.lower().find(q)
        if idx_pos == -1:
            continue
        # Build a snippet around the match
        start = max(0, idx_pos - 80)
        end = min(len(body), idx_pos + len(q) + 80)
        snippet = body[start:end].strip()
        snippet = re.sub(r"\n+", " ", snippet)
        # Highlight the matched substring (markdown bold)
        try:
            snippet = (
                snippet[:snippet.lower().find(q)]
                + "**" + snippet[snippet.lower().find(q):
                                 snippet.lower().find(q) + len(q)] + "**"
                + snippet[snippet.lower().find(q) + len(q):]
            )
        except Exception:
            pass
        hits.append({
            "section_id": s["id"],
            "title": s["title"],
            "snippet": ("…" if start > 0 else "") + snippet
                       + ("…" if end < len(body) else ""),
        })
        if len(hits) >= max_results:
            break
    return hits


# ─── Visual: deal-flow diagram (shared between Playbook + Pipeline) ─
DEAL_FLOW_STAGES = [
    {"id": "prospect",   "name": "Prospect",  "icon": "contact_mail",  "gate": "Target identified"},
    {"id": "discovery",  "name": "Discovery", "icon": "forum",         "gate": "Disco call booked"},
    {"id": "proposal",   "name": "Proposal",  "icon": "description",   "gate": "Notes logged"},
    {"id": "review",     "name": "Review",    "icon": "rate_review",   "gate": "Proposal sent"},
    {"id": "closed",     "name": "Closed",    "icon": "check_circle",  "gate": "Terms agreed"},
]


# ─── Visual: persona cards (intro to the Personas playbook section) ─
PERSONAS = [
    {
        "id": "cfo", "icon": "account_balance",
        "name": "CFO",
        "optimizes": "The nursing labor line. Specifically the contract-labor sub-line that's been ugly since 2020.",
        "opener": "I'm not going to make you guess at the savings. The Excel has every facility broken out with the math shown.",
        "donts": ["FICA mechanics", "Trust-me claims", "Other-hospital averages"],
    },
    {
        "id": "cno", "icon": "vaccines",
        "name": "CNO",
        "optimizes": "Unit-level quality, retention, and credibility with nursing managers.",
        "opener": "I want to show you the nurses, not just the numbers. Can I walk you through the portal first?",
        "donts": ["Agency vocabulary", "We'll-handle-it", "NCLEX-ready (table stakes)"],
    },
    {
        "id": "ta", "icon": "badge",
        "name": "Talent / HR",
        "optimizes": "Time-to-fill, regulatory compliance, not getting blamed when something goes wrong.",
        "opener": "We'd own the visa, the credentialing, and the English documentation. You'd run our nurses through your standard orientation.",
        "donts": ["Aggressive volume", "Surprise compliance work"],
    },
    {
        "id": "coo", "icon": "factory",
        "name": "COO / VP Ops",
        "optimizes": "Operational continuity, service-line growth, operating margin.",
        "opener": "What service line would you grow if you had 10 more permanent RNs?",
        "donts": ["Staffing-agency framing", "Price-only positioning"],
    },
]


def _render_persona_cards(st) -> None:
    cards = []
    for p in PERSONAS:
        chips = "".join(f"<span class='chip'>{d}</span>" for d in p["donts"])
        cards.append(f"""
            <div class='fl-persona-card'>
              <div class='head'>
                <div class='icon'>{p['icon']}</div>
                <div class='name'>{p['name']}</div>
              </div>
              <div class='optimizes'>{p['optimizes']}</div>
              <div class='opener'>"{p['opener']}"</div>
              <div class='donts'>{chips}</div>
            </div>
        """)
    st.markdown(
        f"<div class='fl-persona-grid'>{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def render_deal_flow_diagram(st, active_stage: Optional[str] = None,
                             closed_state: Optional[str] = None) -> None:
    """Render the 5-stage deal flow as a horizontal visual.

    active_stage: one of the stage ids to highlight as current
    closed_state: "won" or "lost" — only used when active_stage == "closed"
    """
    nodes_html = []
    for stage in DEAL_FLOW_STAGES:
        is_active = (active_stage == stage["id"])
        css_class = "fl-flow-stage"
        if is_active:
            if stage["id"] == "closed":
                css_class += f" closed-{closed_state or 'won'}"
            else:
                css_class += " active"
        nodes_html.append(
            f"<div class='{css_class}'>"
            f"<div class='icon'>{stage['icon']}</div>"
            f"<div class='stage-name'>{stage['name']}</div>"
            f"<div class='gate'>{stage['gate']}</div>"
            f"</div>"
        )
    st.markdown(
        f"<div class='fl-flow'>{''.join(nodes_html)}</div>",
        unsafe_allow_html=True,
    )


# ─── Coaching tips ──────────────────────────────────────────────────
def coach_tip(key: str, role: str = "rep", value: Optional[str] = None) -> str:
    """Return the role-specific coaching tooltip for a metric key.

    The `value` interpolation is used for tips that include "${value}"
    placeholders — e.g. a savings number rendered live in the UI.
    """
    idx = _load_index()
    tip = (idx.get("coaching") or {}).get(key, {}).get(role)
    if not tip:
        # Fall back to the rep tip if the role-specific one is missing
        tip = (idx.get("coaching") or {}).get(key, {}).get("rep", "")
    if value is not None:
        tip = tip.replace("${value}", str(value))
    return tip


def list_coaching_keys() -> list[str]:
    return list((_load_index().get("coaching") or {}).keys())


# ─── Streamlit tab renderer ─────────────────────────────────────────
def streamlit_render(st, current_role: str = "admin",
                     current_user_email: str = "") -> None:
    """Render the full Playbook tab. Call from app.py's tab_playbook block."""
    sections = list_sections(role=current_role)
    if not sections:
        st.info("No playbook sections available for your role.",
                icon=":material/info:")
        return

    # ─── Header ──────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-family:Inter,sans-serif; font-size:0.8rem; "
        "letter-spacing:0.18em; text-transform:uppercase; color:#475467; "
        "margin-bottom:4px;'>SALES PLAYBOOK</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h2 style='font-family:Playfair Display,Georgia,serif; font-weight:500; "
        "color:#101828; margin-top:0; font-size:2.2rem;'>"
        "Everything you need to sell Florence."
        "</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Source-of-truth for the pitch, methodology, deal flow, and "
        "objection responses. Edited by sales leadership; surfaced as "
        "tooltips everywhere else in the app."
    )

    st.markdown("---")

    # ─── Search ──────────────────────────────────────────────────────
    q = st.text_input(
        "Search the playbook",
        placeholder="e.g. 'FICA', 'union', 'CFO objection', 'placement fee'",
        key="playbook_search",
    )
    if q:
        results = search(q, role=current_role)
        if not results:
            st.warning(f"No matches for '{q}'.",
                       icon=":material/search_off:")
        else:
            st.caption(f"Found in {len(results)} section(s):")
            for r in results:
                with st.container(border=True):
                    st.markdown(f"**{r['title']}** — {r['snippet']}")
                    if st.button(
                        f"Open {r['title']} →",
                        key=f"pb_jump_{r['section_id']}",
                        type="secondary",
                    ):
                        st.session_state["playbook_active_section"] = r["section_id"]
                        st.rerun()
        st.markdown("---")

    # ─── Section navigation + content ────────────────────────────────
    active_id = st.session_state.get(
        "playbook_active_section", sections[0]["id"]
    )
    nav_col, content_col = st.columns([1, 3], gap="large")

    with nav_col:
        st.markdown(
            "<div style='font-family:Inter,sans-serif; font-size:0.75rem; "
            "letter-spacing:0.18em; text-transform:uppercase; color:#475467; "
            "margin-bottom:8px;'>CONTENTS</div>",
            unsafe_allow_html=True,
        )
        for s in sections:
            is_active = (s["id"] == active_id)
            label = f":material/{s.get('icon','article')}: {s['title']}"
            if st.button(
                label,
                key=f"pb_nav_{s['id']}",
                use_container_width=True,
                type=("primary" if is_active else "secondary"),
            ):
                st.session_state["playbook_active_section"] = s["id"]
                st.rerun()

    with content_col:
        sec = get_section(active_id)
        if not sec:
            st.warning("Section not found.")
            return
        eyebrow = sec.get("eyebrow", "").upper()
        if eyebrow:
            st.markdown(
                f"<div style='font-family:Inter,sans-serif; font-size:0.75rem; "
                f"letter-spacing:0.18em; color:#0ABAB5; margin-bottom:6px;'>"
                f"{eyebrow}</div>",
                unsafe_allow_html=True,
            )
        # Visual intro for the Deal flow section
        if sec["id"] == "deal_flow":
            render_deal_flow_diagram(st, active_stage=None)
        # Visual intro for the Personas section — handled via persona cards block
        if sec["id"] == "personas":
            _render_persona_cards(st)
        st.markdown(sec["body"])

        # Footer: copy-to-clipboard, jump-to-section signal
        st.markdown("---")
        c1, c2 = st.columns([1, 1])
        with c1:
            st.download_button(
                ":material/download: Download this section (.md)",
                data=sec["body"],
                file_name=sec["file"],
                mime="text/markdown",
                use_container_width=True,
            )
        with c2:
            st.caption(
                f"Section ID: `{sec['id']}` · "
                f"File: `playbook/{sec['file']}`"
            )

    # ─── Meta ────────────────────────────────────────────────────────
    idx = _load_index()
    st.markdown("---")
    st.caption(
        f"Playbook version **{idx.get('version','?')}** · "
        f"Last reviewed **{idx.get('last_reviewed','?')}** · "
        f"Maintained by **{idx.get('maintainer','?')}** · "
        f"Edit source files in `/playbook/`."
    )


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- Playbook smoke test ---")
    secs = list_sections(role="rep")
    print(f"\n{len(secs)} sections visible to 'rep':")
    for s in secs:
        body = _load_section_text(s["file"])
        print(f"  - {s['id']:<16} '{s['title']}' ({len(body):,} chars)")

    print("\nCoaching keys:")
    for k in list_coaching_keys():
        print(f"  - {k}")

    print("\nSample tips:")
    print(f"  savings (rep): {coach_tip('savings', 'rep', value='420,000')[:100]}…")
    print(f"  savings (admin): {coach_tip('savings', 'admin')[:100]}…")
    print(f"  fica_offset (rep): {coach_tip('fica_offset', 'rep')[:80]}…")

    print("\nSearch 'union':")
    for r in search("union", role="rep"):
        print(f"  → {r['title']}: {r['snippet'][:120]}…")

    print("\nSearch 'FICA':")
    for r in search("FICA", role="rep"):
        print(f"  → {r['title']}: {r['snippet'][:120]}…")


if __name__ == "__main__":
    main()
