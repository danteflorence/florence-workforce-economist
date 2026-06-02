"""
Funnel analytics — outreach → engaged → activated → hired, overall + by rep.

Read-only over the stores the engine already writes:
  data/mail_log.csv        (lob_mailer)        — drafted / sent / responded
  data/activations.csv     (florence_activate) — retrieval code → sign-up
  data/sales_pipeline.csv  (workbench)         — deals; stage closed_won = hired

No writes; defensive on every missing/empty file so the view renders cleanly
before any activity exists.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
MAIL = DATA_DIR / "mail_log.csv"
ACTS = DATA_DIR / "activations.csv"
PIPE = DATA_DIR / "sales_pipeline.csv"


def _read(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _ndistinct(df: pd.DataFrame, col: str) -> int:
    if df.empty or col not in df.columns:
        return 0
    s = df[col].astype(str).str.strip()
    return int(s[s != ""].nunique())


def funnel_counts() -> dict:
    """Distinct accounts at each funnel stage (top → bottom)."""
    mail, acts, pipe = _read(MAIL), _read(ACTS), _read(PIPE)
    sent = mail[mail["status"].isin(["sent", "responded"])] if ("status" in mail.columns) else mail.iloc[0:0]
    resp = mail[mail["status"] == "responded"] if ("status" in mail.columns) else mail.iloc[0:0]
    won = pipe[pipe["stage"] == "closed_won"] if ("stage" in pipe.columns) else pipe.iloc[0:0]
    return {
        "Outreach drafted": _ndistinct(mail, "entity_id"),
        "Sent": _ndistinct(sent, "entity_id"),
        "Responded": _ndistinct(resp, "entity_id"),
        "Activated": _ndistinct(acts, "code"),
        "Hired (won)": _ndistinct(won, "system_id"),
    }


def open_deals() -> int:
    """Distinct systems with an open (non-closed) deal."""
    pipe = _read(PIPE)
    if pipe.empty or "stage" not in pipe.columns:
        return 0
    op = pipe[~pipe["stage"].isin(["closed_won", "closed_lost"])]
    return _ndistinct(op, "system_id")


def by_rep() -> pd.DataFrame:
    """Per-rep: outreach accounts, responses, open+all deals, hires."""
    mail, pipe = _read(MAIL), _read(PIPE)
    recs: dict[str, dict] = {}

    def _row(rep):
        return recs.setdefault(rep or "unassigned",
                               {"rep": rep or "unassigned", "outreach": 0,
                                "responses": 0, "deals": 0, "won": 0})

    if not mail.empty and "by" in mail.columns:
        for rep, g in mail.groupby(mail["by"].replace("", "unassigned")):
            r = _row(rep)
            r["outreach"] = _ndistinct(g, "entity_id")
            r["responses"] = _ndistinct(g[g.get("status") == "responded"], "entity_id")
    if not pipe.empty and "rep_email" in pipe.columns:
        for rep, g in pipe.groupby(pipe["rep_email"].replace("", "unassigned")):
            r = _row(rep)
            r["deals"] = _ndistinct(g, "system_id")
            r["won"] = _ndistinct(g[g.get("stage") == "closed_won"], "system_id")

    df = pd.DataFrame(list(recs.values()))
    if df.empty:
        return df
    return df.sort_values(["won", "outreach"], ascending=False).reset_index(drop=True)
