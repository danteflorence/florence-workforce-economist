"""
Florence auth — email-OTP login that works locally and swaps to production
providers without changing call sites.

═══════════════════════════════════════════════════════════════════════════
WHY THIS MODULE EXISTS
═══════════════════════════════════════════════════════════════════════════
Until now the nurse portal used hard-coded demo passcodes (FLORENCE-001, etc.)
and the internal app had no gate at all. This module replaces both with a
single email-OTP flow that:

  - Works LOCALLY with no signup or external service (codes are written to
    data/auth_otp_outbox.log — dev tails the log to read the OTP)
  - Swaps to PRODUCTION email by setting env vars OR replacing the
    `_send_email` function with a Resend/SendGrid/SES call
  - Persists users + sessions to CSV today; clean migration path to
    Postgres/Supabase (the storage layer is two functions deep)

═══════════════════════════════════════════════════════════════════════════
PRODUCTION SWAP POINTS
═══════════════════════════════════════════════════════════════════════════

1. Email delivery — replace _send_email() with your provider:
       Resend:    https://resend.com/docs/api-reference
       SendGrid:  https://docs.sendgrid.com/api-reference
       SES:       boto3 client('ses').send_email(...)
   Or simply set env vars:
       FLORENCE_SMTP_HOST, FLORENCE_SMTP_PORT,
       FLORENCE_SMTP_USER, FLORENCE_SMTP_PASS, FLORENCE_FROM_EMAIL
   and SMTP will be used automatically.

2. User + session storage — replace _read_csv/_write_csv with a real DB
   client. The function signatures stay the same. Recommended targets:
       Supabase (Postgres + auth.users table)
       Clerk    (full SaaS, JWT exchange)
       Auth0    (full SaaS)

3. Session secret — set FLORENCE_SESSION_SECRET in production. Locally
   this module generates one and persists it to data/.auth_secret.

═══════════════════════════════════════════════════════════════════════════
DATA FILES
═══════════════════════════════════════════════════════════════════════════
data/auth_users.csv          user_id, email, name, role, created_at, last_login_at
data/auth_otp_codes.csv      email, code, expires_at, used_at
data/auth_sessions.csv       session_token, user_id, created_at, expires_at, revoked_at
data/auth_otp_outbox.log     local-dev log of all OTP codes ever generated
data/.auth_secret            32-byte HMAC secret (gitignored — do not commit)
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
USERS_FILE = DATA_DIR / "auth_users.csv"
OTP_FILE = DATA_DIR / "auth_otp_codes.csv"
SESSIONS_FILE = DATA_DIR / "auth_sessions.csv"
OTP_LOG = DATA_DIR / "auth_otp_outbox.log"
SECRET_FILE = DATA_DIR / ".auth_secret"

# Schemas
USER_FIELDS = ["user_id", "email", "name", "role", "created_at", "last_login_at"]
OTP_FIELDS = ["email", "code_hash", "expires_at", "used_at"]
SESSION_FIELDS = ["session_token_hash", "user_id", "created_at",
                  "expires_at", "revoked_at"]

# Tunables
OTP_TTL_MINUTES = 10
SESSION_TTL_DAYS = 30
OTP_CODE_LENGTH = 6   # digits


# ─── Secret management ──────────────────────────────────────────────
def _session_secret() -> bytes:
    """Return the HMAC secret for signing session tokens.

    Order of precedence:
      1. FLORENCE_SESSION_SECRET env var (production)
      2. data/.auth_secret file (local persistent)
      3. Generate a new one and persist it
    """
    env = os.environ.get("FLORENCE_SESSION_SECRET")
    if env:
        return env.encode()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    secret = secrets.token_bytes(32)
    SECRET_FILE.write_bytes(secret)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except Exception:
        pass
    return secret


def _hash(value: str) -> str:
    """Constant-time HMAC-SHA256 of a value with the session secret."""
    return hmac.new(_session_secret(), value.encode(), hashlib.sha256).hexdigest()


# ─── Storage helpers (CSV today, swap for DB later) ─────────────────
def _ensure_header(path: Path, fields: list[str]) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(fields)


def _read(path: Path, fields: list[str]) -> pd.DataFrame:
    _ensure_header(path, fields)
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in fields:
        if col not in df.columns:
            df[col] = ""
    return df


def _append(path: Path, fields: list[str], row: dict) -> None:
    _ensure_header(path, fields)
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([row.get(k, "") for k in fields])


def _rewrite(path: Path, fields: list[str], df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, columns=fields)


# ─── User management ────────────────────────────────────────────────
def get_user(email: str) -> Optional[dict]:
    df = _read(USERS_FILE, USER_FIELDS)
    email = email.strip().lower()
    hit = df[df["email"].str.lower() == email]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def create_or_get_user(email: str, name: str = "",
                       role: str = "nurse") -> dict:
    """Idempotent user creation. Returns the user dict."""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("Invalid email")
    existing = get_user(email)
    if existing:
        return existing
    user_id = f"U{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"
    row = {
        "user_id": user_id, "email": email, "name": name or email.split("@")[0],
        "role": role, "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "last_login_at": "",
    }
    _append(USERS_FILE, USER_FIELDS, row)
    return row


def update_user_role(email: str, role: str) -> bool:
    df = _read(USERS_FILE, USER_FIELDS)
    mask = df["email"].str.lower() == email.strip().lower()
    if not mask.any():
        return False
    df.loc[mask, "role"] = role
    _rewrite(USERS_FILE, USER_FIELDS, df)
    return True


# ─── Email delivery ─────────────────────────────────────────────────
def _send_email_smtp(to_email: str, subject: str, body: str) -> bool:
    """Send via SMTP. Skips if env vars not configured."""
    host = os.environ.get("FLORENCE_SMTP_HOST")
    port = int(os.environ.get("FLORENCE_SMTP_PORT", "587"))
    user = os.environ.get("FLORENCE_SMTP_USER")
    pw = os.environ.get("FLORENCE_SMTP_PASS")
    from_addr = os.environ.get("FLORENCE_FROM_EMAIL", user)
    if not (host and user and pw and from_addr):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[auth] SMTP send failed: {e}")
        return False


def _send_email(to_email: str, subject: str, body: str) -> str:
    """Deliver an email by whatever path is available.

    Returns the delivery channel used ("smtp" or "local_log").
    Local-log is fine for development — just `tail -f data/auth_otp_outbox.log`.
    """
    if _send_email_smtp(to_email, subject, body):
        return "smtp"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OTP_LOG, "a") as f:
        f.write(f"\n--- {datetime.utcnow().isoformat()} → {to_email} ---\n")
        f.write(f"Subject: {subject}\n\n{body}\n")
    return "local_log"


# ─── OTP flow ───────────────────────────────────────────────────────
def send_otp(email: str) -> dict:
    """Generate a 6-digit OTP, persist its hash, and deliver to the user.

    Returns: {"ok": bool, "channel": "smtp"|"local_log", "expires_at": str}
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "Invalid email"}
    code = "".join(secrets.choice("0123456789") for _ in range(OTP_CODE_LENGTH))
    expires_at = (datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(timespec="seconds")
    _append(OTP_FILE, OTP_FIELDS, {
        "email": email,
        "code_hash": _hash(code),
        "expires_at": expires_at,
        "used_at": "",
    })
    body = (
        f"Your Florence sign-in code is: {code}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes. "
        f"If you didn't request this, you can ignore the email."
    )
    channel = _send_email(email, "Your Florence sign-in code", body)
    return {"ok": True, "channel": channel, "expires_at": expires_at}


def verify_otp(email: str, code: str) -> Optional[dict]:
    """Verify the code. On success returns the user dict and creates a session token.

    NOTE: This function does NOT auto-create the user — the caller must
    call create_or_get_user() before send_otp(), or after verify_otp() if
    the flow is sign-up. This keeps the auth library role-agnostic.
    """
    email = email.strip().lower()
    code = code.strip()
    df = _read(OTP_FILE, OTP_FIELDS)
    now = datetime.utcnow()
    code_hash = _hash(code)
    # Find a matching, unused, unexpired code for this email
    cand = df[
        (df["email"].str.lower() == email)
        & (df["code_hash"] == code_hash)
        & (df["used_at"] == "")
    ].copy()
    cand = cand[cand["expires_at"].apply(
        lambda s: bool(s) and datetime.fromisoformat(s) > now
    )]
    if cand.empty:
        return None

    # Mark this code as used
    idx = cand.index[0]
    df.loc[idx, "used_at"] = now.isoformat(timespec="seconds")
    _rewrite(OTP_FILE, OTP_FIELDS, df)

    user = get_user(email)
    if not user:
        return None
    # Bump last_login
    udf = _read(USERS_FILE, USER_FIELDS)
    udf.loc[udf["email"].str.lower() == email, "last_login_at"] = now.isoformat(timespec="seconds")
    _rewrite(USERS_FILE, USER_FIELDS, udf)
    return user


# ─── Session tokens ─────────────────────────────────────────────────
def create_session(user_id: str) -> str:
    """Mint a session token tied to user_id and persist its hash."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS)).isoformat(timespec="seconds")
    _append(SESSIONS_FILE, SESSION_FIELDS, {
        "session_token_hash": _hash(token),
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "expires_at": expires,
        "revoked_at": "",
    })
    return token


def get_session(token: str) -> Optional[dict]:
    """Return user dict if token is valid, else None."""
    if not token:
        return None
    th = _hash(token)
    df = _read(SESSIONS_FILE, SESSION_FIELDS)
    hit = df[
        (df["session_token_hash"] == th)
        & (df["revoked_at"] == "")
    ]
    if hit.empty:
        return None
    row = hit.iloc[0]
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
            return None
    except Exception:
        return None
    udf = _read(USERS_FILE, USER_FIELDS)
    user = udf[udf["user_id"] == row["user_id"]]
    if user.empty:
        return None
    return user.iloc[0].to_dict()


def revoke_session(token: str) -> bool:
    if not token:
        return False
    th = _hash(token)
    df = _read(SESSIONS_FILE, SESSION_FIELDS)
    mask = df["session_token_hash"] == th
    if not mask.any():
        return False
    df.loc[mask, "revoked_at"] = datetime.utcnow().isoformat(timespec="seconds")
    _rewrite(SESSIONS_FILE, SESSION_FIELDS, df)
    return True


# ─── Streamlit integration helper ───────────────────────────────────
def streamlit_login(st, *, default_role: str = "nurse",
                    title: str = "Sign in to Florence",
                    blurb: str = "") -> Optional[dict]:
    """Render an email-OTP login form. Returns the user dict on success.

    Manages two session_state keys:
      - florence_session_token
      - florence_otp_email   (the email we just sent a code to)
    """
    # Already signed in?
    tok = st.session_state.get("florence_session_token")
    if tok:
        user = get_session(tok)
        if user:
            return user
        # Invalid — clear it
        st.session_state["florence_session_token"] = None

    st.markdown(f"### {title}")
    if blurb:
        st.caption(blurb)

    pending_email = st.session_state.get("florence_otp_email", "")

    if not pending_email:
        # Step 1: enter email
        with st.form("auth_email_form"):
            email = st.text_input(
                "Email", placeholder="you@hospital.com",
                key="auth_email_input",
            )
            name = st.text_input(
                "Name (optional, first time only)",
                key="auth_name_input",
            )
            submitted = st.form_submit_button(
                "Send me a code →", type="primary",
                use_container_width=True,
            )
        if submitted:
            try:
                create_or_get_user(email, name=name, role=default_role)
                res = send_otp(email)
                if res.get("ok"):
                    st.session_state["florence_otp_email"] = email.strip().lower()
                    if res.get("channel") == "local_log":
                        st.info(
                            "Local-dev mode: your 6-digit code was written to "
                            f"`{OTP_LOG.relative_to(Path.cwd()) if OTP_LOG.is_absolute() else OTP_LOG}`. "
                            "Run `tail -n 5 data/auth_otp_outbox.log` to read it.",
                            icon=":material/info:",
                        )
                    else:
                        st.success("Code sent. Check your inbox.")
                    st.rerun()
                else:
                    st.error(res.get("error", "Send failed"))
            except Exception as e:
                st.error(f"Error: {e}")
        return None

    # Step 2: enter code
    st.caption(f"We sent a 6-digit code to **{pending_email}**.")
    with st.form("auth_code_form"):
        code = st.text_input(
            "6-digit code",
            max_chars=OTP_CODE_LENGTH,
            placeholder="••••••",
            key="auth_code_input",
        )
        col_v, col_r = st.columns(2)
        with col_v:
            verify = st.form_submit_button(
                "Verify →", type="primary", use_container_width=True,
            )
        with col_r:
            reset = st.form_submit_button(
                "Use a different email", use_container_width=True,
            )
    if reset:
        st.session_state["florence_otp_email"] = ""
        st.rerun()
    if verify:
        user = verify_otp(pending_email, code)
        if user:
            token = create_session(user["user_id"])
            st.session_state["florence_session_token"] = token
            st.session_state["florence_otp_email"] = ""
            st.rerun()
        else:
            st.error("Code invalid or expired. Try again or request a new code.")
    return None


def streamlit_logout(st) -> None:
    tok = st.session_state.get("florence_session_token")
    if tok:
        revoke_session(tok)
    st.session_state["florence_session_token"] = None
    st.session_state["florence_otp_email"] = ""


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- Florence auth smoke test ---")
    test_email = "smoketest@florence.dev"
    u = create_or_get_user(test_email, name="Smoke Test", role="nurse")
    print(f"User: {u['user_id']} ({u['email']})")
    res = send_otp(test_email)
    print(f"send_otp → {res}")
    # Read the code from the log
    code = None
    if OTP_LOG.exists():
        for line in OTP_LOG.read_text().splitlines()[::-1]:
            if "Your Florence sign-in code is:" in line:
                code = line.split(":", 1)[1].strip()
                break
    print(f"Code from log: {code}")
    if code:
        v = verify_otp(test_email, code)
        print(f"verify_otp → {v['email'] if v else None}")
        if v:
            tok = create_session(v["user_id"])
            print(f"session token (truncated): {tok[:20]}…")
            s = get_session(tok)
            print(f"get_session → {s['email'] if s else None}")
            r = revoke_session(tok)
            print(f"revoke_session → {r}")
            s2 = get_session(tok)
            print(f"get_session (after revoke) → {s2}")


if __name__ == "__main__":
    main()
