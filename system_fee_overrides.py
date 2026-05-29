"""
Per-system flat-fee overrides for the FLAT_PLACEMENT_FEE pricing mode.

Some systems will accept (or demand) a different per-RN placement fee than
the global default. Examples:
  - Kaiser Permanente: $50K per RN (deck reference)
  - HCA: $40K per RN (high volume, pricing power)
  - Sutter Health: $60K per RN (premium market, smaller volume)
  - Mass General Brigham: $55K per RN

This module stores per-system overrides in `data/system_flat_fee_overrides.json`
and exposes lookup/save APIs. Applied at pricing time when the mode is
FLAT_PLACEMENT_FEE.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

DATA_DIR = Path(__file__).parent / "data"
FEE_OVERRIDES_PATH = DATA_DIR / "system_flat_fee_overrides.json"


@dataclass
class FlatFeeOverride:
    system_id: str
    system_name: str
    flat_fee_per_rn: float
    term_months: int = 36
    note: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)


def load_overrides() -> dict[str, FlatFeeOverride]:
    """Return {system_id: override}. Empty if file missing."""
    if not FEE_OVERRIDES_PATH.exists():
        return {}
    try:
        with open(FEE_OVERRIDES_PATH) as f:
            blob = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, FlatFeeOverride] = {}
    for r in blob.get("overrides", []):
        out[str(r["system_id"])] = FlatFeeOverride(
            system_id=str(r["system_id"]),
            system_name=str(r.get("system_name", "")),
            flat_fee_per_rn=float(r["flat_fee_per_rn"]),
            term_months=int(r.get("term_months", 36)),
            note=str(r.get("note", "")),
            created_at=str(r.get("created_at", "")),
        )
    return out


def save_overrides(records: Iterable[FlatFeeOverride]) -> None:
    FEE_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "version": 1,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "overrides": [r.to_dict() for r in records],
    }
    tmp = FEE_OVERRIDES_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=2)
    tmp.replace(FEE_OVERRIDES_PATH)


def overrides_mtime() -> float:
    return FEE_OVERRIDES_PATH.stat().st_mtime if FEE_OVERRIDES_PATH.exists() else 0.0


def fee_for_system(system_id: str, default_fee: float = 50_000.0,
                   default_term: int = 36) -> tuple[float, int]:
    """Return (flat_fee_per_rn, term_months) for the given system_id."""
    ov = load_overrides().get(str(system_id))
    if ov is None:
        return (default_fee, default_term)
    return (ov.flat_fee_per_rn, ov.term_months)


def upsert(system_id: str, system_name: str, flat_fee_per_rn: float,
           term_months: int = 36, note: str = "") -> None:
    """Add or update an override."""
    records = load_overrides()
    records[str(system_id)] = FlatFeeOverride(
        system_id=str(system_id),
        system_name=system_name,
        flat_fee_per_rn=float(flat_fee_per_rn),
        term_months=int(term_months),
        note=note,
    )
    save_overrides(records.values())


def delete(system_id: str) -> bool:
    records = load_overrides()
    if str(system_id) not in records:
        return False
    del records[str(system_id)]
    save_overrides(records.values())
    return True


def delete_all() -> int:
    n = len(load_overrides())
    save_overrides([])
    return n


if __name__ == "__main__":
    print(f"Overrides file: {FEE_OVERRIDES_PATH}")
    overrides = load_overrides()
    print(f"Active flat-fee overrides: {len(overrides)}")
    for sid, ov in overrides.items():
        print(f"  {sid:<30}  ${ov.flat_fee_per_rn:>8,.0f} × {ov.term_months}mo  · {ov.note}")
