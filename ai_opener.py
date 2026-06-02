"""
AI-personalized outreach opener — DORMANT on ANTHROPIC_API_KEY.

Generates a 1–2 sentence opening line tailored to a system's real facts. With
ANTHROPIC_API_KEY set it asks Claude (cheap Haiku); otherwise — and on ANY error,
or if the model slips a prohibited term — it falls back to a deterministic
local-data opener. Never raises, never blocks the app, never emits
FICA/visa/tax/immigration language.
"""
from __future__ import annotations

import os
import re

_BANNED = re.compile(r"\b(fica|irs|visa|visas|tax|taxes|immigration|f-1|green card)\b", re.I)


def is_configured() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def _money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return f"${v:,.0f}"


def _rule_based(facts: dict) -> str:
    name = facts.get("system_name", "this system")
    n = int(facts.get("n_facilities") or 0)
    rn = int(facts.get("rn_need") or 0)
    state = str(facts.get("state") or "").strip()
    hero = _money(facts.get("annual_savings"))
    if n >= 2 and rn:
        where = f" across {state}" if state else ""
        return (f"{name} runs {n:,} facilities{where} on an estimated {rn:,}-RN footprint — at that "
                f"scale the agency premium compounds, and we peg the recoverable RN labor cost near "
                f"{hero} a year.")
    if rn:
        return (f"With an estimated {rn:,}-RN footprint, {name} is carrying roughly {hero} a year in "
                f"avoidable agency premium that permanent hires would recover.")
    return f"We estimate {name} is leaving about {hero} a year on the table in avoidable RN agency premium."


_PROMPT = (
    "Write one or two sentences (max ~45 words) to OPEN a B2B sales email to a U.S. hospital / "
    "health-system executive, from Florence — which places permanent, U.S.-licensed registered nurses "
    "(direct hire) to replace agency and travel premium. Use the specific facts. Be concrete and "
    "professional; no hype, no greeting, no sign-off, no em-dash salesy clichés. STRICT: never mention "
    "taxes, FICA, visas, immigration, or nurse nationality/origin. Facts:\n{facts}\n\nOpening line:"
)


def generate(facts: dict, use_ai: bool | None = None) -> dict:
    """Return {'opener': str, 'source': 'ai'|'rule'}. Always safe."""
    want_ai = is_configured() if use_ai is None else (bool(use_ai) and is_configured())
    if want_ai:
        try:
            import anthropic
            client = anthropic.Anthropic()
            fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items()
                                   if v not in (None, "", 0))
            msg = client.messages.create(
                model=os.environ.get("FLORENCE_AI_MODEL", "claude-3-5-haiku-latest"),
                max_tokens=140,
                messages=[{"role": "user", "content": _PROMPT.format(facts=fact_lines)}],
            )
            text = "".join(getattr(b, "text", "") for b in msg.content
                           if getattr(b, "type", "") == "text").strip()
            if text and not _BANNED.search(text):
                return {"opener": text, "source": "ai"}
        except Exception:
            pass
    return {"opener": _rule_based(facts), "source": "rule"}
