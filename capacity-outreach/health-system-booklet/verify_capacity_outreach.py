"""
verify_capacity_outreach.py
===========================
Offline dry-run verification for the Health-System Capacity Booklet. NO network,
NO Lob key, NO mail. Proves the contract that the feedback flagged:

  1. all modules import
  2. the Lob merge-variable mapping == the audience CSV columns (the bug)
  3. systems_from_universe yields real, priced systems with all required fields
  4. campaign_links builds per-system tracked URLs with UTM + ids and NO PII
  5. a built audience CSV carries the economics + tracked links
  6. mailpiece copy carries no FICA / visa / tax / immigration / "eligible offsets"

Run:  python3 verify_capacity_outreach.py
"""
from __future__ import annotations

import csv
import os
import tempfile

P = F = 0
def ok(label, cond, extra=""):
    global P, F
    print(f"{'✓' if cond else '✗'} {label}" + (f" — {extra}" if extra else ""))
    P += 1 if cond else 0
    F += 0 if cond else 1

HERE = os.path.dirname(os.path.abspath(__file__))

# 1. Imports
import campaign_links
import hospital_audience
import lob_booklet
import hospital_universe_audience as hua
ok("imports: all capacity-outreach modules import", True)

# 2. The Lob mapping == audience merge columns (the exact bug the feedback flagged)
merge_map = lob_booklet.upload_payload("cmp_test")["mergeVariableColumnMapping"]
ok("contract: Lob mergeVariableColumnMapping keys == audience MERGE_COLS",
   sorted(merge_map.keys()) == sorted(hospital_audience.MERGE_COLS),
   f"lob={sorted(merge_map)} audience={sorted(hospital_audience.MERGE_COLS)}")
ok("contract: Lob no longer maps the stale university vars",
   "university" not in merge_map and "logo_url" not in merge_map)
ok("contract: company prints the health system (not 'university')",
   lob_booklet.upload_payload("c")["optionalAddressColumnMapping"].get("company") == "system_name")

# 3. Real universe → priced systems
systems = hua.systems_from_universe(limit=15)
ok("universe: ≥10 real priced systems from hospital_universe.csv", len(systems) >= 10, f"{len(systems)} systems")
required = {"name", "nFacilities", "totalRnNeed", "medianFee", "effectiveLow"}
ok("universe: every system has the required booklet fields", all(required <= set(s) for s in systems))
ok("universe: pricing is positive (engine-derived, never invented)",
   all(s["medianFee"] > 0 and s["effectiveLow"] > 0 for s in systems))
ok("universe: catch-all 'Independent/Unknown' bucket excluded",
   not any("independent" in s["name"].lower() or "unknown" in s["name"].lower() for s in systems))

# 4. Tracked links — UTM + ids, no PII
url = campaign_links.build_capacity_url(account_slug="HCA Healthcare", segment="health_system",
                                        campaign_id="cmp_123", account_id="acct_hca",
                                        campaign="health_system_capacity_q3", content="hca_teal_8pp")
ok("links: per-system URL has utm_source/medium/campaign/content", all(k in url for k in
   ["utm_source=direct_mail", "utm_medium=booklet", "utm_campaign=health_system_capacity_q3", "utm_content=hca_teal_8pp"]))
ok("links: carries frn_campaign_id + frn_account_id", "frn_campaign_id=cmp_123" in url and "frn_account_id=acct_hca" in url)
ok("links: slug is opaque, NO PII (no @, no contact name/email)", "@" not in url and "hca-healthcare" in url)
hh = campaign_links.build_capacity_url(account_slug="Valley Home Health", segment="home_health", path="capacity")
ok("links: supports other segments (home_health) for the staged mailer families", "/home-health/" in hh)

# 5. Audience CSV round-trips with economics + tracked links
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "run.csv")
    hospital_audience.build_audience_csv(systems[:5], out, campaign_id="cmp_q3", campaign="hs_q3")
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    ok("audience: CSV has a row per system", len(rows) == 5)
    cols = set(rows[0].keys())
    ok("audience: CSV columns == address + merge cols (incl. landing_url/qr_url)",
       cols == set(hospital_audience.ADDR_COLS + hospital_audience.MERGE_COLS))
    ok("audience: every row has a tracked landing_url + qr_url",
       all(r["landing_url"].startswith("http") and r["qr_url"].startswith("http") for r in rows))
    ok("audience: $ + thousands formatting applied", rows[0]["list_rate"].startswith("$") and "," in rows[0]["rn_need"] or rows[0]["rn_need"].isdigit())

# 6. Mail-safe copy — no FICA/visa/tax/immigration/"eligible offsets" on the mailpiece.
#    Scan RENDERED copy only: strip comments/docstrings first, so the header comment that
#    STATES the rule ("NO FICA/visa…") isn't itself flagged.
import re
def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)        # JS/CSS block comments
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)        # HTML comments
    text = re.sub(r'"""(?:.|\n)*?"""', " ", text)              # py docstrings
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("//") or s.startswith("#"):
            continue                                            # whole-line JS/py comments
        out.append(line)
    return "\n".join(out)
copy_text = ""
for rel in ["renderer/hospital-booklet.js", "hospital_audience.py", "build_hospital_booklet.html"]:
    copy_text += _strip_comments(open(os.path.join(HERE, rel), encoding="utf-8").read()).lower()
banned = re.findall(r"fica|payroll[ -]?tax|\bvisa\b|immigration|eligible offset", copy_text)
ok("copy: no FICA / payroll-tax / visa / immigration / 'eligible offset' in rendered mailpiece copy",
   not banned, ",".join(sorted(set(banned))) or "clean")

print(f"\n{'CAPACITY OUTREACH VERIFY FAILED' if F else 'CAPACITY OUTREACH VERIFY PASSED'} — {P} passed, {F} failed")
raise SystemExit(1 if F else 0)
