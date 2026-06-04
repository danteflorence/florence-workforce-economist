"""
Unified facility-level pricing table for the market map — inpatient hospitals
+ outpatient sites (ASC/SNF/HHA/dialysis/hospice), with a live reprice() so the
map can recolor under different FICA-offset / partner-markup / floor-ceiling
assumptions.

Reprice formula (matches the engine):
    fee       = clamp(FICA_savings_per_RN_mo / offset_pct, floor, ceiling)
    partner   = fee * (1 + markup_pct)          # AMN wholesale channel
    effective = max(fee - FICA_savings, 0)      # employer net after FICA offset
"""
from __future__ import annotations
import functools, io, zipfile
import numpy as np
import pandas as pd

DATA = "data/"
HOURS_MO = 156.0  # ~36 hrs/wk * 52 / 12, the engine's monthly-hours basis

DEFAULTS = dict(offset_pct=0.40, markup_pct=0.20, floor=750.0, ceiling=2000.0)


@functools.lru_cache(maxsize=1)
def _zip_centroids() -> pd.DataFrame:
    z = zipfile.ZipFile(DATA + "zcta_gazetteer.zip")
    name = [n for n in z.namelist() if n.endswith(".txt")][0]
    g = pd.read_csv(io.BytesIO(z.read(name)), sep="\t", dtype=str)
    g.columns = [c.strip() for c in g.columns]
    g = g.rename(columns={"GEOID": "zip", "INTPTLAT": "lat", "INTPTLONG": "lon"})
    g["zip"] = g["zip"].str.zfill(5)
    g["lat"] = pd.to_numeric(g["lat"], errors="coerce")
    g["lon"] = pd.to_numeric(g["lon"], errors="coerce")
    return g[["zip", "lat", "lon"]].dropna()


@functools.lru_cache(maxsize=1)
def _zip_cbsa() -> pd.DataFrame:
    z = pd.read_csv(DATA + "geo/zip_cbsa.csv", dtype=str)
    z["zip"] = z["zip"].str.zfill(5)
    return z.drop_duplicates("zip")[["zip", "cbsa_code", "cbsa_title"]]


@functools.lru_cache(maxsize=1)
def load_facilities() -> pd.DataFrame:
    """One row per facility, both settings, with the inputs needed to reprice."""
    # ---- inpatient hospitals ----
    r = pd.read_parquet(DATA + "recommendations.parquet")
    u = pd.read_csv(DATA + "hospital_universe.csv", dtype={"ccn": str})
    r["ccn"] = r["ccn"].astype(str).str.zfill(6)
    u["ccn"] = u["ccn"].astype(str).str.zfill(6)
    r = r[r["feasible"] == True]
    ucols = ["ccn", "lat", "lon", "cbsa_code", "cbsa_title", "hospital_type",
             "agency_premium_per_hour", "health_system"]
    # drop any universe-owned columns recs may already carry, to avoid merge-suffix collisions
    r = r.drop(columns=[c for c in ucols if c != "ccn" and c in r.columns], errors="ignore")
    m = r.merge(u[ucols], on="ccn", how="left")
    m = m[m["lat"].notna() & m["lon"].notna()]
    inp = pd.DataFrame({
        "ccn": m["ccn"], "name": m["name"], "city": m["city"], "state": m["state"],
        "lat": m["lat"].astype(float), "lon": m["lon"].astype(float),
        "cbsa_code": m["cbsa_code"], "cbsa_title": m["cbsa_title"].fillna("Non-metro"),
        "kind": "Inpatient", "ftype": m["hospital_type"].fillna("Hospital"),
        "fica_savings": pd.to_numeric(m["target_fica_savings_per_rn_per_month"], errors="coerce"),
        "florence_stored": pd.to_numeric(m["target_monthly_fee"], errors="coerce"),
        "effective_stored": pd.to_numeric(m["target_fica_adjusted_effective_cost"], errors="coerce"),
        "rn_need": pd.to_numeric(m["rn_need"], errors="coerce"),
        "agency_prem_hr": pd.to_numeric(m["agency_premium_per_hour"], errors="coerce"),
        "health_system": m["health_system"].fillna(""),
    })

    # ---- outpatient / non-hospital ----
    nf = pd.read_csv(DATA + "non_hospital_facilities.csv", dtype={"ccn": str, "zip": str})
    pr = pd.read_parquet(DATA + "non_hospital_priced.parquet")
    nf["ccn"] = nf["ccn"].astype(str)
    pr["ccn"] = pr["ccn"].astype(str)
    o = nf.merge(pr[["ccn", "monthly_fica_savings_per_rn", "florence_fee_per_rn_month",
                     "employer_net_cost_per_rn_month"]], on="ccn", how="inner")
    o["zip"] = o["zip"].astype(str).str.extract(r"(\d{5})")[0].str.zfill(5)
    o = o.merge(_zip_centroids(), on="zip", how="left").merge(_zip_cbsa(), on="zip", how="left")
    o = o[o["lat"].notna() & o["lon"].notna()]
    out = pd.DataFrame({
        "ccn": o["ccn"], "name": o["name"], "city": o["city"], "state": o["state"],
        "lat": o["lat"].astype(float), "lon": o["lon"].astype(float),
        "cbsa_code": o["cbsa_code"], "cbsa_title": o["cbsa_title"].fillna("Non-metro"),
        "kind": "Outpatient", "ftype": o["facility_type"],
        "fica_savings": pd.to_numeric(o["monthly_fica_savings_per_rn"], errors="coerce"),
        "florence_stored": pd.to_numeric(o["florence_fee_per_rn_month"], errors="coerce"),
        "effective_stored": pd.to_numeric(o["employer_net_cost_per_rn_month"], errors="coerce"),
        "rn_need": pd.to_numeric(o["rn_estimate"], errors="coerce").fillna(1.0).clip(lower=1.0),
        "agency_prem_hr": np.nan,
        "health_system": o["health_system"].fillna(""),
    })

    df = pd.concat([inp, out], ignore_index=True)
    df = df[df["fica_savings"].notna() & (df["fica_savings"] > 0)]
    # keep CONUS + AK/HI
    df = df[df["lat"].between(17, 72) & df["lon"].between(-180, -64)]
    return df.reset_index(drop=True)


def reprice(df: pd.DataFrame, offset_pct=0.40, markup_pct=0.20,
            floor=750.0, ceiling=2000.0) -> pd.DataFrame:
    """Recolor inputs. At the default calibration we show the engine's stored
    per-facility rates (consistent with the decks/MSA map); move the offset,
    floor or ceiling and we recompute uniformly from local FICA savings."""
    d = df.copy()
    at_default = (abs(offset_pct - 0.40) < 1e-9 and abs(floor - 750.0) < 1e-9
                  and abs(ceiling - 2000.0) < 1e-9 and "florence_stored" in d.columns)
    formula_fee = (d["fica_savings"] / max(float(offset_pct), 1e-6)).clip(lower=floor, upper=ceiling)
    if at_default:
        fee = d["florence_stored"].where(d["florence_stored"].notna(), formula_fee)
        eff = d["effective_stored"].where(d["effective_stored"].notna(), (fee - d["fica_savings"]).clip(lower=0))
    else:
        fee = formula_fee
        eff = (fee - d["fica_savings"]).clip(lower=0)
    d["florence"] = fee
    d["partner"] = fee * (1.0 + markup_pct)
    d["effective"] = eff.clip(lower=0)
    d["agency_monthly"] = d["agency_prem_hr"] * HOURS_MO
    d["spread_vs_agency"] = d["agency_monthly"] - fee
    return d


def msa_rollup(d: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a (re)priced facility frame to MSA centroids for the bubble view."""
    d = d[d["cbsa_code"].notna() & (d["cbsa_title"] != "Non-metro")]
    g = d.groupby("cbsa_code").agg(
        msa=("cbsa_title", "first"), lat=("lat", "mean"), lon=("lon", "mean"),
        florence=("florence", "median"), partner=("partner", "median"),
        effective=("effective", "median"), n_fac=("ccn", "count"),
        rn_need=("rn_need", "sum"), agency_prem=("agency_prem_hr", "median"),
    ).reset_index()
    return g.sort_values("rn_need", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    df = load_facilities()
    print("UNIFIED FACILITY TABLE")
    print("  total:", len(df))
    print("  by kind:", df["kind"].value_counts().to_dict())
    print("  by ftype:", df["ftype"].value_counts().to_dict())
    d = reprice(df, **DEFAULTS)
    print("\nREPRICE @ defaults (offset 40%, markup 20%, $750-$2000):")
    for k in ("Inpatient", "Outpatient"):
        s = d[d["kind"] == k]
        print(f"  {k:10} n={len(s):6}  florence med ${s.florence.median():,.0f}  "
              f"partner ${s.partner.median():,.0f}  effective ${s.effective.median():,.0f}")
    # sanity vs stored inpatient fee
    r = pd.read_parquet(DATA + "recommendations.parquet")
    r["ccn"] = r["ccn"].astype(str).str.zfill(6)
    chk = d[d["kind"] == "Inpatient"].merge(
        r[["ccn", "target_monthly_fee"]], on="ccn", how="left")
    err = (chk["florence"] - chk["target_monthly_fee"]).abs()
    print(f"\n  inpatient reprice vs stored target_monthly_fee: max abs err ${err.max():.2f}, "
          f"mean ${err.mean():.4f}  (should be ~0)")
    print("  MSAs in rollup:", len(msa_rollup(d)))
