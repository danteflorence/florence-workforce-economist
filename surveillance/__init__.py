"""
Florence Workforce Surveillance — continuous monitoring of U.S. RN labor market.

Modules:
  bls_fetch        — Generic BLS Public Data API client
  jolts_healthcare — Monthly job openings/hires/separations for healthcare sector
  ces_rn          — Monthly RN employment by state/MSA
  oews_refresh    — Annual May OEWS wage refresh
  cms_care_compare — Quarterly CMS Care Compare star + staffing changes
  news_feeds      — RSS scrape of AHA News, Becker's, etc.
  briefing        — Weekly "what changed" summarizer

Each module pulls fresh data and writes to data/surveillance/<feed>/YYYY-MM-DD.{csv,json}
Snapshots are kept indefinitely so we can compute deltas.

Usage (manual):
    python -m surveillance.jolts_healthcare
    python -m surveillance.ces_rn

Or via cron (recommended monthly on the 5th):
    5 0 5 * * cd /path/to/florence && python -m surveillance.briefing
"""

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "surveillance"
DATA_DIR.mkdir(parents=True, exist_ok=True)
