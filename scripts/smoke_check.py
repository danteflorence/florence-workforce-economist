#!/usr/bin/env python3
"""
Post-deploy smoke check — answers "did it actually deploy and work?"

Stdlib only (no deps), so it runs on your laptop or in CI. Checks:
  • Streamlit app   GET  {app}/_stcore/health   → 200 "ok"
  • Pricing API     GET  {api}/health           → 200 {"status":"ok"}
  • Pricing API     POST {api}/price            → 200, a sane Florence fee

Usage:
  python3 scripts/smoke_check.py --app-url https://florence-economist.onrender.com \
                                 --api-url https://florence-pricing-api.onrender.com
  # or via env: FLORENCE_APP_URL / FLORENCE_API_URL

Cloudflare Access note: if the app sits behind CF Access, an unauthenticated
GET returns a 302/303 to a login page. That's EXPECTED — Render's own health
check still validates the app booted. To check straight through CF Access, set a
service token:  CF_ACCESS_CLIENT_ID=...  CF_ACCESS_CLIENT_SECRET=...
"""
from __future__ import annotations  # so `dict | None` annotations work on Python 3.9

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

TIMEOUT = 25
GREEN, RED, YEL, RST = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def _headers() -> dict:
    h = {"User-Agent": "florence-smoke-check"}
    cid, csec = os.environ.get("CF_ACCESS_CLIENT_ID"), os.environ.get("CF_ACCESS_CLIENT_SECRET")
    if cid and csec:
        h["CF-Access-Client-Id"] = cid
        h["CF-Access-Client-Secret"] = csec
    return h


def _request(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    h = _headers()
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def _ok(msg):  print(f"  {GREEN}✓{RST} {msg}")
def _warn(msg): print(f"  {YEL}!{RST} {msg}")
def _fail(msg): print(f"  {RED}✗{RST} {msg}")


def check_app(url: str) -> bool:
    print(f"App  · {url}")
    status, text = _request("GET", url.rstrip("/") + "/_stcore/health")
    if status == 200 and "ok" in text.lower():
        _ok("Streamlit health: 200 ok"); return True
    if status in (301, 302, 303, 307, 308):
        _warn(f"redirect ({status}) — likely Cloudflare Access. App boot is still "
              "validated by Render's health check; pass a CF service token to check through.")
        return True  # not a failure: the gate is expected
    _fail(f"Streamlit health: {status} {text[:120]!r}"); return False


def check_api(url: str) -> bool:
    base = url.rstrip("/")
    print(f"API  · {base}")
    ok = True
    status, text = _request("GET", base + "/health")
    if status == 200 and json.loads(text or "{}").get("status") == "ok":
        _ok("API health: 200 ok")
    else:
        _fail(f"API health: {status} {text[:120]!r}"); ok = False

    body = {"hospital": {"name": "Smoke Test", "state": "CA",
                         "taxable_wage_per_hour": 66.85, "benefit_load_per_hour": 17.50,
                         "all_in_agency_per_hour": 121.73}}
    status, text = _request("POST", base + "/price", body)
    try:
        fee = json.loads(text).get("florence_monthly_fee_per_rn") if status == 200 else None
    except Exception:
        fee = None
    if status == 200 and isinstance(fee, (int, float)) and 500 <= fee <= 4000:
        _ok(f"API /price: 200, Florence fee ${fee:,.0f}/RN/mo (in range)")
    else:
        _fail(f"API /price: {status} fee={fee} {text[:120]!r}"); ok = False
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Florence post-deploy smoke check")
    ap.add_argument("--app-url", default=os.environ.get("FLORENCE_APP_URL"))
    ap.add_argument("--api-url", default=os.environ.get("FLORENCE_API_URL"))
    args = ap.parse_args()

    if not args.app_url and not args.api_url:
        print("Provide --app-url and/or --api-url (or FLORENCE_APP_URL / FLORENCE_API_URL).")
        return 2

    results = []
    if args.app_url:
        results.append(check_app(args.app_url))
    if args.api_url:
        results.append(check_api(args.api_url))

    passed = all(results)
    print()
    print(f"{GREEN}SMOKE PASS{RST}" if passed else f"{RED}SMOKE FAIL{RST}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
