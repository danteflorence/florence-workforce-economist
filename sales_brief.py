"""
AI-powered sales-brief agent.

"I'm meeting with HCA tomorrow. Brief me." → 1-page intelligence pack.

Pulls together:
  - System overview (facility count, geography, size)
  - Pricing recommendations (target tier + Florence opportunity)
  - Recent news mentions (last 30 days)
  - Labor market signals (state-level wage/JOLTS)
  - Florence positioning (talking points + ROI math)

Uses Claude via ai_qa/ for narrative summarization when available.
Falls back to template-based briefing when no API key.

Output: dict ready for st.markdown or PDF rendering.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"


def _load_recs() -> pd.DataFrame:
    p = DATA_DIR / "recommendations.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def _load_news_mentions() -> pd.DataFrame:
    p = DATA_DIR / "surveillance" / "news_feeds" / "mentions.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df["date_fetched"] = pd.to_datetime(df["date_fetched"], errors="coerce")
    return df.dropna(subset=["date_fetched"])


def _load_briefing() -> dict:
    briefings = sorted((DATA_DIR / "surveillance" / "briefings").glob("*.json"))
    if not briefings:
        return {}
    return json.loads(briefings[-1].read_text())


def _system_news_mentions(system_name: str, days: int = 30) -> list[dict]:
    df = _load_news_mentions()
    if df.empty:
        return []
    cutoff = pd.Timestamp.today() - pd.Timedelta(days=days)
    recent = df[df["date_fetched"] >= cutoff]
    # systems_str is pipe-separated
    matched = recent[
        recent["systems_str"].astype(str).str.contains(system_name, case=False, na=False)
    ]
    return matched.head(10).to_dict(orient="records")


def build_brief(system_id: str) -> dict:
    """Build a comprehensive brief for the given health system."""
    recs = _load_recs()
    if recs.empty:
        return {"error": "No recommendations data."}

    # Filter to system
    sys_recs = recs[(recs["health_system_id"] == system_id) & (recs.get("feasible", True))]
    if sys_recs.empty:
        return {"error": f"No feasible recommendations for system_id={system_id}"}

    system_name = sys_recs.iloc[0]["health_system"]
    n_facilities = len(sys_recs)
    states = sorted(sys_recs["state"].unique())
    rn_need = float(sys_recs.get("rn_need", pd.Series([0])).sum())

    # Pricing math (Target tier)
    term_fee = float(sys_recs["target_term_florence_fee_account"].sum())
    term_savings = float(sys_recs["target_term_net_savings_account"].sum())
    annual_savings = term_savings / 2
    monthly_fee_median = float(sys_recs["target_monthly_fee"].median())
    median_target_pct = float(sys_recs["target_target_offset_pct"].median())
    savings_ratio = term_savings / max(term_fee, 1)

    # Top 3 facilities
    top_facilities = sys_recs.sort_values(
        "target_term_net_savings_account", ascending=False
    ).head(3)[["name", "city", "state", "target_term_florence_fee_account",
               "target_term_net_savings_account"]].to_dict(orient="records")

    # News in last 30 days
    news = _system_news_mentions(system_name, days=30)

    # Market context
    briefing = _load_briefing()
    market_headline = briefing.get("headline", "")
    forecast = briefing.get("forecast_narrative", "")

    # State concentration
    state_counts = sys_recs["state"].value_counts().head(5)

    return {
        "system_id": system_id,
        "system_name": system_name,
        "as_of": date.today().isoformat(),
        "overview": {
            "n_facilities": n_facilities,
            "n_states": len(states),
            "top_states": state_counts.to_dict(),
            "rn_need_fte": rn_need,
        },
        "pricing": {
            "median_target_monthly_fee": monthly_fee_median,
            "median_target_offset_pct": median_target_pct,
            "term_florence_fee": term_fee,
            "term_hospital_savings": term_savings,
            "annual_hospital_savings": annual_savings,
            "savings_ratio": savings_ratio,
        },
        "top_facilities": top_facilities,
        "news_last_30d": news,
        "market_context": {
            "headline": market_headline,
            "forecast": forecast,
        },
        "talking_points": _generate_talking_points(
            system_name, n_facilities, term_savings, term_fee, savings_ratio,
            news, market_headline,
        ),
    }


def _generate_talking_points(
    system_name: str, n_facilities: int, term_savings: float, term_fee: float,
    savings_ratio: float, news: list[dict], market_headline: str,
) -> list[str]:
    """Build templated talking points (LLM enhancement happens elsewhere)."""
    points = []
    savings_str = f"${term_savings/1e9:.2f}B" if term_savings >= 1e9 else f"${term_savings/1e6:,.0f}M"
    fee_str = f"${term_fee/1e9:.2f}B" if term_fee >= 1e9 else f"${term_fee/1e6:,.0f}M"
    points.append(
        f"**The economic ask.** Florence delivers {n_facilities} permanent RN streams "
        f"to {system_name}. Over 24 months, your business saves {savings_str} on a "
        f"{fee_str} Florence investment — every $1 with Florence returns ${savings_ratio:.1f} in net savings."
    )
    points.append(
        f"**The market context.** {market_headline} This is the market environment "
        f"the {system_name} CFO is reading every morning. Lead with it."
    )
    if news:
        recent = news[0]
        title = str(recent.get("title", ""))[:120]
        points.append(
            f"**Recent news angle.** {system_name} was mentioned in industry "
            f"coverage this past 30 days: \"{title}\" — reference it to show you've done your homework."
        )
    points.append(
        "**The structural pitch.** Permanent — not contingent. International RNs trained "
        "through Florence's full production pipeline become full-time employees of "
        f"{system_name} on multi-year contracts. Standard hiring. Standard benefits."
    )
    points.append(
        f"**Risk reversal.** Florence fees are payable on successful employment start. "
        f"Replacement protection for early attrition is built into the program."
    )
    return points


def enhance_with_llm(brief: dict, system_name: str) -> dict:
    """Optional: use Claude to add a sharper narrative + custom angle."""
    try:
        from ai_qa.llm_client import is_available, ask_claude
        if not is_available():
            return brief
        prompt = (
            f"You are Florence's strategic sales advisor. Given the data below about "
            f"{system_name}, write a 3-sentence opening for a sales rep walking into a "
            f"meeting tomorrow. Make it specific, market-aware, and confident — no fluff.\n\n"
            f"Data: {json.dumps({k: v for k, v in brief.items() if k in ('overview', 'pricing', 'market_context')}, default=str)[:2000]}"
        )
        response = ask_claude(prompt)
        if response and isinstance(response, dict):
            opening = response.get("narrative") or response.get("data") or ""
            if opening:
                brief["ai_opening"] = opening
    except Exception:
        pass
    return brief


if __name__ == "__main__":
    brief = build_brief("hca")
    if "error" not in brief:
        print(f"=== Brief for {brief['system_name']} ===")
        print(f"\nOverview: {brief['overview']['n_facilities']} facilities in "
              f"{brief['overview']['n_states']} states · "
              f"{brief['overview']['rn_need_fte']:.0f} RN need")
        print(f"\nPricing: ${brief['pricing']['median_target_monthly_fee']:.0f}/mo median fee · "
              f"{brief['pricing']['savings_ratio']:.1f}× savings:fee")
        print(f"\nTalking points:")
        for tp in brief["talking_points"]:
            print(f"  • {tp[:200]}")
        if brief["news_last_30d"]:
            print(f"\nRecent news ({len(brief['news_last_30d'])} items)")
            for n in brief["news_last_30d"][:3]:
                print(f"  - {n.get('title','')[:80]}")
    else:
        print(brief["error"])
