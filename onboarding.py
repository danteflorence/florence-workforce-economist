"""
Florence Sales Onboarding — a 5-day guided track that uses the real tool.

The track is structured so a new rep, with a sales leader checking in once
a day, can be productive on their first live deal by end of day 5. Every
day mixes reading (Playbook) with doing (Workbench / pricing / discovery
role-play).

═══════════════════════════════════════════════════════════════════════════
DATA FILE
═══════════════════════════════════════════════════════════════════════════
data/onboarding_progress.csv

Columns:
    rep_email, day, checkpoint_id, status, completed_at, notes
    status: pending | in_progress | done | leader_signed_off
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
PROGRESS_FILE = DATA_DIR / "onboarding_progress.csv"

FIELDS = ["rep_email", "day", "checkpoint_id", "status",
          "completed_at", "notes"]


# ─── The track ──────────────────────────────────────────────────────
# Each day has a theme + a list of checkpoints. A checkpoint is one
# observable action ("read the pitch section", "generate a practice
# proposal"). Some checkpoints require sales-leadership sign-off.
TRACK = [
    {
        "day": 1,
        "title": "What we do, and why anyone buys it",
        "summary": "Read the pitch. Sit with the value props. Meet sales leadership. By end of day you should be able to give the 60-second pitch from memory.",
        "checkpoints": [
            {"id": "d1_pitch", "label": "Read Playbook → The pitch",
             "type": "playbook", "section": "pitch",
             "leader_signoff": False},
            {"id": "d1_value_op", "label": "Read Playbook → Value to operators",
             "type": "playbook", "section": "value_operators",
             "leader_signoff": False},
            {"id": "d1_value_nurse", "label": "Read Playbook → Value to nurses",
             "type": "playbook", "section": "value_nurses",
             "leader_signoff": False},
            {"id": "d1_pitch_back", "label": "Deliver the 60-second pitch back to a sales leader (live or recorded)",
             "type": "leader", "leader_signoff": True},
        ],
    },
    {
        "day": 2,
        "title": "Methodology — why our numbers are credible",
        "summary": "Open the pricing tab and the data-provenance tab. By end of day, you should be able to defend any number on a sample proposal.",
        "checkpoints": [
            {"id": "d2_pricing", "label": "Read Playbook → How our pricing works",
             "type": "playbook", "section": "pricing",
             "leader_signoff": False},
            {"id": "d2_glossary", "label": "Skim Playbook → Glossary",
             "type": "playbook", "section": "glossary",
             "leader_signoff": False},
            {"id": "d2_provenance", "label": "Walk through the Data Provenance tab for one facility",
             "type": "doing", "leader_signoff": False},
            {"id": "d2_defend", "label": "Defend three numbers from a sample proposal — leader plays CFO",
             "type": "leader", "leader_signoff": True},
        ],
    },
    {
        "day": 3,
        "title": "Build a practice proposal",
        "summary": "Use the Workbench. Open a sandbox deal on a test system. Generate the bundle. Sit with the output before clicking around.",
        "checkpoints": [
            {"id": "d3_deal_flow", "label": "Read Playbook → The deal flow",
             "type": "playbook", "section": "deal_flow",
             "leader_signoff": False},
            {"id": "d3_open_deal", "label": "Open a sandbox deal in the Workbench",
             "type": "doing", "leader_signoff": False},
            {"id": "d3_log_disco", "label": "Log discovery notes (use the question library)",
             "type": "doing", "leader_signoff": False},
            {"id": "d3_generate", "label": "Generate the proposal bundle (.xlsx + .pdf)",
             "type": "doing", "leader_signoff": False},
            {"id": "d3_review", "label": "Walk a sales leader through your proposal end-to-end",
             "type": "leader", "leader_signoff": True},
        ],
    },
    {
        "day": 4,
        "title": "Discovery role-play and objection handling",
        "summary": "The proposal isn't the hard part — discovery is. Spend the day on the question library and the top-10 objections. Role-play with a leader.",
        "checkpoints": [
            {"id": "d4_personas", "label": "Read Playbook → Buyer personas",
             "type": "playbook", "section": "personas",
             "leader_signoff": False},
            {"id": "d4_objections", "label": "Read Playbook → Top 10 objections",
             "type": "playbook", "section": "objections",
             "leader_signoff": False},
            {"id": "d4_roleplay_disco", "label": "Discovery role-play (30 min) — leader plays a CNO",
             "type": "leader", "leader_signoff": True},
            {"id": "d4_roleplay_obj", "label": "Objection role-play — leader picks 3 from the top 10",
             "type": "leader", "leader_signoff": True},
        ],
    },
    {
        "day": 5,
        "title": "First live deal — shadowed",
        "summary": "Real customer, real call, leader shadows. By end of day you've started your first pipeline deal.",
        "checkpoints": [
            {"id": "d5_field_card", "label": "Print + carry the One-page field card",
             "type": "playbook", "section": "field_card",
             "leader_signoff": False},
            {"id": "d5_prospect", "label": "Pick a real target from the lead-scoring tab",
             "type": "doing", "leader_signoff": False},
            {"id": "d5_outreach", "label": "Draft + send first outreach email (leader reviews before send)",
             "type": "leader", "leader_signoff": True},
            {"id": "d5_open_real", "label": "Open the real deal in the Workbench",
             "type": "doing", "leader_signoff": False},
            {"id": "d5_certification", "label": "Sales-leadership certification: ready to run point on deals",
             "type": "leader", "leader_signoff": True},
        ],
    },
]


# ─── Storage helpers ────────────────────────────────────────────────
def _ensure_header() -> None:
    if not PROGRESS_FILE.exists():
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROGRESS_FILE, "w", newline="") as f:
            csv.writer(f).writerow(FIELDS)


def _read() -> pd.DataFrame:
    _ensure_header()
    return pd.read_csv(PROGRESS_FILE, dtype=str).fillna("")


def _rewrite(df: pd.DataFrame) -> None:
    df.to_csv(PROGRESS_FILE, index=False, columns=FIELDS)


# ─── Progress API ───────────────────────────────────────────────────
def get_status(rep_email: str, checkpoint_id: str) -> str:
    df = _read()
    rep_email = rep_email.strip().lower()
    hit = df[
        (df["rep_email"].str.lower() == rep_email)
        & (df["checkpoint_id"] == checkpoint_id)
    ]
    if hit.empty:
        return "pending"
    return hit.iloc[-1]["status"]


def set_status(rep_email: str, checkpoint_id: str, status: str,
               notes: str = "") -> None:
    """Upsert the rep's progress on a checkpoint."""
    if status not in ("pending", "in_progress", "done", "leader_signed_off"):
        raise ValueError(f"Invalid status {status}")
    df = _read()
    rep_email = rep_email.strip().lower()
    mask = (
        (df["rep_email"].str.lower() == rep_email)
        & (df["checkpoint_id"] == checkpoint_id)
    )
    # Find the matching day
    day = None
    for d in TRACK:
        for cp in d["checkpoints"]:
            if cp["id"] == checkpoint_id:
                day = d["day"]
                break
    row = {
        "rep_email": rep_email,
        "day": str(day) if day else "",
        "checkpoint_id": checkpoint_id,
        "status": status,
        "completed_at": datetime.utcnow().isoformat(timespec="seconds")
                        if status in ("done", "leader_signed_off") else "",
        "notes": notes,
    }
    if mask.any():
        for k, v in row.items():
            df.loc[mask, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _rewrite(df)


def rep_progress(rep_email: str) -> pd.DataFrame:
    """Return the rep's full progress as one row per checkpoint."""
    rows = []
    for d in TRACK:
        for cp in d["checkpoints"]:
            rows.append({
                "day": d["day"],
                "checkpoint_id": cp["id"],
                "label": cp["label"],
                "type": cp["type"],
                "leader_signoff": cp.get("leader_signoff", False),
                "status": get_status(rep_email, cp["id"]),
            })
    return pd.DataFrame(rows)


def overall_pct(rep_email: str) -> float:
    p = rep_progress(rep_email)
    if p.empty:
        return 0.0
    done = (p["status"].isin(["done", "leader_signed_off"])).sum()
    return (done / len(p)) * 100


def team_progress() -> pd.DataFrame:
    """Aggregate progress across all reps."""
    df = _read()
    if df.empty:
        return pd.DataFrame()
    total = sum(len(d["checkpoints"]) for d in TRACK)
    out = []
    for rep in df["rep_email"].unique():
        done = ((df["rep_email"] == rep)
                & (df["status"].isin(["done", "leader_signed_off"]))).sum()
        sign = ((df["rep_email"] == rep)
                & (df["status"] == "leader_signed_off")).sum()
        last = df[df["rep_email"] == rep]["completed_at"].max()
        out.append({
            "rep_email": rep,
            "completed": done,
            "leader_signed_off": sign,
            "total": total,
            "pct_complete": round(done / total * 100, 1),
            "last_activity": last,
        })
    return pd.DataFrame(out).sort_values("pct_complete", ascending=False)


# ─── Streamlit views ────────────────────────────────────────────────
def streamlit_rep_view(st, rep_email: str) -> None:
    """The rep's own onboarding view — 5 days, checkpoint-by-checkpoint."""
    pct = overall_pct(rep_email)
    st.markdown(
        f"<div style='font-family:Inter,sans-serif; font-size:0.8rem; "
        f"letter-spacing:0.18em; text-transform:uppercase; color:#5B6675;'>"
        f"YOUR ONBOARDING</div>"
        f"<h2 style='font-family:Newsreader,Georgia,serif; font-weight:500; "
        f"color:#0F1B2D; margin-top:0; font-size:2.2rem;'>"
        f"5 days to your first live deal.</h2>",
        unsafe_allow_html=True,
    )
    st.progress(pct / 100, text=f"Overall: {pct:.0f}% complete")
    st.caption(
        "A guided 5-day track. Each day mixes reading the Playbook with "
        "real work in the Workbench. Sales leadership signs off on the "
        "actions marked ★."
    )

    for day in TRACK:
        day_checks = day["checkpoints"]
        day_done = sum(
            1 for cp in day_checks
            if get_status(rep_email, cp["id"]) in ("done", "leader_signed_off")
        )
        with st.expander(
            f"**Day {day['day']} — {day['title']}**   "
            f"({day_done}/{len(day_checks)} complete)",
            expanded=(day_done < len(day_checks) and day["day"] <= 2),
        ):
            st.caption(day["summary"])
            for cp in day_checks:
                status = get_status(rep_email, cp["id"])
                done = status in ("done", "leader_signed_off")
                signed = status == "leader_signed_off"
                signoff_required = cp.get("leader_signoff", False)

                cols = st.columns([6, 2, 2])
                with cols[0]:
                    star = " ★" if signoff_required else ""
                    label_color = "#5B6675" if done else "#0F1B2D"
                    icon = ":material/check_circle:" if done else ":material/radio_button_unchecked:"
                    st.markdown(
                        f"{icon} <span style='color:{label_color};'>"
                        f"{cp['label']}{star}</span>",
                        unsafe_allow_html=True,
                    )
                    if cp["type"] == "playbook":
                        if st.button(
                            f"Open in Playbook →",
                            key=f"open_pb_{cp['id']}",
                            type="secondary",
                        ):
                            st.session_state["playbook_active_section"] = cp.get("section")
                            st.info(
                                "Section selected — switch to the Playbook tab "
                                "to read.",
                                icon=":material/lightbulb:",
                            )
                with cols[1]:
                    if signoff_required:
                        if signed:
                            st.success(":material/verified: Signed", icon=":material/verified:")
                        elif done:
                            st.caption("Awaiting leader sign-off")
                        else:
                            st.caption("Awaiting completion")
                    else:
                        st.caption("")
                with cols[2]:
                    if not done:
                        if st.button(
                            "Mark done",
                            key=f"done_{cp['id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            set_status(rep_email, cp["id"], "done")
                            st.rerun()
                    elif signoff_required and not signed:
                        st.button(
                            "Pending leader",
                            key=f"pending_{cp['id']}",
                            use_container_width=True,
                            disabled=True,
                        )
                    else:
                        if st.button(
                            "Undo",
                            key=f"undo_{cp['id']}",
                            type="secondary",
                            use_container_width=True,
                        ):
                            set_status(rep_email, cp["id"], "pending")
                            st.rerun()


def streamlit_leader_view(st) -> None:
    """Sales-leadership view: see all reps' progress + sign off pending."""
    st.markdown(
        "<div style='font-family:Inter,sans-serif; font-size:0.8rem; "
        "letter-spacing:0.18em; text-transform:uppercase; color:#5B6675;'>"
        "TEAM PROGRESS</div>"
        "<h2 style='font-family:Newsreader,Georgia,serif; font-weight:500; "
        "color:#0F1B2D; margin-top:0; font-size:2.2rem;'>"
        "Your reps' onboarding.</h2>",
        unsafe_allow_html=True,
    )
    tp = team_progress()
    if tp.empty:
        st.info("No reps have started onboarding yet.")
        return
    st.dataframe(tp, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Sign off a checkpoint")
    rep_pick = st.selectbox(
        "Rep",
        options=tp["rep_email"].tolist(),
        key="onb_signoff_rep",
    )
    if rep_pick:
        prog = rep_progress(rep_pick)
        # Show only signoff-required, currently "done" checkpoints
        pending = prog[
            (prog["leader_signoff"]) & (prog["status"] == "done")
        ]
        if pending.empty:
            st.caption("No checkpoints pending sign-off for this rep.")
        else:
            for _, row in pending.iterrows():
                with st.container(border=True):
                    st.markdown(f"**Day {row['day']}** — {row['label']}")
                    notes = st.text_input(
                        "Notes (optional)",
                        key=f"signnotes_{row['checkpoint_id']}",
                    )
                    if st.button(
                        ":material/verified: Sign off",
                        key=f"sign_{row['checkpoint_id']}",
                        type="primary",
                    ):
                        set_status(rep_pick, row["checkpoint_id"],
                                   "leader_signed_off", notes=notes)
                        st.rerun()


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- Onboarding smoke test ---")
    rep = "newrep@florence.dev"
    set_status(rep, "d1_pitch", "done")
    set_status(rep, "d1_value_op", "done")
    set_status(rep, "d1_value_nurse", "done")
    set_status(rep, "d1_pitch_back", "done")
    set_status(rep, "d1_pitch_back", "leader_signed_off",
               notes="Crisp 58-sec delivery. Approved.")
    print(f"After day 1: {overall_pct(rep):.1f}% complete")

    print("\nRep progress:")
    print(rep_progress(rep)[["day", "label", "status"]].head(8).to_string(index=False))

    print("\nTeam progress:")
    print(team_progress().to_string(index=False))


if __name__ == "__main__":
    main()
