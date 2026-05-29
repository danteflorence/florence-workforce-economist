"""
CMS Care Compare quarterly refresh — staffing + ratings deltas.

CMS publishes quality data quarterly for Hospitals, Nursing Homes, Home Health,
Hospice. The most relevant signals for Florence:
  - Star rating (overall + staffing component)
  - RN hours per resident day (SNF)
  - Total nurse staffing hours (SNF)
  - Patient experience scores

Tracking these per CCN over time tells us:
  - Facilities whose staffing is DETERIORATING → urgent Florence pitch
  - Systems whose ratings just dropped → leadership pressure, openness to change
  - Facilities raising staffing → competitive wage pressure in that market

Pulls from data.cms.gov (Provider Data Catalog) which we already use for the
universe build. Comparison against previous snapshot identifies changes.

Run quarterly (CMS releases ~mid-quarter).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from . import DATA_DIR

# Provider Data Catalog dataset identifiers (the metastore IDs we used before)
DATASETS = {
    "nh_provider_info": {
        "id": "4pq5-n9py",
        "title": "Nursing Home Provider Information",
        "key": "CMS Certification Number (CCN)",
        "tracked_fields": [
            "Overall Rating",
            "Health Inspection Rating",
            "QM Rating",
            "Staffing Rating",
            "RN Staffing Rating",
            "Reported Nurse Aide Staffing Hours per Resident per Day",
            "Reported LPN Staffing Hours per Resident per Day",
            "Reported RN Staffing Hours per Resident per Day",
            "Reported Total Nurse Staffing Hours per Resident per Day",
            "Number of Citations from Infection Control Inspections",
        ],
    },
    "hh_provider_info": {
        "id": "6jpm-sxkc",
        "title": "Home Health Care Agencies",
        "key": "CMS Certification Number (CCN)",
        "tracked_fields": [
            "Quality of patient care star rating",
        ],
    },
    "hospice_provider_info": {
        "id": "yc9t-dgbk",
        "title": "Hospice General Information",
        "key": "CMS Certification Number (CCN)",
        "tracked_fields": [
            "Ownership Type",
        ],
    },
}


def _latest_download_url(dataset_id: str) -> str | None:
    """Look up the most recent CSV URL via the Provider Data Catalog metastore."""
    url = (
        f"https://data.cms.gov/provider-data/api/1/metastore/schemas/"
        f"dataset/items?identifier={dataset_id}"
    )
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            dist = data[0].get("distribution", [{}])[0]
            return dist.get("downloadURL")
    except Exception as e:
        print(f"  metastore lookup failed for {dataset_id}: {e}")
    return None


def fetch_snapshot(dataset_key: str) -> pd.DataFrame | None:
    info = DATASETS[dataset_key]
    feed_dir = DATA_DIR / "cms_care_compare" / dataset_key
    feed_dir.mkdir(parents=True, exist_ok=True)

    url = _latest_download_url(info["id"])
    if not url:
        return None

    print(f"  Downloading {info['title']} from {url[:80]}...")
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
    except Exception as e:
        print(f"  Download failed: {e}")
        return None

    raw_path = feed_dir / f"{date.today().isoformat()}.csv"
    raw_path.write_bytes(r.content)
    df = pd.read_csv(raw_path, low_memory=False, dtype={info["key"]: str},
                     encoding="utf-8", errors="replace")
    df[info["key"]] = df[info["key"]].astype(str).str.zfill(6)
    return df


def compare_to_previous(dataset_key: str, current: pd.DataFrame) -> list[dict]:
    """Identify CCNs whose tracked fields changed since the last snapshot."""
    feed_dir = DATA_DIR / "cms_care_compare" / dataset_key
    snapshots = sorted(feed_dir.glob("*.csv"))
    if len(snapshots) < 2:
        return []
    prev_path = snapshots[-2]
    info = DATASETS[dataset_key]
    try:
        prev = pd.read_csv(prev_path, low_memory=False,
                           dtype={info["key"]: str},
                           encoding="utf-8", errors="replace")
        prev[info["key"]] = prev[info["key"]].astype(str).str.zfill(6)
    except Exception:
        return []
    changes: list[dict] = []
    merged = current.merge(prev, on=info["key"], how="inner", suffixes=("", "_prev"))
    for field in info["tracked_fields"]:
        prev_field = f"{field}_prev"
        if field not in merged.columns or prev_field not in merged.columns:
            continue
        # Numeric delta where possible
        try:
            cur_vals = pd.to_numeric(merged[field], errors="coerce")
            old_vals = pd.to_numeric(merged[prev_field], errors="coerce")
            delta = cur_vals - old_vals
            sig = merged[delta.notna() & (delta.abs() >= 1)]  # 1-point change
            for _, r in sig.head(50).iterrows():
                changes.append({
                    "dataset": dataset_key,
                    "ccn": r[info["key"]],
                    "field": field,
                    "previous": r[prev_field],
                    "current": r[field],
                    "delta": float(cur_vals.loc[_]) - float(old_vals.loc[_]),
                })
        except Exception:
            # Categorical change
            sig = merged[merged[field] != merged[prev_field]]
            for _, r in sig.head(20).iterrows():
                changes.append({
                    "dataset": dataset_key,
                    "ccn": r[info["key"]],
                    "field": field,
                    "previous": r[prev_field],
                    "current": r[field],
                    "delta": None,
                })
    return changes


def main():
    print("CMS Care Compare quarterly refresh")
    all_changes = []
    for ds_key in DATASETS.keys():
        print(f"\n[{ds_key}]")
        df = fetch_snapshot(ds_key)
        if df is None:
            print(f"  Skipped — no data")
            continue
        print(f"  Snapshot saved ({len(df):,} rows)")
        changes = compare_to_previous(ds_key, df)
        print(f"  Detected {len(changes)} significant changes vs previous snapshot")
        all_changes.extend(changes)

    out = DATA_DIR / "cms_care_compare" / f"changes_{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_changes, indent=2, default=str))
    print(f"\n✓ Wrote {len(all_changes)} change-events → {out}")


if __name__ == "__main__":
    main()
