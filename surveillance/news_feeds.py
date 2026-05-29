"""
Healthcare news RSS surveillance — AHA News, Becker's, Modern Healthcare.

For each curated source, pull the RSS feed daily and:
  - Store new headlines
  - Match against known health system names
  - Surface "Tenet announced layoffs" / "HCA opens new SNF division" / etc.

Output goes to data/surveillance/news_feeds/feed_name/YYYY-MM-DD.json
and aggregates into a `mentions.csv` for the briefing.

Run daily via cron.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from . import DATA_DIR

FEEDS = {
    "ahanews": {
        "url": "https://www.aha.org/news/news.rss",
        "title": "American Hospital Association News",
    },
    "beckers_hospital": {
        "url": "https://www.beckershospitalreview.com/feed/",
        "title": "Becker's Hospital Review",
    },
    "modern_healthcare": {
        "url": "https://www.modernhealthcare.com/news/feed",
        "title": "Modern Healthcare",
    },
    "fierce_healthcare": {
        "url": "https://www.fiercehealthcare.com/rss.xml",
        "title": "Fierce Healthcare",
    },
}

# Health systems we care about — match these substrings against headlines
WATCHLIST_SYSTEMS = {
    "HCA": ["hca healthcare", "hca ", "hca holdings"],
    "Tenet": ["tenet healthcare", "tenet "],
    "Community Health Systems": ["community health systems"],
    "Ascension": ["ascension health", "ascension "],
    "CommonSpirit": ["commonspirit"],
    "Trinity Health": ["trinity health"],
    "Kaiser Permanente": ["kaiser permanente", "kaiser foundation"],
    "Providence": ["providence health", "providence saint", "providence st"],
    "Sutter Health": ["sutter health"],
    "AdventHealth": ["adventhealth"],
    "Cleveland Clinic": ["cleveland clinic"],
    "Mayo Clinic": ["mayo clinic"],
    "Mass General Brigham": ["mass general brigham", "massachusetts general"],
    "Northwell Health": ["northwell"],
    "Banner Health": ["banner health"],
    "UPMC": ["upmc"],
    "Intermountain": ["intermountain"],
    "Lifepoint Health": ["lifepoint"],
    "Universal Health Services": ["universal health services"],
    "DaVita": ["davita"],
    "Fresenius": ["fresenius"],
    "Encompass Health": ["encompass health"],
    "Amedisys": ["amedisys"],
    "Genesis Healthcare": ["genesis healthcare"],
    "Ensign Group": ["ensign group"],
}

# Topics that matter most for Florence
RELEVANT_KEYWORDS = [
    "layoff", "layoffs", "workforce", "labor", "nurse", "rn ",
    "strike", "union", "contract negotiation",
    "merger", "acquisition", "sold", "divest",
    "closure", "closing", "shutdown",
    "earnings", "revenue", "loss", "margin",
    "staffing", "agency", "agency labor", "contract labor",
    "ceo", "leadership", "appointed",
    "outsource", "outsourcing",
]


def _parse_rss(feed_url: str, feed_name: str) -> list[dict]:
    """Lightweight RSS parser using stdlib ElementTree."""
    try:
        r = requests.get(
            feed_url,
            timeout=30,
            headers={"User-Agent": "Florence-Workforce-Surveillance/1.0"},
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  {feed_name}: fetch error {e}")
        return []

    items: list[dict] = []
    try:
        # Try RSS first
        root = ET.fromstring(r.content)
        # RSS 2.0 channel/item
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            items.append({
                "title": title, "link": link, "pubDate": pub,
                "description": desc[:500],
            })
        if not items:
            # Atom <entry>
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = entry.findtext("atom:title", default="", namespaces=ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.attrib.get("href", "") if link_el is not None else ""
                pub = entry.findtext("atom:published", default="", namespaces=ns).strip()
                items.append({"title": title, "link": link, "pubDate": pub, "description": ""})
    except ET.ParseError as e:
        print(f"  {feed_name}: parse error {e}")
        return []
    return items


def _match_systems_and_keywords(text: str) -> tuple[list[str], list[str]]:
    text_l = text.lower()
    matched_systems = []
    for system, patterns in WATCHLIST_SYSTEMS.items():
        if any(p in text_l for p in patterns):
            matched_systems.append(system)
    matched_keywords = [kw for kw in RELEVANT_KEYWORDS if kw in text_l]
    return matched_systems, matched_keywords


def fetch_all() -> list[dict]:
    """Pull every feed, annotate items with system + keyword matches.
    Returns aggregated mention list."""
    feed_dir = DATA_DIR / "news_feeds"
    feed_dir.mkdir(parents=True, exist_ok=True)
    all_mentions = []
    today = date.today()
    for name, info in FEEDS.items():
        print(f"[{name}]")
        items = _parse_rss(info["url"], name)
        print(f"  Fetched {len(items)} items")
        annotated = []
        for it in items:
            text = it["title"] + " " + it.get("description", "")
            sys, kws = _match_systems_and_keywords(text)
            it["matched_systems"] = sys
            it["matched_keywords"] = kws
            it["relevant"] = bool(sys or kws)
            annotated.append(it)
            if it["relevant"]:
                all_mentions.append({
                    "source": name,
                    "date_fetched": today.isoformat(),
                    "title": it["title"],
                    "link": it["link"],
                    "pubDate": it["pubDate"],
                    "systems": sys,
                    "keywords": kws,
                })
        # Persist daily snapshot
        snap = feed_dir / name / f"{today.isoformat()}.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps(annotated, indent=2, default=str))
        rel = sum(1 for it in annotated if it["relevant"])
        print(f"  {rel} relevant items saved")
    # Aggregate mentions CSV
    if all_mentions:
        mentions_df = pd.DataFrame(all_mentions)
        mentions_df["systems_str"] = mentions_df["systems"].apply(lambda s: "|".join(s))
        mentions_df["keywords_str"] = mentions_df["keywords"].apply(lambda k: "|".join(k))
        path = feed_dir / "mentions.csv"
        existing = pd.read_csv(path) if path.exists() else pd.DataFrame()
        combined = pd.concat([existing, mentions_df]).drop_duplicates(subset=["title", "link"])
        combined.to_csv(path, index=False)
        print(f"\n✓ Mentions log: {path} ({len(combined):,} rows total)")
    return all_mentions


def main():
    mentions = fetch_all()
    if not mentions:
        print("No relevant headlines today.")
        return
    print(f"\n=== {len(mentions)} relevant headlines today ===")
    for m in mentions[:20]:
        sys_str = " · ".join(m["systems"]) or "(no system match)"
        kw_str = ", ".join(m["keywords"][:3])
        print(f"  [{m['source']}] {sys_str}")
        print(f"     {m['title']}")
        print(f"     keywords: {kw_str}")
        print()


if __name__ == "__main__":
    main()
