"""
Smoke test: every nav view in app.py renders with no exception.

The key regression guard for unattended development — if any view breaks, this
fails. Runnable under pytest or as a plain script.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
APP = str(ROOT / "app.py")

VIEWS = [
    "inpatient", "today", "outpatient", "funnel", "contacts", "call_center", "growth",
    "market_intel", "forecast", "national_map", "health_systems",
    "system_ownership", "price_hospital", "hospital_table", "market_view",
    "elasticity", "calibration_sweep", "data_quality", "data_provenance",
    "playbook", "onboarding", "pipeline",
]


def _check(view: str) -> None:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.session_state["nav_view"] = view
    at.run()
    # at.exception is an ElementList (empty == no exception), never None.
    assert not at.exception, f"{view}: {at.exception}"


def test_all_views_load():
    for v in VIEWS:
        _check(v)


if __name__ == "__main__":
    ok = True
    for v in VIEWS:
        try:
            _check(v)
            print(f"PASS  {v}")
        except Exception as e:
            ok = False
            print(f"FAIL  {v}: {str(e)[:200]}")
    print(f"\n{'ALL VIEWS GREEN' if ok else 'SMOKE FAILED'}")
    sys.exit(0 if ok else 1)
