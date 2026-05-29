"""
Execute the LLM's plan against actual data.

Takes a plan dict (from Claude or rule-based parser) and executes it,
returning the result (DataFrame, dict, or narrative text).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"

# Whitelist of safe datasets — never let arbitrary file paths through
DATASET_PATHS = {
    "hospital_universe.csv": DATA_DIR / "hospital_universe.csv",
    "recommendations.parquet": DATA_DIR / "recommendations.parquet",
    "non_hospital_facilities.csv": DATA_DIR / "non_hospital_facilities.csv",
    "non_hospital_priced.parquet": DATA_DIR / "non_hospital_priced.parquet",
    "state_benchmarks.csv": DATA_DIR / "state_benchmarks.csv",
    "surveillance.jolts_healthcare": DATA_DIR / "surveillance" / "jolts_healthcare" / "long_history.csv",
    "surveillance.ces_rn": DATA_DIR / "surveillance" / "ces_rn" / "long_history.csv",
}


def _load(dataset_name: str) -> pd.DataFrame:
    path = DATASET_PATHS.get(dataset_name)
    if path is None or not path.exists():
        raise ValueError(f"Dataset not found: {dataset_name}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype={"ccn": str} if "ccn" in str(path) else None)


def execute(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute a plan and return result + metadata.

    Result format:
      {"kind": "table|chart|text", "data": <pd.DataFrame|str>, "narrative": str,
       "chart_type": "table|bar|choropleth|timeseries"}
    """
    if "narrative" in plan and "dataset" not in plan:
        return {"kind": "text", "data": plan["narrative"], "narrative": "", "chart_type": "text"}
    if "error" in plan:
        return {"kind": "text", "data": plan["error"], "narrative": "", "chart_type": "text"}

    dataset = plan.get("dataset")
    if not dataset:
        return {"kind": "text", "data": "No dataset specified in plan.",
                "narrative": "", "chart_type": "text"}

    try:
        df = _load(dataset)
    except Exception as e:
        return {"kind": "text", "data": str(e), "narrative": "", "chart_type": "text"}

    # Apply filters
    for col, val in (plan.get("filters") or {}).items():
        if col not in df.columns:
            continue
        if isinstance(val, list):
            df = df[df[col].isin(val)]
        elif isinstance(val, bool):
            df = df[df[col] == val]
        elif isinstance(val, str):
            df = df[df[col].astype(str).str.lower() == val.lower()]
        else:
            df = df[df[col] == val]

    # Aggregate
    if plan.get("intent") == "aggregate" and plan.get("group_by"):
        metrics = plan.get("metrics") or []
        df = df.groupby(plan["group_by"])[metrics].sum().reset_index()

    # Sort
    sort_by = plan.get("sort_by")
    if sort_by and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False)

    # Limit
    limit = plan.get("limit") or 50
    df = df.head(limit)

    # Select displayed metrics
    metrics = plan.get("metrics")
    if metrics:
        keep_cols = [c for c in metrics if c in df.columns]
        # Always include identifier columns if present
        for id_col in ["ccn", "name", "state", "city", "health_system"]:
            if id_col in df.columns and id_col not in keep_cols:
                keep_cols.insert(0, id_col)
        if keep_cols:
            df = df[keep_cols]

    return {
        "kind": "table" if plan.get("chart_type", "table") == "table" else "chart",
        "data": df,
        "narrative": plan.get("narrative", ""),
        "chart_type": plan.get("chart_type", "table"),
    }
