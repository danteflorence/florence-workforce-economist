"""
Predictive lead scoring — find systems most likely to close.

Approach:
  1. Build a feature vector per system from aggregated facility data:
     - Size (facility count, RN need)
     - Geography concentration (Census region distribution)
     - Cost structure (median agency rate, contract-labor intensity)
     - Pricing signals (Florence savings ratio, deal score)
     - News heat (recent mentions, layoff signals)
  2. Compute pairwise similarity between systems (cosine)
  3. Surface "10 systems most like [target]" for lookalike pipelining
  4. Score each system on Florence-fit composite metric

No LLM required — pure numerical features + sklearn-style cosine similarity.

For a more advanced version, swap the feature vector for Claude embeddings
on each system's news-mention narrative.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"


# ─── Census region map ──────────────────────────────────────────────
CENSUS_REGION = {
    # Northeast
    "CT": "NE", "ME": "NE", "MA": "NE", "NH": "NE",
    "NJ": "NE", "NY": "NE", "PA": "NE", "RI": "NE", "VT": "NE",
    # Midwest
    "IL": "MW", "IN": "MW", "IA": "MW", "KS": "MW", "MI": "MW",
    "MN": "MW", "MO": "MW", "NE": "MW", "ND": "MW", "OH": "MW",
    "SD": "MW", "WI": "MW",
    # South
    "AL": "S", "AR": "S", "DE": "S", "DC": "S", "FL": "S",
    "GA": "S", "KY": "S", "LA": "S", "MD": "S", "MS": "S",
    "NC": "S", "OK": "S", "SC": "S", "TN": "S", "TX": "S",
    "VA": "S", "WV": "S",
    # West
    "AK": "W", "AZ": "W", "CA": "W", "CO": "W", "HI": "W",
    "ID": "W", "MT": "W", "NV": "W", "NM": "W", "OR": "W",
    "UT": "W", "WA": "W", "WY": "W",
}


def build_system_features() -> pd.DataFrame:
    """Build a feature matrix where each row is a health system."""
    recs_path = DATA_DIR / "recommendations.parquet"
    if not recs_path.exists():
        raise FileNotFoundError("recommendations.parquet missing — run batch_recommend first")
    recs = pd.read_parquet(recs_path)
    recs = recs[recs["feasible"]].copy()
    recs["region"] = recs["state"].map(CENSUS_REGION).fillna("Other")

    # Per-system aggregations
    base = (
        recs.groupby(["health_system_id", "health_system"])
        .agg(
            n_facilities=("ccn", "count"),
            rn_need=("rn_need", "sum"),
            term_florence_fee=("target_term_florence_fee_account", "sum"),
            term_savings=("target_term_net_savings_account", "sum"),
            median_agency_premium=("signal_agency_premium", "median"),
            median_cl_intensity=("signal_cl_intensity", "median"),
            median_deal_score=("target_deal_score", "median"),
            median_savings_ratio=("target_savings_ratio", "median"),
            mean_data_confidence=("signal_data_confidence", "mean"),
        )
        .reset_index()
    )

    # Regional distribution (% of facilities in each region)
    region_pct = (
        recs.groupby(["health_system_id", "region"]).size()
        .unstack(fill_value=0)
        .div(recs.groupby("health_system_id").size(), axis=0)
        .add_prefix("pct_")
        .reset_index()
    )
    base = base.merge(region_pct, on="health_system_id", how="left")
    base = base.fillna(0)

    # Derived: log-scale size, savings:fee ratio (already there as median_savings_ratio)
    base["log_n_facilities"] = np.log1p(base["n_facilities"])
    base["log_rn_need"] = np.log1p(base["rn_need"])
    base["fee_to_facility_ratio"] = base["term_florence_fee"] / base["n_facilities"].clip(lower=1)
    base["log_fee_to_facility"] = np.log1p(base["fee_to_facility_ratio"])

    return base


def feature_columns() -> list[str]:
    """The columns used in cosine similarity (numeric features only)."""
    return [
        "log_n_facilities",
        "log_rn_need",
        "log_fee_to_facility",
        "median_agency_premium",
        "median_cl_intensity",
        "median_deal_score",
        "median_savings_ratio",
        "mean_data_confidence",
        "pct_NE", "pct_MW", "pct_S", "pct_W",
    ]


def standardize(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Z-score standardize the numeric columns (handles missing cols)."""
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = 0
        vals = pd.to_numeric(out[c], errors="coerce").fillna(0)
        std = vals.std()
        out[c] = (vals - vals.mean()) / (std if std > 0 else 1)
    return out


def cosine_similarity_matrix(X: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity for rows of X."""
    norm = np.linalg.norm(X, axis=1, keepdims=True)
    norm[norm == 0] = 1
    Xn = X / norm
    return Xn @ Xn.T


def lookalikes(target_system_id: str, top_k: int = 10) -> pd.DataFrame:
    """Return the top-K most-similar systems to `target_system_id`."""
    df = build_system_features()
    cols = feature_columns()
    standardized = standardize(df, cols)
    X = standardized[cols].to_numpy(dtype=float)

    if target_system_id not in df["health_system_id"].values:
        return pd.DataFrame()

    target_idx = df.index[df["health_system_id"] == target_system_id][0]
    sims = cosine_similarity_matrix(X)
    sim_to_target = sims[target_idx]
    df["similarity"] = sim_to_target
    df = df[df["health_system_id"] != target_system_id]
    df = df.sort_values("similarity", ascending=False).head(top_k)
    return df[[
        "health_system_id", "health_system", "n_facilities", "rn_need",
        "term_florence_fee", "median_deal_score", "similarity",
    ]]


def florence_fit_score(df: pd.DataFrame) -> pd.DataFrame:
    """Compute a 0-100 Florence-fit composite score per system."""
    out = df.copy()
    # Component scores (each 0-100 via percentile rank)
    out["s_size"] = out["n_facilities"].rank(pct=True) * 100
    out["s_agency_premium"] = out["median_agency_premium"].rank(pct=True) * 100
    out["s_cl_intensity"] = out["median_cl_intensity"].rank(pct=True) * 100
    out["s_deal_score"] = out["median_deal_score"].rank(pct=True) * 100
    out["s_data_confidence"] = out["mean_data_confidence"].rank(pct=True) * 100
    # Weighted composite
    out["florence_fit_score"] = (
        0.25 * out["s_size"] +
        0.20 * out["s_agency_premium"] +
        0.15 * out["s_cl_intensity"] +
        0.30 * out["s_deal_score"] +
        0.10 * out["s_data_confidence"]
    )
    return out.sort_values("florence_fit_score", ascending=False)


def top_fit(n: int = 20) -> pd.DataFrame:
    """Top-N systems by Florence-fit composite score."""
    df = build_system_features()
    scored = florence_fit_score(df)
    return scored.head(n)[[
        "health_system", "n_facilities", "rn_need",
        "term_florence_fee", "median_deal_score", "florence_fit_score",
    ]]


if __name__ == "__main__":
    print("=== Top 15 systems by Florence-fit score ===\n")
    print(top_fit(15).to_string(index=False))
    print("\n=== Top 10 systems most-similar to Kaiser Permanente ===\n")
    print(lookalikes("kaiser_permanente", 10).to_string(index=False))
