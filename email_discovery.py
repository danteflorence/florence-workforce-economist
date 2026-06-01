"""
Email discovery — close the biggest gap in the outreach engine.

CMS gives us named decision-makers + phones but NO email, so the email / Gmail
channel can't fire for most accounts. This derives the *likely* work email from
the person's name + the organization's domain (the directory carries a domain
per system), ranked by how common each corporate pattern is, so a rep can
click-to-fill instead of guessing.

Honest by design:
  • Pattern generation is instant + offline (no spammy SMTP probing, which is
    unreliable and can wreck sender reputation).
  • domain_deliverable() does a best-effort MX check (dnspython if installed,
    else returns None = unknown) — "does this domain accept mail at all".
  • verify_email() is a DORMANT vendor hook: if EMAIL_VERIFY_URL is set it POSTs
    the address to your verifier (NeverBounce/ZeroBounce/etc.) and returns its
    verdict; otherwise it reports "unknown". Never fabricates a "verified" claim.

YOU PROVISION (optional): EMAIL_VERIFY_URL (+ EMAIL_VERIFY_KEY) for paid
verification; `pip install dnspython` for MX checks.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DIRECTORY_FILE = DATA_DIR / "system_directory.csv"

# Common corporate local-part patterns, most → least likely.
_PATTERNS = [
    ("first.last", lambda f, l: f"{f}.{l}"),
    ("firstlast", lambda f, l: f"{f}{l}"),
    ("flast", lambda f, l: f"{f[0]}{l}"),
    ("first", lambda f, l: f),
    ("first_last", lambda f, l: f"{f}_{l}"),
    ("f.last", lambda f, l: f"{f[0]}.{l}"),
    ("lastfirst", lambda f, l: f"{l}{f}"),
    ("last.first", lambda f, l: f"{l}.{f}"),
    ("last", lambda f, l: l),
    ("first.l", lambda f, l: f"{f}.{l[0]}"),
]

_TITLES = {"dr", "mr", "mrs", "ms", "miss", "prof", "rev", "sir"}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "md", "rn", "msn", "dnp", "phd", "mba", "fache"}


def normalize_domain(domain: str) -> str:
    """Strip scheme / www / path → bare registrable domain."""
    d = (domain or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    d = re.sub(r"^www\.", "", d)
    return d.strip()


def _name_parts(name: str) -> tuple[str, str] | None:
    """Return (first, last) lowercased + alnum-only, or None if unparseable."""
    raw = re.split(r"[\s,]+", (name or "").strip())
    toks = []
    for t in raw:
        clean = re.sub(r"[^a-zA-Z]", "", t).lower()
        if not clean or clean in _TITLES or clean in _SUFFIXES:
            continue
        toks.append(clean)
    if len(toks) < 2:
        return None
    return toks[0], toks[-1]


def candidate_emails(name: str, domain: str, limit: int = 6) -> list[dict]:
    """Ranked candidate work emails for a person at a domain.

    Returns [{pattern, email}] best-guess first. Empty if name/domain unusable.
    """
    dom = normalize_domain(domain)
    parts = _name_parts(name)
    if not dom or "." not in dom or not parts:
        return []
    f, l = parts
    seen, out = set(), []
    for label, fn in _PATTERNS:
        try:
            local = fn(f, l)
        except Exception:
            continue
        email = f"{local}@{dom}"
        if email in seen:
            continue
        seen.add(email)
        out.append({"pattern": label, "email": email})
        if len(out) >= limit:
            break
    return out


def system_domain(system_id: str) -> str:
    """Look up a health system's email domain from the directory."""
    if not DIRECTORY_FILE.exists():
        return ""
    try:
        import pandas as pd
        df = pd.read_csv(DIRECTORY_FILE, dtype=str).fillna("")
        m = df[df["florence_system_id"].astype(str) == str(system_id)]
        if not m.empty:
            return normalize_domain(str(m.iloc[0].get("domain", "")))
    except Exception:
        pass
    return ""


def domain_deliverable(domain: str) -> bool | None:
    """Best-effort: does the domain publish MX records (accepts mail)?
    True / False, or None when we can't tell (dnspython not installed / lookup error)."""
    dom = normalize_domain(domain)
    if not dom:
        return None
    try:
        import dns.resolver  # type: ignore
        ans = dns.resolver.resolve(dom, "MX", lifetime=4.0)
        return len(ans) > 0
    except Exception:
        return None


def verify_email(email: str, timeout: float = 8.0) -> dict:
    """Dormant vendor hook. With EMAIL_VERIFY_URL set, POST {email} and pass the
    verifier's verdict through; otherwise report 'unknown' (never fabricate)."""
    url = os.environ.get("EMAIL_VERIFY_URL", "")
    if not url:
        return {"status": "unknown", "detail": "No verifier configured (EMAIL_VERIFY_URL)."}
    try:
        import requests
        headers = {}
        key = os.environ.get("EMAIL_VERIFY_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        r = requests.post(url, json={"email": email}, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return {"status": str(data.get("status", "unknown")), "raw": data}
    except Exception as e:
        return {"status": "unknown", "detail": f"Verify failed: {e}"}


def suggest_for(*, name: str, domain: str = "", system_id: str = "") -> dict:
    """Convenience: resolve domain (explicit or via system directory), generate
    ranked candidates, and report MX deliverability of the domain."""
    dom = normalize_domain(domain) or (system_domain(system_id) if system_id else "")
    cands = candidate_emails(name, dom)
    return {
        "domain": dom,
        "candidates": cands,
        "top": cands[0]["email"] if cands else "",
        "mx": domain_deliverable(dom) if dom else None,
    }
