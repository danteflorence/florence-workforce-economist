"""
Nurse community storage layer — peer connections, mentorship, study groups,
milestone celebrations.

Storage is CSV-based for development. Production should migrate to a real DB
(Supabase / Postgres / Firestore) with proper user auth.

Tables:
  data/community_connections.csv  — nurse-to-nurse peer connections
  data/community_mentorship.csv   — mentor/mentee assignments
  data/community_groups.csv       — study groups (e.g., "CCRN-2026")
  data/community_group_members.csv — group membership
  data/community_posts.csv        — group posts / announcements
  data/community_milestones.csv   — public milestone celebrations
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

CONNECTIONS_FILE = DATA_DIR / "community_connections.csv"
MENTORSHIP_FILE = DATA_DIR / "community_mentorship.csv"
GROUPS_FILE = DATA_DIR / "community_groups.csv"
GROUP_MEMBERS_FILE = DATA_DIR / "community_group_members.csv"
POSTS_FILE = DATA_DIR / "community_posts.csv"
MILESTONES_FILE = DATA_DIR / "community_milestones.csv"


def _ensure_header(path: Path, fields: list[str]) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(fields)


def _append(path: Path, fields: list[str], row: dict) -> None:
    _ensure_header(path, fields)
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([row.get(f, "") for f in fields])


def _load(path: Path, fields: list[str]) -> pd.DataFrame:
    _ensure_header(path, fields)
    return pd.read_csv(path)


# ─── Schemas ────────────────────────────────────────────────────────
CONNECTION_FIELDS = ["connection_id", "from_nurse_id", "to_nurse_id",
                     "status", "created_at"]  # status: pending/accepted/declined
MENTORSHIP_FIELDS = ["mentorship_id", "mentor_nurse_id", "mentee_nurse_id",
                     "topic", "status", "started_at"]
GROUP_FIELDS = ["group_id", "name", "description", "focus_cert",
                "next_milestone", "created_at"]
MEMBER_FIELDS = ["group_id", "nurse_id", "role", "joined_at"]   # role: member/lead
POST_FIELDS = ["post_id", "group_id", "nurse_id", "content", "posted_at"]
MILESTONE_FIELDS = ["milestone_id", "nurse_id", "milestone_type",
                    "title", "celebrated_at"]


# ─── Connection APIs ────────────────────────────────────────────────
def request_connection(from_nurse_id: str, to_nurse_id: str) -> str:
    cid = f"C{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{from_nurse_id}-{to_nurse_id}"
    _append(CONNECTIONS_FILE, CONNECTION_FIELDS, {
        "connection_id": cid,
        "from_nurse_id": from_nurse_id,
        "to_nurse_id": to_nurse_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    return cid


def list_connections(nurse_id: str) -> pd.DataFrame:
    df = _load(CONNECTIONS_FILE, CONNECTION_FIELDS)
    return df[
        (df["from_nurse_id"] == nurse_id) | (df["to_nurse_id"] == nurse_id)
    ]


# ─── Mentorship APIs ────────────────────────────────────────────────
def request_mentorship(mentor_id: str, mentee_id: str, topic: str) -> str:
    mid = f"M{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{mentor_id}-{mentee_id}"
    _append(MENTORSHIP_FILE, MENTORSHIP_FIELDS, {
        "mentorship_id": mid,
        "mentor_nurse_id": mentor_id,
        "mentee_nurse_id": mentee_id,
        "topic": topic,
        "status": "active",
        "started_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    return mid


# ─── Groups APIs ────────────────────────────────────────────────────
def create_group(name: str, description: str, focus_cert: str = "",
                 next_milestone: str = "") -> str:
    gid = f"G{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    _append(GROUPS_FILE, GROUP_FIELDS, {
        "group_id": gid, "name": name, "description": description,
        "focus_cert": focus_cert, "next_milestone": next_milestone,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    return gid


def join_group(group_id: str, nurse_id: str, role: str = "member") -> None:
    _append(GROUP_MEMBERS_FILE, MEMBER_FIELDS, {
        "group_id": group_id, "nurse_id": nurse_id, "role": role,
        "joined_at": datetime.utcnow().isoformat(timespec="seconds"),
    })


def list_groups() -> pd.DataFrame:
    return _load(GROUPS_FILE, GROUP_FIELDS)


def list_group_members(group_id: str) -> pd.DataFrame:
    df = _load(GROUP_MEMBERS_FILE, MEMBER_FIELDS)
    return df[df["group_id"] == group_id]


def list_nurse_groups(nurse_id: str) -> pd.DataFrame:
    members = _load(GROUP_MEMBERS_FILE, MEMBER_FIELDS)
    groups = _load(GROUPS_FILE, GROUP_FIELDS)
    sub = members[members["nurse_id"] == nurse_id]
    return groups[groups["group_id"].isin(sub["group_id"])]


# ─── Posts APIs ─────────────────────────────────────────────────────
def add_post(group_id: str, nurse_id: str, content: str) -> str:
    pid = f"P{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    _append(POSTS_FILE, POST_FIELDS, {
        "post_id": pid, "group_id": group_id, "nurse_id": nurse_id,
        "content": content,
        "posted_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    return pid


def group_posts(group_id: str, limit: int = 20) -> pd.DataFrame:
    df = _load(POSTS_FILE, POST_FIELDS)
    return df[df["group_id"] == group_id].sort_values("posted_at", ascending=False).head(limit)


# ─── Milestones (public celebrations) ───────────────────────────────
def celebrate_milestone(nurse_id: str, milestone_type: str, title: str) -> str:
    mid = f"MS{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    _append(MILESTONES_FILE, MILESTONE_FIELDS, {
        "milestone_id": mid, "nurse_id": nurse_id,
        "milestone_type": milestone_type, "title": title,
        "celebrated_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    return mid


def recent_milestones(n: int = 20) -> pd.DataFrame:
    df = _load(MILESTONES_FILE, MILESTONE_FIELDS)
    return df.sort_values("celebrated_at", ascending=False).head(n)


# ─── Seed demo data ─────────────────────────────────────────────────
def seed_demo() -> None:
    if not GROUPS_FILE.exists() or _load(GROUPS_FILE, GROUP_FIELDS).empty:
        # Three demo study groups
        g1 = create_group(
            "CCRN-2026 Study Group", "Preparing for CCRN exam, Summer 2026 cohort",
            "CCRN", "exam_august_2026",
        )
        g2 = create_group(
            "Q3 2024 Cohort", "Connect with your cohort peers",
            "", "cohort_anniversary",
        )
        g3 = create_group(
            "California RNs", "Connect with Florence RNs working in California",
            "", "",
        )
        for nurse_id in ["N0001", "N0002", "N0003"]:
            join_group(g2, nurse_id)
        join_group(g1, "N0001", role="lead")
        join_group(g1, "N0002")
        join_group(g3, "N0001")

        # Demo posts
        add_post(g1, "N0001",
                 "Welcome everyone! Let's plan our weekly study sessions. "
                 "Aiming for CCRN by August 2026.")
        add_post(g2, "N0001",
                 "Anyone else hitting the 6-month mark at their facility this week?")

        # Demo milestones
        celebrate_milestone("N0001", "first_start", "Maria S. — first day at Kaiser SF")
        celebrate_milestone("N0002", "nclex_passed", "James K. — NCLEX passed first try")
        celebrate_milestone("N0003", "first_start", "Priya R. — first day at Cleveland Clinic")


if __name__ == "__main__":
    seed_demo()
    print("Demo community data seeded.")
    print(f"\nGroups: {len(list_groups())}")
    print(list_groups()[["name", "focus_cert"]].to_string(index=False))
    print(f"\nRecent milestones:")
    print(recent_milestones(5)[["milestone_type", "title"]].to_string(index=False))
