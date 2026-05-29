"""
Real-time wage signal from public RN job-posting feeds.

The BLS OEWS annual release lags 6-9 months. Job postings give us *today's*
wage signal for any MSA. This module is the persistence + aggregation layer.

═══════════════════════════════════════════════════════════════════════════
HOW THE PROVIDER STACK WORKS
═══════════════════════════════════════════════════════════════════════════
Each provider is a function that returns list[dict] of posting records with
the standardized schema below. Add a provider to ACTIVE_PROVIDERS and it
will be polled on every fetch_and_persist() call.

Standardized posting schema:
    source              str    e.g. "usajobs", "adzuna", "manual_csv"
    title               str    job title
    link                str    URL to the posting
    posted_at           str    ISO date when listed
    state               str    2-letter state code if parseable
    wage_low            float  low end of advertised wage range (annual $)
    wage_high           float  high end of advertised wage range (annual $)
    description_snippet str    first 300 chars of description

═══════════════════════════════════════════════════════════════════════════
WHY THIS MODULE DOES NOT AUTO-SCRAPE INDEED / LINKEDIN
═══════════════════════════════════════════════════════════════════════════
  1. Their robots.txt + ToS forbid scraping without a partnership agreement.
  2. Real scraping would require rotating proxies + headless browsers, which
     is a separate infrastructure investment.
  3. Florence should partner with the source or buy API access — the legal
     and reliability tradeoffs are not worth the cost-savings of scraping.

═══════════════════════════════════════════════════════════════════════════
HOW TO ACTIVATE A PROVIDER
═══════════════════════════════════════════════════════════════════════════

  USAJOBS public API (FREE — register at developer.usajobs.gov):
      export USAJOBS_API_KEY="..."
      export USAJOBS_API_EMAIL="you@florence.com"
      # _fetch_usajobs() is already implemented; will activate automatically.

  Adzuna (FREE TIER 250 calls/month — register at developer.adzuna.com):
      export ADZUNA_APP_ID="..."
      export ADZUNA_APP_KEY="..."
      # _fetch_adzuna() is already implemented; will activate automatically.

  Manual CSV drops (always on):
      Drop a CSV into data/job_postings/manual/*.csv with the standardized
      schema and it will be picked up. Useful for one-off batches you
      gather from public reports.
"""
from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from . import DATA_DIR


# ─── Provider 1: USAJOBS public API (requires free key) ─────────────
def _fetch_usajobs() -> list[dict]:
    """Fetch RN postings from data.usajobs.gov. Free but requires API key.

    Skips silently if USAJOBS_API_KEY + USAJOBS_API_EMAIL are not set.
    """
    api_key = os.environ.get("USAJOBS_API_KEY")
    email = os.environ.get("USAJOBS_API_EMAIL")
    if not (api_key and email):
        return []

    try:
        r = requests.get(
            "https://data.usajobs.gov/api/search",
            params={
                "Keyword": "registered nurse",
                "ResultsPerPage": 50,
                "Page": 1,
            },
            headers={
                "Authorization-Key": api_key,
                "User-Agent": email,
                "Host": "data.usajobs.gov",
            },
            timeout=30,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  USAJOBS API error: {e}")
        return []

    items: list[dict] = []
    data = r.json()
    for hit in (data.get("SearchResult") or {}).get("SearchResultItems", []):
        d = (hit.get("MatchedObjectDescriptor") or {})
        title = d.get("PositionTitle", "")
        link = d.get("PositionURI", "")
        pub = d.get("PublicationStartDate", "")
        locs = d.get("PositionLocation") or []
        state = None
        for loc in locs:
            code = (loc.get("LocationName") or "")
            # e.g. "San Francisco, California"
            for tok in code.split(","):
                tok = tok.strip()
                if len(tok) == 2 and tok.isupper():
                    state = tok
                    break
        pay = (d.get("PositionRemuneration") or [{}])[0]
        try:
            wage_low = float(pay.get("MinimumRange") or 0) or None
            wage_high = float(pay.get("MaximumRange") or 0) or None
        except Exception:
            wage_low, wage_high = None, None
        items.append({
            "source": "usajobs",
            "title": title,
            "link": link,
            "posted_at": pub,
            "state": state,
            "wage_low": wage_low,
            "wage_high": wage_high,
            "description_snippet": (d.get("UserArea") or {}).get(
                "Details", {}).get("JobSummary", "")[:300],
        })
    return items


# ─── Provider 2: Adzuna (requires free tier API key) ────────────────
def _fetch_adzuna() -> list[dict]:
    """Adzuna /jobs/us/search. 250 free calls/month at developer.adzuna.com."""
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    try:
        r = requests.get(
            "https://api.adzuna.com/v1/api/jobs/us/search/1",
            params={
                "app_id": app_id, "app_key": app_key,
                "what": "registered nurse",
                "results_per_page": 50,
                "max_days_old": 30,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  Adzuna error: {e}")
        return []

    items = []
    for j in data.get("results", []):
        area = (j.get("location") or {}).get("area") or []
        state = area[1] if len(area) > 1 else None
        items.append({
            "source": "adzuna",
            "title": j.get("title"),
            "link": j.get("redirect_url"),
            "posted_at": j.get("created"),
            "state": state,
            "wage_low": j.get("salary_min"),
            "wage_high": j.get("salary_max"),
            "description_snippet": (j.get("description") or "")[:300],
        })
    return items


# ─── Provider 3: Manual CSV drops (always on) ───────────────────────
MANUAL_FIELDS = ["source", "title", "link", "posted_at", "state",
                 "wage_low", "wage_high", "description_snippet"]


def _fetch_manual_csv() -> list[dict]:
    """Read any CSVs the operator dropped into data/job_postings/manual/.

    Each CSV must have the standardized schema (see module docstring).
    Use this for one-off batches: e.g. quarterly Premier or Vizient
    workforce reports that publish RN wage ranges by metro.
    """
    manual_dir = DATA_DIR / "job_postings" / "manual"
    manual_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for csv_path in sorted(manual_dir.glob("*.csv")):
        try:
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Coerce numeric fields
                    for k in ("wage_low", "wage_high"):
                        v = row.get(k, "")
                        try:
                            row[k] = float(v) if v not in ("", None) else None
                        except (TypeError, ValueError):
                            row[k] = None
                    row.setdefault("source", csv_path.stem)
                    items.append(row)
        except Exception as e:
            print(f"  Manual CSV error ({csv_path.name}): {e}")
    return items


ACTIVE_PROVIDERS = [
    ("usajobs", _fetch_usajobs),
    ("adzuna", _fetch_adzuna),
    ("manual_csv", _fetch_manual_csv),
]


# ─── Persistence + aggregation ──────────────────────────────────────
def fetch_and_persist() -> pd.DataFrame:
    today = date.today()
    out_dir = DATA_DIR / "job_postings"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_items: list[dict] = []
    configured = 0
    for name, fetcher in ACTIVE_PROVIDERS:
        items = fetcher()
        if items:
            configured += 1
            print(f"[{name}] {len(items)} postings")
            all_items.extend(items)
        else:
            print(f"[{name}] not configured / no results")

    if not all_items:
        print("\nNo postings collected. Configure at least one provider:")
        print("  - USAJOBS_API_KEY + USAJOBS_API_EMAIL  (free, register at developer.usajobs.gov)")
        print("  - ADZUNA_APP_ID + ADZUNA_APP_KEY      (free tier, 250/mo, developer.adzuna.com)")
        print("  - Drop CSVs into data/job_postings/manual/")
        return pd.DataFrame()

    df = pd.DataFrame(all_items)
    df["fetched_at"] = today.isoformat()
    snap = out_dir / f"{today.isoformat()}.csv"
    df.to_csv(snap, index=False)

    # Append to history
    hist = out_dir / "long_history.csv"
    existing = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
    combined = pd.concat([existing, df]).drop_duplicates(
        subset=["title", "link"], keep="last")
    combined.to_csv(hist, index=False)
    print(f"\n✓ {len(df)} postings → {snap}")
    print(f"✓ History: {hist} ({len(combined):,} rows total)")
    return df


def wage_signal_by_state() -> pd.DataFrame:
    """Aggregate posted wages by state (where parsed)."""
    hist = DATA_DIR / "job_postings" / "long_history.csv"
    if not hist.exists():
        return pd.DataFrame()
    df = pd.read_csv(hist)
    df = df.dropna(subset=["state", "wage_low"])
    if df.empty:
        return df
    df["wage_mid"] = df[["wage_low", "wage_high"]].mean(axis=1)
    agg = df.groupby("state").agg(
        n_postings=("wage_mid", "count"),
        median_wage=("wage_mid", "median"),
        mean_wage=("wage_mid", "mean"),
    ).reset_index()
    return agg.sort_values("median_wage", ascending=False)


def seed_demo_manual_csv() -> Path:
    """Create a small example manual CSV so the framework has data to show.

    Numbers below are illustrative ranges drawn from public job-board summaries
    (not a specific posting). Replace with your own observations.
    """
    manual_dir = DATA_DIR / "job_postings" / "manual"
    manual_dir.mkdir(parents=True, exist_ok=True)
    path = manual_dir / "demo_seed.csv"
    if path.exists():
        return path
    rows = [
        ("demo_seed", "RN — Med/Surg", "https://example.com/1", "2026-05-01", "CA",  118000, 142000, "Acute care, 36hr"),
        ("demo_seed", "RN — ICU",      "https://example.com/2", "2026-05-03", "CA",  135000, 168000, "ICU stepdown"),
        ("demo_seed", "RN — Med/Surg", "https://example.com/3", "2026-05-05", "TX",   78000,  92000, "Acute care"),
        ("demo_seed", "RN — ER",       "https://example.com/4", "2026-05-07", "TX",   88000, 108000, "Level II trauma"),
        ("demo_seed", "RN — Med/Surg", "https://example.com/5", "2026-05-10", "FL",   72000,  88000, "Med/Surg float"),
        ("demo_seed", "RN — Telemetry","https://example.com/6", "2026-05-11", "FL",   78000,  96000, "Tele float"),
        ("demo_seed", "RN — Med/Surg", "https://example.com/7", "2026-05-12", "NY",  102000, 124000, "Acute care"),
        ("demo_seed", "RN — OR",       "https://example.com/8", "2026-05-13", "NY",  118000, 145000, "Surgical services"),
        ("demo_seed", "RN — ICU",      "https://example.com/9", "2026-05-15", "WA",  125000, 152000, "ICU"),
        ("demo_seed", "RN — Med/Surg", "https://example.com/10","2026-05-18", "IL",   84000, 104000, "Acute care"),
    ]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(MANUAL_FIELDS)
        w.writerows(rows)
    return path


def main():
    df = fetch_and_persist()
    if df.empty:
        print("\nSeeding a small demo CSV so the framework has data to show…")
        seed_demo_manual_csv()
        df = fetch_and_persist()
    if not df.empty:
        wage_agg = wage_signal_by_state()
        if not wage_agg.empty:
            print("\n=== Posted wage by state (job-postings signal) ===")
            print(wage_agg.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
