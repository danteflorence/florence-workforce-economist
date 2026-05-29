"""
Anthropic Claude SDK wrapper for AI Q&A.

Gracefully degrades when ANTHROPIC_API_KEY is not set:
  - Returns None or a clear error message
  - Caller (router.py) falls back to rule-based parsing

Usage:
    from ai_qa.llm_client import ask_claude
    response = ask_claude("How many California SNFs are owned by Ensign?")
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import ANTHROPIC_KEY_ENV, has_api_key
from .schema import build_system_prompt

MODEL = "claude-sonnet-4-5"  # latest production model as of build time


def ask_claude(user_query: str, *, extra_context: str = "") -> dict[str, Any] | None:
    """Send the query to Claude with the workforce schema in the system prompt.

    Returns:
        - dict with parsed JSON plan if the query is data-bound
        - {"narrative": str} for conversational responses
        - None if no API key configured

    Never raises — wraps everything in try/except for graceful UI integration.
    """
    if not has_api_key():
        return None
    try:
        import anthropic
    except ImportError:
        # SDK not installed
        return {"error": "anthropic SDK not installed. Run: pip install anthropic"}

    try:
        client = anthropic.Anthropic(api_key=os.environ[ANTHROPIC_KEY_ENV])
        system_prompt = build_system_prompt(extra_context)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_query}],
        )
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()
        # Try to parse as JSON; if it's narrative, return as-is
        if text.startswith("NARRATIVE:"):
            return {"narrative": text[len("NARRATIVE:"):].strip()}
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"narrative": text}
        return {"narrative": text}
    except Exception as e:
        return {"error": f"LLM call failed: {e}"}


def is_available() -> bool:
    """Quick check: is the AI Q&A layer ready to use?"""
    if not has_api_key():
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False
