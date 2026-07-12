"""
Freshness guard: CI goes red when a pricing data source ages past its hard
limit, so staleness is loud instead of silent. Soft limits only surface as
amber in-app (provenance.freshness_badge) — this test enforces the hard ones.

When this fails: ingest the new vintage (see docs / surveillance modules),
then update provenance.SOURCES — that single edit updates every buyer-facing
"as of" line and resets the clock.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_no_source_past_hard_limit():
    import provenance
    stale = [f for f in provenance.freshness() if f["status"] == "stale"]
    assert not stale, (
        "Pricing data past its hard freshness limit: "
        + "; ".join(f"{f['source']} ({f['vintage']}) is {f['age_months']} months old "
                    f"(limit {f['hard_limit']})" for f in stale)
        + ". Ingest the new vintage and update provenance.SOURCES."
    )


def test_as_of_line_renders():
    import provenance
    line = provenance.as_of_line()
    assert "BLS OEWS" in line and "HCRIS" in line and "universe refreshed" in line
