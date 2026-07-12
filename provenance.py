"""
Data provenance — the single source of truth for "as of when?".

Every buyer-facing surface (reco tab, exec summary, customer calculator)
renders its data vintage from here, so freshness claims can't silently drift
from reality. tests/test_data_freshness.py fails CI when a source ages past
its hard limit; the in-app badge turns amber at the soft limit.

Update SOURCES when a new vintage is ingested — that one edit updates every
surface and resets the freshness clock.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

# (label, vintage_label, vintage_date, soft_limit_months, hard_limit_months)
# soft: show amber in-app ("refresh soon"); hard: fail CI ("stale enough to
# embarrass us in front of a CFO").
SOURCES = [
    # OEWS releases annually each April; soft limit 24mo means the badge turns
    # amber as soon as a newer release exists un-ingested (May 2025 is out).
    ("RN wages", "BLS OEWS May 2024", dt.date(2024, 5, 1), 24, 32),
    ("Agency rates", "CMS HCRIS FY2023–FY2024 cost reports", dt.date(2024, 6, 30), 30, 42),
    ("System ownership", "NASHP HCT 2024 + CMS PECOS 2026-05", dt.date(2026, 5, 1), 14, 20),
]


def _months_old(d: dt.date, today: dt.date | None = None) -> int:
    t = today or dt.date.today()
    return (t.year - d.year) * 12 + (t.month - d.month)


def universe_refreshed() -> str:
    """When the priced universe itself was last rebuilt (file mtime)."""
    try:
        ts = (DATA_DIR / "hospital_universe.csv").stat().st_mtime
        return dt.date.fromtimestamp(ts).isoformat()
    except OSError:
        return "unknown"


def as_of_line() -> str:
    """One-line vintage statement for captions and report footers."""
    bits = " · ".join(v for _, v, *_ in SOURCES)
    return f"Sources: {bits} · universe refreshed {universe_refreshed()}"


def freshness() -> list[dict]:
    """Per-source age + status: 'fresh' | 'refresh_soon' | 'stale'."""
    out = []
    for label, vintage, date, soft, hard in SOURCES:
        age = _months_old(date)
        status = "stale" if age > hard else "refresh_soon" if age > soft else "fresh"
        out.append({"source": label, "vintage": vintage, "age_months": age,
                    "soft_limit": soft, "hard_limit": hard, "status": status})
    return out


def freshness_badge(st) -> None:
    """Amber caption when any source passes its soft limit; silent when fresh."""
    aging = [f for f in freshness() if f["status"] != "fresh"]
    if not aging:
        return
    names = ", ".join(f"{f['source']} ({f['vintage']}, {f['age_months']} mo old)"
                      for f in aging)
    st.warning(f"Data refresh due: {names}. Quotes still compute, but refresh "
               "before the next big pitch.", icon=":material/update:")
