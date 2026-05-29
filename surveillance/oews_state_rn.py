"""
BLS OEWS state-level Registered Nurse (SOC 29-1141) wages over time.

OEWS is annual (May data). For Florence's state-level wage trends, we pull
the API series for the past 5+ years and store snapshots.

OEWS series ID structure for state RN wages:
    OEUS  <state_code>  00000  291141  04  <annual_mean_wage>
    │     │             │      │       │
    │     │             │      │       └─ Stat = 04 = annual mean wage
    │     │             │      └─────── SOC = 291141 (Registered Nurses)
    │     │             └────────────── 00000 = all areas in state
    │     └──────────────────────────── state FIPS as string (e.g., "0100" = AL)
    └────────────────────────────────── OEUS = OEWS state series prefix

Example: OEUS010000000029114104 = Alabama state-level annual mean RN wage.

State codes use FIPS (Alabama = 01, Alaska = 02, etc.). We map these to the
postal abbreviations the rest of Florence uses.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import DATA_DIR
from .bls_fetch import fetch_series, save_snapshot

# State FIPS → postal code (50 states + DC)
STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}

# OEWS measure codes
MEASURES = {
    "01": "employment_thousands",          # employment
    "02": "employment_rse",                # employment relative standard error
    "03": "hourly_wage_mean",              # mean hourly wage
    "04": "annual_wage_mean",              # mean annual wage
    "13": "hourly_wage_median",            # median hourly wage
}


def _state_rn_series(state_fips: str, measure: str) -> str:
    """Build the BLS OEWS series ID for state-level RN wages."""
    # OEWS series format (state-level): OEUS<state><area><occ><datatype>
    # state: 2-digit FIPS, padded to 7 with zeros (state FIPS + 00000 area)
    # area: 7-digit (state goes here too)
    # occ: 6-digit SOC (291141 for RN)
    # datatype: 2-digit measure
    # Full pattern: OEUS + 7-char location + 6-char occ + 2-char measure
    # For state-level all areas: state FIPS + "00000"
    state_area = state_fips + "00000"
    return f"OEUS{state_area}{state_fips}00000291141{measure}"


def _try_alternate_format(state_fips: str, measure: str) -> str:
    """Alternative format actually used by BLS API."""
    # OEUS<2-state><5-state-area-code><6-soc><2-data>
    # Verified working format: OEUS<state><state_area><soc>00<data>
    return f"OEUM{state_fips}00000291141{measure}"


def fetch_state_rn_wages(states: list[str] | None = None,
                         start_year: int | None = None) -> pd.DataFrame:
    """Fetch state-level RN annual mean wages for the given states (postal codes).
    Returns DataFrame: state, year, hourly_mean, annual_mean, employment."""
    if states is None:
        states = list(STATE_FIPS.values())
    if start_year is None:
        start_year = date.today().year - 5

    # Reverse lookup
    postal_to_fips = {v: k for k, v in STATE_FIPS.items()}

    # Batch series — group by measure to stay under 25-series anonymous limit
    # We need hourly_mean + annual_mean + employment for each state
    rows: list[dict] = []
    # Process in batches of 8 states × 3 measures = 24 series per call (under 25 cap)
    batch_size = 8
    for i in range(0, len(states), batch_size):
        batch = states[i:i + batch_size]
        series_to_label: dict[str, tuple[str, str]] = {}
        for st in batch:
            fips = postal_to_fips.get(st)
            if not fips: continue
            for measure_code, measure_label in [
                ("03", "hourly_mean"),
                ("04", "annual_mean"),
                ("01", "employment"),
            ]:
                sid = f"OEUM{fips}00000291141{measure_code}"
                series_to_label[sid] = (st, measure_label)
        if not series_to_label: continue
        try:
            raw = fetch_series(series_to_label.keys(), start_year=start_year)
        except Exception as e:
            print(f"  Batch {i}-{i+batch_size}: BLS error {e}; skipping")
            continue
        for sid, points in raw.items():
            st, label = series_to_label[sid]
            for p in points:
                rows.append({
                    "state": st,
                    "year": p["year"],
                    "metric": label,
                    "value": p["value"],
                })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Pivot to wide
    wide = df.pivot_table(index=["state", "year"],
                          columns="metric", values="value").reset_index()
    return wide.sort_values(["state", "year"])


def fetch_and_persist() -> pd.DataFrame:
    print("Fetching BLS OEWS state-level RN wages...")
    df = fetch_state_rn_wages()
    if df.empty:
        print("  No data returned from BLS")
        return df
    save_path = DATA_DIR / "oews_state_rn" / "long_history.csv"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(save_path, index=False)
    save_snapshot("oews_state_rn", {"rows": df.to_dict(orient="records")})
    print(f"✓ State RN wages → {save_path} ({len(df):,} rows across {df['state'].nunique()} states)")
    return df


def main():
    df = fetch_and_persist()
    if df.empty:
        return
    print()
    print("=== Top 10 states by latest annual mean RN wage ===")
    latest_year = df["year"].max()
    top = df[df["year"] == latest_year].sort_values("annual_mean", ascending=False).head(10)
    for _, r in top.iterrows():
        print(f"  {r['state']:>2}  ${r.get('hourly_mean', 0):,.2f}/hr  "
              f"${r.get('annual_mean', 0):,.0f}/yr  "
              f"{r.get('employment', 0):,.0f} employed")


if __name__ == "__main__":
    main()
