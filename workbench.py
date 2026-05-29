"""
Sales Workbench — per-rep pipeline + workflow refactor for the proposal flow.

The existing 'Build a customer proposal' tab is a powerful one-screen tool
that assumes the rep knows what they're doing. The Workbench wraps it in a
workflow that mirrors how reps actually work:

    PROSPECT  →  DISCOVERY  →  PROPOSAL  →  REVIEW  →  CLOSED-WON / LOST

Each deal is persisted (CSV today; swap for DB later). The Workbench surfaces
the rep's pipeline, suggests the next-best-move per deal, and gates
stage advancement on the right artifact (e.g. you can't move to Proposal
without discovery notes).

═══════════════════════════════════════════════════════════════════════════
DATA FILE
═══════════════════════════════════════════════════════════════════════════
data/sales_pipeline.csv

Columns:
    deal_id, rep_email, system_id, system_name,
    stage, created_at, last_touched_at,
    discovery_notes, proposal_url, contract_terms,
    closed_at, closed_reason
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
PIPELINE_FILE = DATA_DIR / "sales_pipeline.csv"

FIELDS = [
    "deal_id", "rep_email", "system_id", "system_name",
    "stage", "created_at", "last_touched_at",
    "discovery_notes", "proposal_url", "contract_terms",
    "closed_at", "closed_reason",
]

STAGES = ["prospect", "discovery", "proposal", "review",
          "closed_won", "closed_lost"]

STAGE_LABEL = {
    "prospect": "Prospect",
    "discovery": "Discovery",
    "proposal": "Proposal",
    "review": "Review",
    "closed_won": "Closed-won",
    "closed_lost": "Closed-lost",
}

STAGE_COLOR = {
    "prospect": "#5B6675",
    "discovery": "#F4A261",
    "proposal": "#089478",
    "review": "#0BC5A0",
    "closed_won": "#0F1B2D",
    "closed_lost": "#B33A3A",
}


# ─── Storage helpers ────────────────────────────────────────────────
def _ensure_header() -> None:
    if not PIPELINE_FILE.exists():
        PIPELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PIPELINE_FILE, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure_header()
    return pd.read_csv(PIPELINE_FILE, dtype=str).fillna("")


def _rewrite(df: pd.DataFrame) -> None:
    df.to_csv(PIPELINE_FILE, index=False, columns=FIELDS)


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


# ─── CRUD ───────────────────────────────────────────────────────────
def create_deal(rep_email: str, system_id: str, system_name: str) -> str:
    """Open a new deal at stage=prospect. Returns deal_id."""
    deal_id = f"D{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{system_id[:10]}"
    df = _read()
    df = pd.concat([df, pd.DataFrame([{
        "deal_id": deal_id,
        "rep_email": rep_email.strip().lower(),
        "system_id": system_id,
        "system_name": system_name,
        "stage": "prospect",
        "created_at": _now(),
        "last_touched_at": _now(),
        "discovery_notes": "",
        "proposal_url": "",
        "contract_terms": "",
        "closed_at": "",
        "closed_reason": "",
    }])], ignore_index=True)
    _rewrite(df)
    return deal_id


def get_deal(deal_id: str) -> Optional[dict]:
    df = _read()
    hit = df[df["deal_id"] == deal_id]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def update_deal(deal_id: str, **changes) -> bool:
    df = _read()
    mask = df["deal_id"] == deal_id
    if not mask.any():
        return False
    for k, v in changes.items():
        if k in FIELDS:
            df.loc[mask, k] = v
    df.loc[mask, "last_touched_at"] = _now()
    _rewrite(df)
    return True


def advance_stage(deal_id: str, new_stage: str,
                  closed_reason: str = "") -> bool:
    """Move a deal to a new stage. Closed stages also stamp closed_at."""
    if new_stage not in STAGES:
        raise ValueError(f"Invalid stage '{new_stage}'")
    changes: dict = {"stage": new_stage}
    if new_stage in ("closed_won", "closed_lost"):
        changes["closed_at"] = _now()
        changes["closed_reason"] = closed_reason
    return update_deal(deal_id, **changes)


def list_deals(rep_email: Optional[str] = None,
               include_closed: bool = False) -> pd.DataFrame:
    df = _read()
    if rep_email:
        df = df[df["rep_email"].str.lower() == rep_email.strip().lower()]
    if not include_closed:
        df = df[~df["stage"].isin(["closed_won", "closed_lost"])]
    return df.sort_values("last_touched_at", ascending=False)


# ─── Next-best-move logic ───────────────────────────────────────────
def next_best_move(deal: dict) -> dict:
    """Suggest the next action based on stage + last-touched.

    Returns: {"label": str, "action_button": str, "advance_to": str|None}
    """
    stage = deal.get("stage", "prospect")
    last_touched = deal.get("last_touched_at", "")
    days_since = 0
    try:
        days_since = (datetime.utcnow()
                      - datetime.fromisoformat(last_touched)).days
    except Exception:
        pass

    if stage == "prospect":
        return {
            "label": ("Run the AI sales-brief, draft outreach tied to "
                      "a specific local data point, book the discovery call."),
            "action_button": "Mark discovery call booked →",
            "advance_to": "discovery",
        }
    if stage == "discovery":
        if not (deal.get("discovery_notes") or "").strip():
            return {
                "label": ("Log discovery notes from your call below. "
                          "Required before you can advance to Proposal."),
                "action_button": None,
                "advance_to": None,
            }
        return {
            "label": ("Discovery notes captured. Generate the proposal "
                      "bundle next."),
            "action_button": "Move to Proposal →",
            "advance_to": "proposal",
        }
    if stage == "proposal":
        if days_since >= 5:
            return {
                "label": (f"Proposal sent {days_since}d ago. Time for a "
                          "follow-up nudge — short email referencing one "
                          "number from the deck."),
                "action_button": "Mark follow-up sent →",
                "advance_to": "review",
            }
        return {
            "label": ("Proposal is fresh. Wait for customer ack or schedule "
                      "the follow-up review call."),
            "action_button": "Move to Review →",
            "advance_to": "review",
        }
    if stage == "review":
        if days_since >= 30:
            return {
                "label": (f"In review {days_since}d. Press for the no — "
                          "stuck reviews are usually polite declines."),
                "action_button": "Mark closed-lost →",
                "advance_to": "closed_lost",
            }
        return {
            "label": ("Work through objections (playbook chapter 07). Loop "
                      "in sales leadership before any concession below "
                      "the Reference tier."),
            "action_button": "Mark closed-won →",
            "advance_to": "closed_won",
        }
    return {
        "label": "Deal is closed.",
        "action_button": None,
        "advance_to": None,
    }


# ─── Streamlit views ────────────────────────────────────────────────
def streamlit_pipeline_view(st, rep_email: str) -> Optional[str]:
    """Render the rep's pipeline. Returns the selected deal_id if any."""
    deals = list_deals(rep_email=rep_email, include_closed=False)
    closed = list_deals(rep_email=rep_email, include_closed=True)
    closed = closed[closed["stage"].isin(["closed_won", "closed_lost"])]

    st.markdown("#### Your active pipeline")
    if deals.empty:
        st.info(
            "No active deals yet. Add one below to start tracking work.",
            icon=":material/info:",
        )
    else:
        for _, d in deals.iterrows():
            stage = d["stage"]
            label_color = STAGE_COLOR.get(stage, "#5B6675")
            with st.container(border=True):
                row_l, row_r = st.columns([4, 1])
                with row_l:
                    st.markdown(
                        f"<span style='display:inline-block; padding:2px 10px; "
                        f"border-radius:12px; background:{label_color}1A; "
                        f"color:{label_color}; font-family:Inter,sans-serif; "
                        f"font-size:0.7rem; font-weight:600; letter-spacing:0.06em; "
                        f"text-transform:uppercase;'>{STAGE_LABEL[stage]}</span>"
                        f"<div style='font-family:Newsreader,Georgia,serif; "
                        f"font-size:1.3rem; color:#0F1B2D; margin-top:4px;'>"
                        f"{d['system_name']}</div>"
                        f"<div style='color:#5B6675; font-size:0.85rem;'>"
                        f"Created {d['created_at'][:10]} · "
                        f"Last touched {d['last_touched_at'][:10]}</div>",
                        unsafe_allow_html=True,
                    )
                    nbm = next_best_move(d.to_dict())
                    st.markdown(
                        f"<div style='color:#0F1B2D; font-size:0.9rem; "
                        f"margin-top:6px; padding:6px 10px; background:#F4F6F8; "
                        f"border-left:3px solid #0BC5A0; border-radius:4px;'>"
                        f"<b>Next:</b> {nbm['label']}</div>",
                        unsafe_allow_html=True,
                    )
                with row_r:
                    if st.button(
                        "Open →", key=f"open_{d['deal_id']}",
                        use_container_width=True, type="primary",
                    ):
                        st.session_state["workbench_active_deal"] = d["deal_id"]
                        st.rerun()

    if not closed.empty:
        with st.expander(f"Closed deals ({len(closed)})", expanded=False):
            st.dataframe(
                closed[["system_name", "stage", "closed_at", "closed_reason"]],
                use_container_width=True, hide_index=True,
            )
    return st.session_state.get("workbench_active_deal")


def streamlit_deal_detail(st, deal_id: str,
                          generate_proposal_callback=None) -> None:
    """Render the detail view for a single deal."""
    deal = get_deal(deal_id)
    if not deal:
        st.error("Deal not found.")
        return

    if st.button("← Back to pipeline", type="secondary"):
        st.session_state["workbench_active_deal"] = None
        st.rerun()

    stage = deal["stage"]
    color = STAGE_COLOR.get(stage, "#5B6675")
    st.markdown(
        f"<span style='display:inline-block; padding:3px 12px; "
        f"border-radius:14px; background:{color}1A; color:{color}; "
        f"font-family:Inter,sans-serif; font-size:0.75rem; "
        f"letter-spacing:0.08em; font-weight:600; text-transform:uppercase;'>"
        f"{STAGE_LABEL[stage]}</span>"
        f"<h2 style='font-family:Newsreader,Georgia,serif; font-weight:500; "
        f"color:#0F1B2D; margin-top:6px; font-size:2rem;'>"
        f"{deal['system_name']}</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Deal `{deal['deal_id']}` · Rep `{deal['rep_email']}` · "
        f"Created {deal['created_at'][:10]} · "
        f"Last touched {deal['last_touched_at'][:10]}"
    )

    # Next-best-move
    nbm = next_best_move(deal)
    nbm_col_l, nbm_col_r = st.columns([3, 1])
    with nbm_col_l:
        st.markdown(
            f"<div style='padding:14px 18px; background:#F4F6F8; "
            f"border-left:3px solid #0BC5A0; border-radius:6px; margin:8px 0;'>"
            f"<div style='font-family:Inter,sans-serif; font-size:0.75rem; "
            f"letter-spacing:0.1em; text-transform:uppercase; color:#5B6675;'>"
            f"NEXT BEST MOVE</div>"
            f"<div style='color:#0F1B2D; font-size:1rem; margin-top:4px;'>"
            f"{nbm['label']}</div></div>",
            unsafe_allow_html=True,
        )
    with nbm_col_r:
        if nbm["action_button"] and nbm["advance_to"]:
            if st.button(nbm["action_button"], type="primary",
                         use_container_width=True,
                         key=f"advance_{deal_id}"):
                advance_stage(deal_id, nbm["advance_to"])
                st.rerun()

    # Discovery notes
    st.markdown("#### Discovery notes")
    notes = st.text_area(
        "Capture what you heard on the discovery call",
        value=deal.get("discovery_notes", ""),
        height=160,
        placeholder=(
            "What's their current agency spend? Which units feel it most? "
            "What service lines would they grow? Who's the decision-maker? "
            "(See Playbook → Deal flow → Discovery for the full question list.)"
        ),
        key=f"notes_{deal_id}",
    )
    if notes != deal.get("discovery_notes", ""):
        if st.button("Save notes", type="secondary",
                     key=f"save_notes_{deal_id}"):
            update_deal(deal_id, discovery_notes=notes)
            st.success("Notes saved.")
            st.rerun()

    # Proposal section
    st.markdown("#### Proposal artifacts")
    if generate_proposal_callback:
        generate_proposal_callback(deal)
    else:
        st.caption(
            "Use the standard proposal tools below — your generated bundle "
            "URL can be saved here."
        )

    prop_url = st.text_input(
        "Proposal URL (paste from download)",
        value=deal.get("proposal_url", ""),
        key=f"propurl_{deal_id}",
    )
    if prop_url != deal.get("proposal_url", ""):
        if st.button("Save proposal URL", key=f"save_propurl_{deal_id}"):
            update_deal(deal_id, proposal_url=prop_url)
            st.rerun()

    # Send to leadership
    st.markdown("---")
    st.markdown("#### Sales leadership review")
    if stage in ("proposal", "review"):
        if st.button(
            ":material/escalator_warning: Send to leadership for review",
            type="primary", use_container_width=True,
            key=f"escalate_{deal_id}",
        ):
            advance_stage(deal_id, "review")
            update_deal(deal_id, contract_terms=(
                deal.get("contract_terms", "")
                + f"\n[{_now()}] Escalated to sales leadership."
            ))
            st.success("Deal flagged for leadership review.")
            st.rerun()

    # Manual stage controls
    with st.expander("Stage controls (manual)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Mark Closed-won", key=f"won_{deal_id}",
                         use_container_width=True):
                advance_stage(deal_id, "closed_won")
                st.rerun()
        with c2:
            reason = st.text_input(
                "Reason (for closed-lost)",
                key=f"loss_reason_{deal_id}",
                placeholder="e.g. internal hiring freeze, chose competitor",
            )
            if st.button("Mark Closed-lost", key=f"lost_{deal_id}",
                         use_container_width=True):
                advance_stage(deal_id, "closed_lost",
                              closed_reason=reason or "unspecified")
                st.rerun()


def streamlit_new_deal_form(st, rep_email: str,
                             systems_df: pd.DataFrame) -> Optional[str]:
    """Render a form to open a new deal. Returns deal_id if created."""
    st.markdown("#### Open a new deal")
    if systems_df.empty:
        st.warning("No systems available in your territory.")
        return None

    # Build system options (id → display label)
    sys_options = {}
    for _, row in systems_df.drop_duplicates("health_system_id").iterrows():
        sid = row["health_system_id"]
        sname = row.get("health_system", sid)
        sys_options[sid] = sname

    with st.form("new_deal_form"):
        picked = st.selectbox(
            "Health system",
            options=list(sys_options.keys()),
            format_func=lambda k: sys_options[k],
        )
        submitted = st.form_submit_button(
            ":material/add: Open new deal", type="primary",
            use_container_width=True,
        )
    if submitted and picked:
        deal_id = create_deal(rep_email, picked, sys_options[picked])
        st.session_state["workbench_active_deal"] = deal_id
        st.success(f"Opened deal for {sys_options[picked]}.")
        return deal_id
    return None


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- Workbench smoke test ---")
    did = create_deal("alice@florence.dev", "kaiser_permanente",
                      "Kaiser Permanente")
    print(f"Created deal {did}")
    d = get_deal(did)
    print(f"Stage: {d['stage']}, next: {next_best_move(d)['label'][:60]}…")

    update_deal(did, discovery_notes="They're paying $185/hr for agency at 6 facilities. CFO is hot.")
    advance_stage(did, "discovery")
    d = get_deal(did)
    print(f"After notes + advance, next: {next_best_move(d)['label'][:60]}…")

    advance_stage(did, "proposal")
    d = get_deal(did)
    print(f"At proposal: {next_best_move(d)['label'][:60]}…")

    advance_stage(did, "closed_won")
    d = get_deal(did)
    print(f"At closed_won: stage={d['stage']}, closed_at={d['closed_at']}")

    print("\nActive pipeline:")
    print(list_deals(rep_email="alice@florence.dev",
                     include_closed=True)[["system_name", "stage"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
