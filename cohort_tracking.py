"""
Cohort production tracking — Florence's actual placement data layer.

The schema is built so Florence's ops team can record each placement and
the system can compute production metrics (ramp time, retention, advancement,
yield per cohort) that feed the AI sales-brief, data room, nurse community,
and fundraising reports.

Files:
  data/cohorts.csv          — one row per cohort (cohort_id, year, size, status)
  data/placements.csv       — one row per nurse-placement event
  data/nurse_profiles.csv   — one row per nurse (links to placements)
  data/cohort_milestones.csv — events per nurse (NCLEX, first start, advancement)

All four are append-only logs. Aggregates are computed on read.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
COHORTS_FILE = DATA_DIR / "cohorts.csv"
PLACEMENTS_FILE = DATA_DIR / "placements.csv"
NURSE_PROFILES_FILE = DATA_DIR / "nurse_profiles.csv"
MILESTONES_FILE = DATA_DIR / "cohort_milestones.csv"


@dataclass
class Cohort:
    cohort_id: str             # e.g. "2024-Q3-PHI", "2025-COHORT-A"
    cohort_name: str
    start_year: int
    start_quarter: int          # 1-4
    target_size: int            # planned RNs in the cohort
    actual_size: int            # confirmed enrolled
    status: str                 # "in_pipeline" | "deployed" | "completed"
    origin_country: str          # e.g. "Philippines" | "India"
    program_type: str            # e.g. "F-1 student visa pipeline"
    expected_start_year: int
    expected_start_quarter: int
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NurseProfile:
    nurse_id: str             # internal ID
    full_name: str
    cohort_id: str
    origin_country: str
    nclex_status: str          # "not_taken" | "passed" | "failed"
    nclex_date: Optional[str]
    specialty: str
    license_state: str
    license_date: Optional[str]
    onboarded_at: Optional[str]
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Placement:
    placement_id: str
    nurse_id: str
    facility_ccn: str
    facility_name: str
    health_system_id: str
    placement_date: str         # ISO date of confirmed start
    annual_salary: float
    specialty: str
    contract_term_months: int
    status: str                 # "active" | "completed_term" | "departed_early"
    departed_date: Optional[str] = None
    departure_reason: Optional[str] = None
    customer_satisfaction_score: Optional[int] = None  # 1-5 from facility
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Milestone:
    milestone_id: str
    nurse_id: str
    event_type: str             # "nclex_passed" | "first_start" | "promotion" | "cert_earned"
    event_date: str
    detail: str = ""
    impact_dollars: Optional[float] = None  # e.g., wage step

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Storage helpers ────────────────────────────────────────────────
def _ensure_header(path: Path, fields: list[str]) -> None:
    """Create file with header if missing."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(fields)


def _append(path: Path, fields: list[str], row: dict) -> None:
    """Append a single row in field order."""
    _ensure_header(path, fields)
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([row.get(f, "") for f in fields])


COHORT_FIELDS = list(Cohort.__annotations__.keys())
NURSE_FIELDS = list(NurseProfile.__annotations__.keys())
PLACEMENT_FIELDS = list(Placement.__annotations__.keys())
MILESTONE_FIELDS = list(Milestone.__annotations__.keys())


def add_cohort(c: Cohort) -> None:
    _append(COHORTS_FILE, COHORT_FIELDS, c.to_dict())


def add_nurse(n: NurseProfile) -> None:
    _append(NURSE_PROFILES_FILE, NURSE_FIELDS, n.to_dict())


def add_placement(p: Placement) -> None:
    _append(PLACEMENTS_FILE, PLACEMENT_FIELDS, p.to_dict())


def add_milestone(m: Milestone) -> None:
    _append(MILESTONES_FILE, MILESTONE_FIELDS, m.to_dict())


def list_cohorts() -> pd.DataFrame:
    return pd.read_csv(COHORTS_FILE) if COHORTS_FILE.exists() else pd.DataFrame()


def list_placements() -> pd.DataFrame:
    return pd.read_csv(PLACEMENTS_FILE) if PLACEMENTS_FILE.exists() else pd.DataFrame()


def list_nurses() -> pd.DataFrame:
    return pd.read_csv(NURSE_PROFILES_FILE) if NURSE_PROFILES_FILE.exists() else pd.DataFrame()


def list_milestones() -> pd.DataFrame:
    return pd.read_csv(MILESTONES_FILE) if MILESTONES_FILE.exists() else pd.DataFrame()


# ─── Metrics ────────────────────────────────────────────────────────
def cohort_metrics() -> dict:
    """Aggregate production metrics across cohorts."""
    cohorts = list_cohorts()
    placements = list_placements()
    nurses = list_nurses()

    if cohorts.empty:
        return {
            "n_cohorts": 0, "n_nurses": 0, "n_placements": 0,
            "n_active": 0, "n_systems": 0,
            "by_cohort": [],
        }

    n_active_placements = (
        placements["status"] == "active"
    ).sum() if not placements.empty else 0

    by_cohort = []
    for _, c in cohorts.iterrows():
        n_in_cohort = (nurses["cohort_id"] == c["cohort_id"]).sum() if not nurses.empty else 0
        n_deployed = 0
        if not placements.empty and not nurses.empty:
            n_deployed = (
                placements["nurse_id"].isin(
                    nurses[nurses["cohort_id"] == c["cohort_id"]]["nurse_id"]
                )
            ).sum()
        yield_pct = n_deployed / max(c["target_size"], 1) * 100
        by_cohort.append({
            "cohort_id": c["cohort_id"],
            "cohort_name": c["cohort_name"],
            "target_size": int(c["target_size"]),
            "actual_size": int(c["actual_size"]),
            "deployed": int(n_deployed),
            "yield_pct": yield_pct,
            "status": c["status"],
        })

    return {
        "n_cohorts": len(cohorts),
        "n_nurses": len(nurses),
        "n_placements": len(placements),
        "n_active": int(n_active_placements),
        "n_systems": int(placements["health_system_id"].nunique()) if not placements.empty else 0,
        "by_cohort": by_cohort,
    }


def retention_curve() -> pd.DataFrame:
    """Compute monthly retention curve for active + completed placements."""
    placements = list_placements()
    if placements.empty:
        return pd.DataFrame()
    placements["placement_date"] = pd.to_datetime(placements["placement_date"], errors="coerce")
    placements = placements.dropna(subset=["placement_date"])
    today = pd.Timestamp.today()
    rows = []
    for _, p in placements.iterrows():
        months_to_today = (today - p["placement_date"]).days / 30
        was_active_at = lambda m: m <= months_to_today and (
            p["status"] == "active" or
            (p["status"] == "departed_early" and
             (pd.to_datetime(p["departed_date"]) - p["placement_date"]).days / 30 >= m)
        )
        for m in range(0, 37, 3):  # every 3 months for 3 years
            rows.append({"month": m, "nurse_id": p["nurse_id"],
                         "still_active": bool(was_active_at(m))})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    curve = df.groupby("month")["still_active"].mean().reset_index()
    curve["retention_pct"] = curve["still_active"] * 100
    return curve[["month", "retention_pct"]]


# ─── Seed demo data ─────────────────────────────────────────────────
def seed_demo_data(force: bool = False) -> None:
    """Seed a few cohorts + nurses + placements for development."""
    if COHORTS_FILE.exists() and not force:
        return
    # 3 cohorts
    cohorts = [
        Cohort(
            cohort_id="2024-Q3-PHI", cohort_name="Q3 2024 Philippines Cohort",
            start_year=2024, start_quarter=3, target_size=30, actual_size=28,
            status="deployed", origin_country="Philippines",
            program_type="F-1 student visa pipeline",
            expected_start_year=2025, expected_start_quarter=2,
            notes="First fully-deployed cohort under v2 program.",
        ),
        Cohort(
            cohort_id="2024-Q4-IND", cohort_name="Q4 2024 India Cohort",
            start_year=2024, start_quarter=4, target_size=25, actual_size=24,
            status="in_pipeline", origin_country="India",
            program_type="F-1 student visa pipeline",
            expected_start_year=2025, expected_start_quarter=3,
        ),
        Cohort(
            cohort_id="2025-Q1-PHI", cohort_name="Q1 2025 Philippines Cohort",
            start_year=2025, start_quarter=1, target_size=40, actual_size=38,
            status="in_pipeline", origin_country="Philippines",
            program_type="F-1 student visa pipeline",
            expected_start_year=2025, expected_start_quarter=4,
        ),
    ]
    for c in cohorts:
        add_cohort(c)

    # ~10 demo nurses across cohorts
    nurses = [
        NurseProfile("N0001", "Maria S.", "2024-Q3-PHI", "Philippines",
                     "passed", "2025-01-15", "Med/Surg", "CA", "2025-02-10",
                     "2025-02-15"),
        NurseProfile("N0002", "James K.", "2024-Q3-PHI", "Philippines",
                     "passed", "2025-01-20", "ICU", "TX", "2025-02-25",
                     "2025-03-01"),
        NurseProfile("N0003", "Priya R.", "2024-Q3-PHI", "Philippines",
                     "passed", "2025-01-22", "OR Circulating", "FL", "2025-03-05",
                     "2025-03-10"),
        NurseProfile("N0004", "Anjali D.", "2024-Q4-IND", "India",
                     "not_taken", None, "Med/Surg", "CA", None, None),
        NurseProfile("N0005", "Roberto M.", "2025-Q1-PHI", "Philippines",
                     "not_taken", None, "ER", "TX", None, None),
    ]
    for n in nurses:
        add_nurse(n)

    placements = [
        Placement("P0001", "N0001", "050070", "KFH - SOUTH SAN FRANCISCO",
                  "kaiser_permanente", "2025-02-15", 145000.0, "Med/Surg", 36,
                  "active", customer_satisfaction_score=5),
        Placement("P0002", "N0002", "450291", "MEMORIAL HERMANN - HOUSTON",
                  "memorial_hermann", "2025-03-01", 138000.0, "ICU", 36,
                  "active", customer_satisfaction_score=5),
        Placement("P0003", "N0003", "100024", "CLEVELAND CLINIC FLORIDA",
                  "cleveland_clinic", "2025-03-10", 132000.0, "OR Circulating", 36,
                  "active", customer_satisfaction_score=4),
    ]
    for p in placements:
        add_placement(p)

    # A few milestones
    milestones = [
        Milestone("M0001", "N0001", "nclex_passed", "2025-01-15", "First-attempt pass"),
        Milestone("M0002", "N0001", "first_start", "2025-02-15", "Kaiser SF onboarded"),
        Milestone("M0003", "N0002", "nclex_passed", "2025-01-20", "First-attempt pass"),
        Milestone("M0004", "N0002", "first_start", "2025-03-01", "Memorial Hermann onboarded"),
        Milestone("M0005", "N0003", "nclex_passed", "2025-01-22"),
        Milestone("M0006", "N0003", "first_start", "2025-03-10"),
    ]
    for m in milestones:
        add_milestone(m)


if __name__ == "__main__":
    seed_demo_data()
    metrics = cohort_metrics()
    print(json.dumps(metrics, indent=2, default=str))
