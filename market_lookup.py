"""
Market lookup — the data half of Demand Radar pricing.

`pricing_engine.price()` needs a local wage + agency-rate profile. Demand Radar
usually only knows {state, setting, role} for a scraped opening, so this module
turns that into the engine's inputs by taking medians from the hospital universe
(BLS wages + HCRIS agency rates + the Kaiser overlay already baked in). Pure
stdlib so it's importable in tests and the FastAPI app alike.
"""
from __future__ import annotations

import csv
import os
import statistics
from functools import lru_cache
from typing import Optional

_DATA = os.path.join(os.path.dirname(__file__), "data")


def _median(vals):
    clean = [v for v in vals if v is not None]
    return statistics.median(clean) if clean else None


@lru_cache(maxsize=1)
def _by_state() -> dict:
    out: dict[str, list[dict]] = {}
    path = os.path.join(_DATA, "hospital_universe.csv")
    if not os.path.exists(path):
        return out
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            st = (row.get("state") or "").strip().upper()
            if len(st) != 2:
                continue

            def num(k):
                try:
                    return float(row.get(k) or "")
                except ValueError:
                    return None

            out.setdefault(st, []).append(
                {
                    "wage": num("taxable_wage_per_hour"),
                    "benefit": num("benefit_load_per_hour"),
                    "agency": num("all_in_agency_per_hour"),
                    "premium": num("agency_premium_per_hour"),
                }
            )
    return out


def lookup_market(state: str, setting: Optional[str] = None, role: Optional[str] = None) -> dict:
    """State-level median wage + agency profile for an RN role. Falls back to the
    national median when the state is unknown. `setting` is recorded for context;
    agency-premium data is hospital-derived, so it is applied across settings."""
    st = (state or "").strip().upper()
    by_state = _by_state()
    rows = by_state.get(st, [])
    basis = "state"
    if not rows:
        rows = [r for rs in by_state.values() for r in rs]
        basis = "national"

    wage = _median([r["wage"] for r in rows])
    benefit = _median([r["benefit"] for r in rows])
    agency = _median([r["agency"] for r in rows if r["agency"] and r["agency"] > 0])
    premium = _median([r["premium"] for r in rows if r["premium"] is not None])
    n = len(rows)
    confidence = 0.85 if (basis == "state" and n >= 20) else 0.6 if (basis == "state" and n >= 5) else 0.35

    return {
        "state": st,
        "setting": setting,
        "role": role or "RN — Med/Surg",
        "taxable_wage_per_hour": round(wage, 2) if wage is not None else None,
        "benefit_load_per_hour": round(benefit, 2) if benefit is not None else None,
        "all_in_agency_per_hour": round(agency, 2) if agency is not None else None,
        "agency_premium_per_hour": round(premium, 2) if premium is not None else None,
        "n": n,
        "basis": basis,
        "agency_rate_confidence": confidence,
    }
