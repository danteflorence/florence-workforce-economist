"""
System-level agency-fee overlays per v2 Methodology §5.2.

Some health systems use MSP/VMS arrangements where additional agency fees are
billed at the ORG level (not allocated to facilities in HCRIS). The result is
that HCRIS-reported contract labor for those systems UNDERSTATES the true
all-in agency cost. We need to allocate that org-level overlay back to
facilities so per-hospital agency rates reflect reality.

v2 §5.2 formula:
    TotalAgencySpendUsed = BaseContractLaborSpend + AdditionalAgencyFee + OtherApprovedAgencyOverlay
    AdjustedAgencyRate = TotalAgencySpendUsed / ContractLaborHours
  Allocation:
    OverlayPerContractHour = AdditionalAgencyFee / TotalContractLaborHours
    FacilityAdditionalAgencyFee = FacilityContractLaborHours × OverlayPerContractHour

Documented overlays:
  - Kaiser Permanente: $622M annual underreporting (per user / AMN public filings).
    HCRIS captures direct contract labor wages but misses the MSP/AMN markup
    layer that flows through KP procurement budgets.

Add more systems here as their MSP arrangements become known. Until proven,
new systems default to overlay = 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class SystemOverlay:
    """A system-level agency-fee overlay. Two variants supported:

    1. Real disclosed (is_placeholder=False, additional_agency_fee_annual set):
       Use the exact annual $ amount (e.g., Kaiser's $622M per AMN 10-K).

    2. Placeholder (is_placeholder=True, placeholder_msp_pct set):
       Bump each facility's agency rate by placeholder_msp_pct × base_HCRIS_rate.
       The runtime slider can override the placeholder pct globally.
    """
    health_system_id: str
    health_system_name: str
    source: str
    as_of_year: int
    is_placeholder: bool = False
    additional_agency_fee_annual: float = 0.0
    placeholder_msp_pct: float = 0.0  # e.g., 0.25 for 25% markup placeholder


# Curated list of system-level overlays.
# Kaiser is the only system with disclosed dollar amount; others use a 25%
# placeholder markup until their MSP fee data becomes available.
SYSTEM_OVERLAYS: dict[str, SystemOverlay] = {
    # ─── Real disclosed ───────────────────────────────────────────────
    "kaiser_permanente": SystemOverlay(
        health_system_id="kaiser_permanente",
        health_system_name="Kaiser Permanente",
        additional_agency_fee_annual=622_000_000.0,
        source="User-disclosed; cross-referenced against AMN Healthcare 10-K filings "
               "and Kaiser Permanente Form 990 (KFH Permanente Medical Group reports).",
        as_of_year=2024,
        is_placeholder=False,
    ),

    # ─── Placeholders (25% default markup; tune via Streamlit slider) ─
    "hca": SystemOverlay(
        health_system_id="hca",
        health_system_name="HCA",
        source="Placeholder — MSP markup not yet disclosed; default 25% of base HCRIS rate.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "providence": SystemOverlay(
        health_system_id="providence",
        health_system_name="Providence",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "upmc": SystemOverlay(
        health_system_id="upmc",
        health_system_name="UPMC",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "ascension": SystemOverlay(
        health_system_id="ascension",
        health_system_name="Ascension",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "adventhealth": SystemOverlay(
        health_system_id="adventhealth",
        health_system_name="AdventHealth",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "christus_health": SystemOverlay(
        health_system_id="christus_health",
        health_system_name="CHRISTUS Health",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "ochsner": SystemOverlay(
        health_system_id="ochsner",
        health_system_name="Ochsner",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "sutter_health": SystemOverlay(
        health_system_id="sutter_health",
        health_system_name="Sutter Health",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "banner_health": SystemOverlay(
        health_system_id="banner_health",
        health_system_name="Banner Health",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "beth_israel_lahey_health": SystemOverlay(
        health_system_id="beth_israel_lahey_health",
        health_system_name="Beth Israel Lahey Health",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
    "rwjbarnabas_health": SystemOverlay(
        health_system_id="rwjbarnabas_health",
        health_system_name="RWJBarnabas Health",
        source="Placeholder — MSP markup not yet disclosed; default 25%.",
        as_of_year=2024,
        is_placeholder=True,
        placeholder_msp_pct=0.25,
    ),
}


def placeholder_system_ids(default_pct: float = 0.25) -> dict[str, float]:
    """Return {system_id: pct_to_use} for all placeholder systems.

    If a runtime override (e.g., from the Streamlit slider) is provided, all
    placeholder systems use that pct. Real-disclosed systems are not affected.
    """
    return {
        sys_id: default_pct
        for sys_id, ov in SYSTEM_OVERLAYS.items()
        if ov.is_placeholder
    }


def compute_facility_overlays(
    universe_csv: Path | str,
    hcris_rates_csv: Path | str,
) -> pd.DataFrame:
    """For each system with an overlay, allocate the org-level fee across
    member facilities by contract-labor-hour share.

    Returns DataFrame: ccn, additional_agency_fee_allocated, overlay_per_hour,
    overlay_source.
    """
    universe = pd.read_csv(universe_csv, dtype={"ccn": str, "health_system_id": str})
    universe["ccn"] = universe["ccn"].astype(str).str.zfill(6)
    hcris = pd.read_csv(hcris_rates_csv, dtype={"ccn": str})
    hcris["ccn"] = hcris["ccn"].astype(str).str.zfill(6)

    universe = universe.merge(
        hcris[["ccn", "contract_labor_hours", "contract_labor_dollars"]],
        on="ccn", how="left",
    )

    rows = []
    for system_id, ov in SYSTEM_OVERLAYS.items():
        # Skip placeholder systems — those are applied at PRICING TIME so the
        # Streamlit slider can adjust them without rebuilding the universe.
        if ov.is_placeholder:
            continue

        members = universe[universe["health_system_id"] == system_id].copy()
        if len(members) == 0:
            print(f"  [{ov.health_system_name}] no facilities found — skipping")
            continue
        members["effective_hours"] = members["contract_labor_hours"].fillna(0)
        if members["effective_hours"].sum() == 0:
            print(f"  [{ov.health_system_name}] no HCRIS hours available — cannot allocate.")
            continue

        total_hours = members["effective_hours"].sum()
        overlay_per_hour = ov.additional_agency_fee_annual / total_hours
        print(f"\n  [{ov.health_system_name}] (real-disclosed)")
        print(f"    Annual overlay:        ${ov.additional_agency_fee_annual/1e6:,.1f}M")
        print(f"    Total contract hours:  {total_hours:,.0f}")
        print(f"    Overlay per hour:      ${overlay_per_hour:.2f}/hr")
        print(f"    Member facilities:     {len(members):,}")

        for _, h in members.iterrows():
            hrs = float(h["effective_hours"]) if pd.notna(h["effective_hours"]) else 0.0
            if hrs > 0:
                allocated = hrs * overlay_per_hour
                rows.append({
                    "ccn": h["ccn"],
                    "name": h["name"],
                    "health_system_id": system_id,
                    "health_system_name": ov.health_system_name,
                    "hcris_contract_hours": hrs,
                    "overlay_per_hour": round(overlay_per_hour, 2),
                    "additional_agency_fee_allocated": round(allocated, 2),
                    "overlay_source": ov.source,
                    "overlay_as_of_year": ov.as_of_year,
                    "overlay_type": "real_disclosed",
                })

    # Report placeholder systems (informational only — applied at pricing time)
    placeholders = {sid: ov for sid, ov in SYSTEM_OVERLAYS.items() if ov.is_placeholder}
    if placeholders:
        print(f"\n  Placeholder systems (applied at pricing time via Streamlit slider):")
        for sid, ov in placeholders.items():
            n_facilities = (universe["health_system_id"] == sid).sum()
            print(f"    {ov.health_system_name:>32}  {n_facilities:>3} facilities  "
                  f"default {ov.placeholder_msp_pct:.0%} markup")

    return pd.DataFrame(rows)


def main() -> None:
    DATA_DIR = Path(__file__).parent / "data"
    out = compute_facility_overlays(
        DATA_DIR / "hospital_universe.csv",
        DATA_DIR / "hcris_agency_rates.csv",
    )
    output_path = DATA_DIR / "system_level_overlays.csv"
    out.to_csv(output_path, index=False)
    print(f"\nWrote {output_path}")
    print(f"Total allocated rows: {len(out):,}")
    if len(out):
        print("\nSample (Kaiser facilities):")
        print(out[["ccn", "name", "hcris_contract_hours",
                   "overlay_per_hour", "additional_agency_fee_allocated"]]
              .head(10).to_string(index=False))


if __name__ == "__main__":
    main()
