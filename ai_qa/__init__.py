"""
Florence AI Q&A — natural-language interface to the workforce data.

Drops Claude / OpenAI in front of the data with the schema in the system
prompt. The LLM converts user questions → pandas operations + chart specs.

Architecture:
  router.py    — entry point, decides rule-based vs LLM
  schema.py    — generates schema documentation for the LLM system prompt
  llm_client.py — Anthropic SDK wrapper with graceful fallback
  responder.py — executes the LLM's plan against actual data

Falls back gracefully when ANTHROPIC_API_KEY is not set:
  - Uses the existing rule-based parser in app.py for common queries
  - Returns a clear "AI Q&A available when API key is configured" message

Set the API key via env:
    export ANTHROPIC_API_KEY="sk-..."

Or in your Streamlit secrets.toml:
    ANTHROPIC_API_KEY = "sk-..."
"""

import os

ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"


def has_api_key() -> bool:
    """Return True if Anthropic API key is configured in environment."""
    return bool(os.environ.get(ANTHROPIC_KEY_ENV))
