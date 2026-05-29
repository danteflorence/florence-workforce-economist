"""
Role-based access control for the Florence internal app.

Builds on top of auth.py — auth answers "who are you?", rbac answers
"what can you do?". Roles + territory are stored in CSV today, with the
same swap-to-DB path as auth (one storage module deep).

═══════════════════════════════════════════════════════════════════════════
ROLE MATRIX
═══════════════════════════════════════════════════════════════════════════

Role        Scope                       Sees                                  Admin tabs
──────────  ──────────────────────────  ────────────────────────────────────  ──────────
rep         Assigned territory only     Hospitals + systems in territory      No
ops         National (all territories)  All hospitals, all systems            No
admin       National + write access     Everything                            Yes

Territory format:
  "ALL"              — full national access (default for ops / admin)
  "CA"               — single-state territory
  "CA,NV,OR,WA"      — comma-separated multi-state territory
  "NE" / "MW" / "S" / "W"  — Census region territory

═══════════════════════════════════════════════════════════════════════════
HOW TO ASSIGN ROLES
═══════════════════════════════════════════════════════════════════════════
At startup, the first user to sign in is auto-promoted to admin (call to
bootstrap_first_admin()). Subsequent users default to "rep" with territory
"ALL" until an admin re-assigns them in the Admin tab.

Admins can also assign roles by editing data/rbac_assignments.csv directly
and restarting the app.

═══════════════════════════════════════════════════════════════════════════
DATA FILE
═══════════════════════════════════════════════════════════════════════════
data/rbac_assignments.csv  email, role, territory, assigned_by, assigned_at
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RBAC_FILE = DATA_DIR / "rbac_assignments.csv"

RBAC_FIELDS = ["email", "role", "territory", "assigned_by", "assigned_at"]

VALID_ROLES = {"rep", "ops", "admin"}
DEFAULT_ROLE = "rep"
DEFAULT_TERRITORY = "ALL"

# Census region map (subset — full map lives in lead_scoring.py)
CENSUS_REGION = {
    "NE": {"CT", "ME", "MA", "NH", "NJ", "NY", "PA", "RI", "VT"},
    "MW": {"IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH",
           "SD", "WI"},
    "S":  {"AL", "AR", "DE", "DC", "FL", "GA", "KY", "LA", "MD", "MS",
           "NC", "OK", "SC", "TN", "TX", "VA", "WV"},
    "W":  {"AK", "AZ", "CA", "CO", "HI", "ID", "MT", "NV", "NM", "OR",
           "UT", "WA", "WY"},
}


# ─── Storage ────────────────────────────────────────────────────────
def _ensure_header() -> None:
    if not RBAC_FILE.exists():
        RBAC_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RBAC_FILE, "w", newline="") as f:
            csv.writer(f).writerow(RBAC_FIELDS)


def _read() -> pd.DataFrame:
    _ensure_header()
    return pd.read_csv(RBAC_FILE, dtype=str).fillna("")


def _rewrite(df: pd.DataFrame) -> None:
    df.to_csv(RBAC_FILE, index=False, columns=RBAC_FIELDS)


# ─── Role queries ───────────────────────────────────────────────────
def get_assignment(email: str) -> Optional[dict]:
    df = _read()
    email = email.strip().lower()
    hit = df[df["email"].str.lower() == email]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def get_role(email: str) -> str:
    a = get_assignment(email)
    if not a:
        return DEFAULT_ROLE
    role = (a.get("role") or "").strip().lower()
    return role if role in VALID_ROLES else DEFAULT_ROLE


def get_territory(email: str) -> str:
    a = get_assignment(email)
    if not a:
        return DEFAULT_TERRITORY
    return (a.get("territory") or DEFAULT_TERRITORY).strip()


def assign(email: str, role: str, territory: str = DEFAULT_TERRITORY,
           assigned_by: str = "system") -> None:
    """Upsert an assignment. Raises ValueError on invalid role."""
    role = role.strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of {VALID_ROLES}")
    email = email.strip().lower()
    df = _read()
    mask = df["email"].str.lower() == email
    row = {
        "email": email,
        "role": role,
        "territory": territory.strip() or DEFAULT_TERRITORY,
        "assigned_by": assigned_by,
        "assigned_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    if mask.any():
        for k, v in row.items():
            df.loc[mask, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _rewrite(df)


def bootstrap_first_admin(email: str) -> bool:
    """If no admin exists yet, promote this user to admin. Idempotent.

    Returns True if a promotion happened, False otherwise.
    """
    df = _read()
    has_admin = (df["role"].str.lower() == "admin").any()
    if has_admin:
        return False
    assign(email, role="admin", territory="ALL", assigned_by="bootstrap")
    return True


def list_assignments() -> pd.DataFrame:
    return _read()


# ─── Territory parsing + data filtering ─────────────────────────────
def parse_territory(territory: str) -> set[str]:
    """Convert a territory string to a set of state codes.

    Returns set() for "ALL" (sentinel for unrestricted access — call sites
    should special-case this).
    """
    t = (territory or "").strip().upper()
    if not t or t == "ALL":
        return set()
    # Census region?
    if t in CENSUS_REGION:
        return set(CENSUS_REGION[t])
    # Comma-separated list of state codes
    return {tok.strip() for tok in t.split(",") if tok.strip()}


def filter_by_territory(
    df: pd.DataFrame,
    territory: str,
    state_col: str = "state",
) -> pd.DataFrame:
    """Filter a dataframe to rows in the given territory.

    "ALL" returns the df unchanged. Unknown state column returns df unchanged.
    """
    states = parse_territory(territory)
    if not states or state_col not in df.columns:
        return df
    return df[df[state_col].astype(str).str.upper().isin(states)]


# ─── Permission helpers ─────────────────────────────────────────────
def has_role(email: str, allowed: Iterable[str]) -> bool:
    return get_role(email) in set(allowed)


def is_admin(email: str) -> bool:
    return get_role(email) == "admin"


def streamlit_require_role(st, allowed: Iterable[str],
                           message: str = "Restricted to authorized roles.") -> bool:
    """Render an inline 'restricted' notice and return False if user lacks role.

    Use at the top of a tab:
        if not rbac.streamlit_require_role(st, ["ops", "admin"]):
            st.stop()
    """
    user = st.session_state.get("current_user") or {}
    email = user.get("email", "")
    role = st.session_state.get("current_role", DEFAULT_ROLE)
    if role in set(allowed):
        return True
    st.warning(
        f":material/lock: {message} You are signed in as **{email or 'guest'}** "
        f"with role **{role}**. Required: {', '.join(allowed)}.",
        icon=":material/lock:",
    )
    return False


# ─── Streamlit admin panel ──────────────────────────────────────────
def streamlit_admin_panel(st) -> None:
    """Render the admin panel for managing role assignments. Admin-only."""
    if not streamlit_require_role(st, ["admin"],
                                  message="Role management is admin-only."):
        return
    st.markdown("#### Active assignments")
    df = list_assignments()
    if df.empty:
        st.info("No assignments yet. The first user to sign in is auto-admin.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Assign / update a user")
    # Pull the user list from auth.py
    try:
        import auth as _flo_auth
        users_df = _flo_auth._read(_flo_auth.USERS_FILE, _flo_auth.USER_FIELDS)
        email_options = sorted(users_df["email"].dropna().unique().tolist())
    except Exception:
        email_options = []
    with st.form("rbac_assign_form"):
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            email_pick = st.selectbox(
                "User",
                options=["— pick a user —"] + email_options,
            )
        with c2:
            role_pick = st.selectbox("Role", options=list(VALID_ROLES))
        with c3:
            territory_pick = st.text_input(
                "Territory",
                value=DEFAULT_TERRITORY,
                help="ALL, a state code (e.g. CA), comma-separated states "
                     "(CA,NV,OR), or a Census region (NE/MW/S/W).",
            )
        submitted = st.form_submit_button(
            "Save assignment", type="primary", use_container_width=True,
        )
    if submitted:
        if email_pick == "— pick a user —":
            st.error("Pick a user.")
            return
        assigner = (st.session_state.get("current_user") or {}).get("email", "admin")
        try:
            assign(email_pick, role_pick, territory_pick, assigned_by=assigner)
            st.success(f"Assigned {email_pick} → {role_pick} / {territory_pick}.")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")


# ─── CLI smoke test ─────────────────────────────────────────────────
def main():
    print("--- Florence RBAC smoke test ---")
    bootstrap_first_admin("alice@florence.dev")
    print("After bootstrap, alice role:", get_role("alice@florence.dev"))
    assign("bob@florence.dev", role="rep", territory="CA,NV",
           assigned_by="alice@florence.dev")
    print("Bob role:", get_role("bob@florence.dev"))
    print("Bob territory:", get_territory("bob@florence.dev"))
    print("Bob territory set:", parse_territory(get_territory("bob@florence.dev")))
    assign("carol@florence.dev", role="ops", territory="ALL",
           assigned_by="alice@florence.dev")
    print("Carol role:", get_role("carol@florence.dev"))
    print("\nAll assignments:")
    print(list_assignments().to_string(index=False))
    # Territory filter demo
    import pandas as _pd
    test = _pd.DataFrame({
        "ccn": ["A", "B", "C", "D"],
        "state": ["CA", "NV", "TX", "FL"],
        "rn_need": [100, 50, 200, 150],
    })
    print("\nFull table:")
    print(test.to_string(index=False))
    print("\nBob (territory CA,NV) sees:")
    print(filter_by_territory(test, get_territory("bob@florence.dev")).to_string(index=False))
    print("\nCarol (territory ALL) sees:")
    print(filter_by_territory(test, get_territory("carol@florence.dev")).to_string(index=False))


if __name__ == "__main__":
    main()
