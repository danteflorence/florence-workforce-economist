"""
Google sign-in gate (Streamlit native OIDC, 1.42+).

DESIGN: the gate is *conditional*. It enforces login only when a `[auth]`
section exists in .streamlit/secrets.toml (or st.secrets). With no secrets, every
function no-ops and the app runs exactly as before — so wiring this in can never
lock anyone out of the live app before YOU provision the Google OAuth client.

YOU PROVISION (the agent can't): a Google Cloud OAuth 2.0 client, and the
[auth] secrets (client_id / client_secret / cookie_secret / redirect_uri). See
.streamlit/secrets.toml.example. Optionally restrict to your domain(s) via
FLORENCE_ALLOWED_DOMAIN=florence.health (or [auth].allowed_domain).

This handles authentication only (who you are). Gmail/Streak API calls need their
own OAuth scope + flow (see crm_sync.py) — they can share the same Google client.
"""
from __future__ import annotations

import os
from typing import Optional


def is_configured(st) -> bool:
    """True iff a usable [auth] section is present in secrets."""
    try:
        auth = st.secrets.get("auth")
    except Exception:
        return False
    if not auth:
        return False
    try:
        return bool(auth.get("client_id") or auth.get("google") or auth.get("cookie_secret"))
    except Exception:
        return bool(auth)


def _provider(st) -> Optional[str]:
    """Named sub-provider ('google') if configured, else None (default provider)."""
    try:
        auth = st.secrets.get("auth") or {}
        g = auth.get("google")
        if hasattr(g, "get") or isinstance(g, dict):
            return "google"
    except Exception:
        pass
    return None


def _allowed_domains(st) -> set:
    raw = os.environ.get("FLORENCE_ALLOWED_DOMAIN", "")
    if not raw:
        try:
            raw = (st.secrets.get("auth") or {}).get("allowed_domain", "") or ""
        except Exception:
            raw = ""
    return {d.strip().lower() for d in raw.replace(";", ",").split(",") if d.strip()}


def current_user(st) -> Optional[dict]:
    """Return {'email','name'} if a Google session is active, else None."""
    try:
        u = st.user
    except Exception:
        return None
    if u is None:
        return None
    logged = bool(getattr(u, "is_logged_in", False))
    if not logged:
        return None

    def _g(key):
        v = getattr(u, key, None)
        if v is None and hasattr(u, "get"):
            try:
                v = u.get(key)
            except Exception:
                v = None
        return v

    email = (_g("email") or "").strip()
    return {"email": email, "name": (_g("name") or email or "").strip()}


def require_login(st) -> Optional[dict]:
    """Gate the app.

    • Not configured → return None (OPEN mode; caller proceeds unauthenticated).
    • Configured + not logged in → render a sign-in card and st.stop().
    • Configured + logged in but off-domain → show a notice + logout, st.stop().
    • Configured + logged in + allowed → return {'email','name'}.
    """
    if not is_configured(st):
        return None

    user = current_user(st)
    if user is None:
        st.markdown(
            "<div style='max-width:460px;margin:90px auto;padding:36px;border:1px "
            "solid #E4E7EC;border-radius:16px;background:#fff;text-align:center;'>"
            "<div style='font-family:\"Playfair Display\",Georgia,serif;font-size:26px;"
            "color:#067F7B;font-weight:700;'>Florence</div>"
            "<div style='font-weight:600;color:#101828;margin-top:10px;'>"
            "Workforce Economist</div>"
            "<div style='color:#475467;font-size:14px;margin:8px 0 22px;'>"
            "Internal tool — sign in with your Florence Google account.</div></div>",
            unsafe_allow_html=True,
        )
        col = st.columns([1, 1.4, 1])[1]
        with col:
            prov = _provider(st)
            if st.button("Sign in with Google", type="primary", use_container_width=True,
                         key="florence_google_login"):
                st.login(prov) if prov else st.login()
        st.stop()

    allowed = _allowed_domains(st)
    if allowed:
        domain = user["email"].split("@")[-1].lower() if "@" in user["email"] else ""
        if domain not in allowed:
            st.error(
                f"{user['email']} isn't in an authorized Florence workspace "
                f"({', '.join(sorted(allowed))}). Ask an admin for access."
            )
            if st.button("Sign out", key="florence_google_logout_denied"):
                st.logout()
            st.stop()
    return user


def logout_button(st, *, location=None) -> None:
    """Small sign-out control (only meaningful when auth is configured)."""
    if not is_configured(st) or current_user(st) is None:
        return
    target = location or st.sidebar
    u = current_user(st)
    target.caption(f"Signed in · {u['email']}")
    if target.button("Sign out", key="florence_google_logout"):
        st.logout()
