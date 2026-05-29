"""
Generic BLS Public Data API client.

BLS API v2: https://api.bls.gov/publicAPI/v2/
- Anonymous: 25 series/day, 10 yr historical max, 3 yr/query, 200 req/day
- Registered (free key): 50 series/day, 20 yr historical, 500 req/day

For Florence's monthly cadence, anonymous is plenty. Register a key later
(https://data.bls.gov/registrationEngine/) if usage grows.

Series ID structure (e.g., JOLTS healthcare hires national):
    JTS  600000  HIR  L  R
    │    │       │    │  └─ Rate code (R) or level code (S)
    │    │       │    └──── L = Level or R = Rate
    │    │       └───────── HIR = Hires (HIL = Job openings, QUL = Quits, etc.)
    │    └───────────────── 600000 = Health care and social assistance NAICS code
    └────────────────────── JTS = JOLTS prefix

CES (Employment) series:
    CES   65   62   00   00   01
    │     │    │    │    │    └─ Data type code (01 = all employees)
    │     │    │    │    └────── Industry code (00 = all)
    │     │    │    └─────────── 00 = supersector total
    │     │    └──────────────── 62 = healthcare & social assistance
    │     └───────────────────── 65 = sector code prefix
    └─────────────────────────── CES = Current Employment Statistics

OEWS series — annual data, simpler.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def fetch_series(
    series_ids: Iterable[str],
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
) -> dict:
    """Fetch one or more BLS series.

    Returns a dict keyed by series ID with list of {year, period, value, latest}.
    """
    if end_year is None:
        end_year = date.today().year
    if start_year is None:
        start_year = end_year - 2

    payload = {
        "seriesid": list(series_ids),
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    if api_key:
        payload["registrationkey"] = api_key

    headers = {"Content-Type": "application/json"}
    r = requests.post(BLS_API_URL, data=json.dumps(payload), headers=headers, timeout=30)
    r.raise_for_status()
    body = r.json()

    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API: {body.get('status')} — {body.get('message')}")

    out: dict[str, list[dict]] = {}
    for series in body.get("Results", {}).get("series", []):
        sid = series["seriesID"]
        rows = []
        for d in series.get("data", []):
            rows.append({
                "year": int(d["year"]),
                "period": d["period"],
                "period_name": d.get("periodName", ""),
                "value": float(d["value"]) if d["value"] not in ("", "-") else None,
                "latest": d.get("latest", "") == "true",
            })
        out[sid] = rows
    return out


def save_snapshot(feed_name: str, data: dict) -> Path:
    """Persist a feed's response under data/surveillance/<feed>/YYYY-MM-DD.json."""
    from . import DATA_DIR
    feed_dir = DATA_DIR / feed_name
    feed_dir.mkdir(parents=True, exist_ok=True)
    out_path = feed_dir / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(data, indent=2))
    return out_path
