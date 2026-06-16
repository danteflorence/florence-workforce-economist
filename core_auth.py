"""
FlorenceRN Core SSO verification for the Streamlit Workforce Economist.

Verifies the shared `fl_session` RS256 cookie minted by FlorenceRN Core (against
Core's JWKS) and maps the Core role onto rbac.py's admin/ops/rep model. Mirrors
florence_auth.py's conditional design: when there's no valid Core session the
caller either falls back to a legacy path or is sent to Core to sign in.

The cookie is HttpOnly, but Streamlit reads request cookies SERVER-SIDE via
st.context.cookies (Streamlit >= 1.42), so HttpOnly is not a problem here.

Requires: pyjwt[crypto]  (added to requirements.txt).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional
from urllib.parse import quote

CORE_URL = os.environ.get("CORE_ISSUER_URL", os.environ.get("PUBLIC_CORE_URL", "http://id.lvh.me:8080")).rstrip("/")
JWKS_URL = os.environ.get("CORE_JWKS_URL", f"{CORE_URL}/.well-known/jwks.json")
ISSUER = os.environ.get("TOKEN_ISS", "florence-auth")
AUDIENCE = os.environ.get("TOKEN_AUD", "florence")
COOKIE_NAME = os.environ.get("COOKIE_NAME", "fl_session")

# Core role → Streamlit rbac role (rbac.py VALID_ROLES = {rep, ops, admin}).
ROLE_MAP = {"super_admin": "admin", "ops": "ops", "qa": "ops", "instructor": "ops", "rep": "rep"}


def is_configured() -> bool:
    """True iff the PyJWT crypto stack is importable (else caller falls back)."""
    try:
        import jwt  # noqa: F401
        import cryptography  # noqa: F401
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _jwk_client():
    from jwt import PyJWKClient
    # Cache JWKS for an hour; PyJWKClient refetches on unknown kid (rotation-safe).
    return PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)


def verify_token(token: str) -> Optional[dict]:
    """Verify an RS256 Core token against Core's JWKS. Returns claims or None."""
    if not token:
        return None
    try:
        import jwt
        signing_key = _jwk_client().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=60,
        )
    except Exception:
        return None


def map_role(core_role: Optional[str]) -> Optional[str]:
    return ROLE_MAP.get(core_role or "")


def login_url(redirect: str) -> str:
    return f"{CORE_URL}/login?redirect={quote(redirect or CORE_URL, safe='')}"


def logout_url(redirect: str) -> str:
    return f"{CORE_URL}/logout?redirect={quote(redirect or CORE_URL, safe='')}"


def app_origin(st) -> str:
    """Best-effort public origin of THIS app, for the post-login return URL."""
    try:
        h = st.context.headers
        host = h.get("Host") or h.get("host") or ""
        proto = h.get("X-Forwarded-Proto") or (
            "http" if ("lvh.me" in host or "localhost" in host or "127.0.0.1" in host) else "https"
        )
        return f"{proto}://{host}" if host else CORE_URL
    except Exception:
        return os.environ.get("PUBLIC_PRICING_URL", CORE_URL)


def current_user(st) -> Optional[dict]:
    """Read + verify the Core cookie from the Streamlit request.

    Returns {email, name, role, core_role, territory} when a valid Core session
    is present, else None. `role` is the mapped rbac role (may be None if the
    user has no pricing-relevant Core role).
    """
    token = None
    try:
        token = st.context.cookies.get(COOKIE_NAME)
    except Exception:
        token = None
    claims = verify_token(token) if token else None
    if not claims:
        return None
    core_role = claims.get("role")
    return {
        "email": claims.get("email") or "",
        "name": claims.get("name") or claims.get("email") or "",
        "role": map_role(core_role),
        "core_role": core_role,
        "territory": claims.get("territory"),
    }


def require_login(st) -> Optional[dict]:
    """Gate the app on a Core session.

    • Valid Core session with a pricing role → return the user dict.
    • Signed in but no pricing role → show a notice + Core switch link, st.stop().
    • No session → render a sign-in card linking to Core, st.stop().
    """
    user = current_user(st)
    if user and user.get("role"):
        return user
    target = login_url(app_origin(st))
    if user and not user.get("role"):
        st.error(
            f"{user.get('email', 'You')} is signed in but has no Workforce Economist "
            f"role. Ask an admin for rep / ops / admin access."
        )
        st.link_button("Switch account", target)
    else:
        st.markdown("### Florence Workforce Economist")
        st.write("Sign in with your FlorenceRN account to continue.")
        st.link_button("Sign in with FlorenceRN", target)
    st.stop()
    return None
