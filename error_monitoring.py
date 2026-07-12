"""
Error monitoring for the Workforce Economist services.

Two layers, both zero-config by default:

  1. Always on — ERROR-level records append to data/errors.log (the Render
     persistent disk in production), so there is a server-side trace even
     with nothing provisioned.
  2. Optional — if SENTRY_DSN is set (and sentry-sdk is installed), errors
     also stream to Sentry with the service name tagged. No DSN → no-op.

Usage (idempotent; call once near the top of each entrypoint):

    from error_monitoring import init_monitoring
    init_monitoring("economist")        # app.py
    init_monitoring("pricing-api")      # pricing_api.py
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

_INITIALIZED: set[str] = set()

LOG_PATH = Path(__file__).resolve().parent / "data" / "errors.log"


def init_monitoring(service: str) -> None:
    if service in _INITIALIZED:
        return
    _INITIALIZED.add(service)

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setLevel(logging.ERROR)
        handler.setFormatter(logging.Formatter(
            f"%(asctime)s [{service}] %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
    except OSError:
        pass  # read-only filesystem etc. — never block startup on logging

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("FLORENCE_ENV", "production"),
            release=os.environ.get("RENDER_GIT_COMMIT", None),
            traces_sample_rate=0.0,   # errors only; no perf tracing cost
            send_default_pii=False,   # lead/contact PII stays out of Sentry
        )
        sentry_sdk.set_tag("service", service)
    except Exception:
        logging.getLogger(__name__).exception("Sentry init failed; continuing without it")
