"""
AI Q&A entry point.

Routes a user query to:
  1. The LLM (if ANTHROPIC_API_KEY is set + anthropic SDK installed)
  2. Otherwise: returns a clear "AI Q&A available when configured" message
     and lets the caller fall back to rule-based parsing.

Single entry point: ask(query)
"""
from __future__ import annotations

from typing import Any

from . import has_api_key
from .llm_client import ask_claude, is_available
from .responder import execute


def ask(query: str, *, extra_context: str = "") -> dict[str, Any]:
    """Process a user question and return a result.

    Returns: {"kind": "table|chart|text", "data": ..., "narrative": str,
              "source": "llm" | "fallback", "available": bool}
    """
    if not query.strip():
        return {
            "kind": "text",
            "data": "Please type a question.",
            "narrative": "",
            "source": "fallback",
            "available": is_available(),
        }

    if not is_available():
        return {
            "kind": "text",
            "data": (
                "AI Q&A is not configured. Set ANTHROPIC_API_KEY in your environment "
                "and install the anthropic SDK (`pip install anthropic`) to enable "
                "natural-language queries against the full data layer. "
                "Meanwhile, use the rule-based query box in Market Intelligence — "
                "it handles 'top 10 states by wage', 'compare CA TX FL', "
                "single-state lookups, and 'headline'."
            ),
            "narrative": "",
            "source": "fallback",
            "available": False,
        }

    plan = ask_claude(query, extra_context=extra_context)
    if plan is None:
        return {
            "kind": "text",
            "data": "No response from LLM.",
            "narrative": "",
            "source": "llm",
            "available": True,
        }
    result = execute(plan)
    result["source"] = "llm"
    result["available"] = True
    return result
