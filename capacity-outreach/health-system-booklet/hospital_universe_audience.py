"""
hospital_universe_audience.py
=============================
Wire the booklet's audience to the REAL data: aggregate the facility-level
`data/hospital_universe.csv` (CMS HCRIS + BLS) by health system, then price each
system with the existing Workforce Economist engine (`pricing_engine.price`) to get
the two commercial numbers the booklet shows:

    list_rate     ← PricingResult.florence_monthly_fee_per_rn
    effective_cost← PricingResult.fica_adjusted_effective_cost_per_rn_month

Structural facts come straight from the universe:
    nFacilities   ← count of facilities in the system
    totalRnNeed   ← sum of estimated_rn_need_fte

`systems_from_universe()` returns dicts shaped for hospital_audience.build_audience_csv.
Addresses are NOT in the universe — they come from the CRM / HQ list at send time
(left blank here, filled before a real Lob run). Pricing reuses the engine, so the
mailpiece never invents a fee. Systems the engine flags for manual review are skipped
(or kept with pricing omitted) rather than guessed.

Usage:
    from hospital_universe_audience import systems_from_universe
    from hospital_audience import build_audience_csv
    systems = systems_from_universe(limit=25)               # top systems by RN need
    build_audience_csv(systems, "hospital_run.csv", campaign_id="cmp_q3")
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

# Reuse the Workforce Economist pricing engine (repo root, two levels up).
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

UNIVERSE_CSV = os.path.join(_ROOT, "data", "hospital_universe.csv")


def _f(v, default=0.0):
    try:
        x = float(v)
        return default if x != x else x  # NaN guard
    except (TypeError, ValueError):
        return default


def _aggregate(universe_csv: str = UNIVERSE_CSV):
    """Group facilities by health system → blended per-hour economics + structural totals."""
    groups: dict[str, dict] = {}
    facilities: dict[str, list] = defaultdict(list)
    with open(universe_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("health_system_id") or "").strip()
            name = (row.get("health_system") or "").strip()
            if not sid or not name:
                continue  # unaffiliated facility — skip system rollup
            low = name.lower()
            if "independent" in low or "unknown" in low or low in {"n/a", "none"}:
                continue  # catch-all bucket, not a real targetable system
            facilities[sid].append(row)
            g = groups.setdefault(sid, {"id": sid, "name": name, "states": defaultdict(int)})
            st = (row.get("state") or "").strip().upper()
            if st:
                g["states"][st] += 1
    out = []
    for sid, rows in facilities.items():
        g = groups[sid]
        n = len(rows)
        need = sum(_f(r.get("estimated_rn_need_fte")) for r in rows)
        # FTE-weighted blend of the loaded per-hour inputs the pricing engine reads.
        def wmean(field):
            num = sum(_f(r.get(field)) * (_f(r.get("hcris_total_fte")) or 1) for r in rows)
            den = sum((_f(r.get("hcris_total_fte")) or 1) for r in rows)
            return num / den if den else 0.0
        dom_state = max(g["states"].items(), key=lambda kv: kv[1])[0] if g["states"] else ""
        out.append({
            "id": sid, "name": g["name"], "nFacilities": n, "totalRnNeed": round(need),
            "state": dom_state,
            "taxable_wage_per_hour": wmean("taxable_wage_per_hour"),
            "benefit_load_per_hour": wmean("benefit_load_per_hour"),
            "all_in_agency_per_hour": wmean("all_in_agency_per_hour"),
        })
    return out


def _price(system: dict) -> tuple[float | None, float | None]:
    """(list_rate, effective_cost) from the pricing engine, or (None, None) if it
    flags manual review / can't price. Never invents a fee."""
    try:
        from pricing_engine import HospitalProfile, price
        prof = HospitalProfile(
            name=system["name"], city="", state=system.get("state", ""),
            taxable_wage_per_hour=system["taxable_wage_per_hour"],
            benefit_load_per_hour=system["benefit_load_per_hour"],
            all_in_agency_per_hour=system["all_in_agency_per_hour"],
        )
        r = price(prof, system_id=system["id"])
        if getattr(r, "manual_review", False):
            return None, None
        fee = round(r.florence_monthly_fee_per_rn)
        eff = round(r.fica_adjusted_effective_cost_per_rn_month)
        if fee <= 0 or eff <= 0:
            return None, None  # degenerate (e.g. agency premium ≤ loaded cost) — not mailable
        return fee, eff
    except Exception:
        return None, None


def systems_from_universe(limit: int | None = None, ids: list[str] | None = None,
                          require_pricing: bool = True, universe_csv: str = UNIVERSE_CSV) -> list[dict]:
    """Real health systems shaped for build_audience_csv. Sorted by RN need (desc).
    `require_pricing` drops systems the engine won't auto-price (the safe default for
    a mailpiece). Addresses are blank — join the CRM HQ list before a live send."""
    systems = _aggregate(universe_csv)
    if ids:
        wanted = {i.lower() for i in ids}
        systems = [s for s in systems if s["id"].lower() in wanted or s["name"].lower() in wanted]
    systems.sort(key=lambda s: s["totalRnNeed"], reverse=True)
    out = []
    for s in systems:
        fee, eff = _price(s)
        if fee is None and require_pricing:
            continue
        s["medianFee"] = fee if fee is not None else 0
        s["effectiveLow"] = eff if eff is not None else 0
        s["priced"] = fee is not None
        # Address placeholders — replaced by the CRM HQ join at send time.
        s.setdefault("contact_name", "Chief Nursing Officer")
        s.setdefault("address_line1", "")
        s.setdefault("address_city", s.get("state", ""))
        s.setdefault("address_state", s.get("state", ""))
        s.setdefault("address_zip", "")
        out.append(s)
        if limit and len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rows = systems_from_universe(limit=n)
    for s in rows:
        print(f"  {s['name'][:34]:34}  facilities={s['nFacilities']:>4}  rn_need={s['totalRnNeed']:>7,}  "
              f"fee=${s['medianFee']:,}  effective=${s['effectiveLow']:,}")
    print(f"\n{len(rows)} priced systems (of the full universe).")
