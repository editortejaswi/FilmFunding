"""
Passwordless auth: a filmmaker enters their email, we mail a one-time magic
link; clicking it mints a long-lived session cookie. Stdlib only (secrets).
"""

import secrets
from datetime import datetime, timedelta, timezone

from . import config, db, email_send


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def request_login(conn, email: str) -> str:
    """Create a magic-link token, email it, and return the link (also logged
    for local/dev use). Registers the user if new."""
    email = (email or "").strip().lower()
    if "@" not in email:
        raise ValueError("invalid email")
    db.upsert_user(conn, email)
    token = secrets.token_urlsafe(32)
    expires = _iso(_now() + timedelta(minutes=config.MAGIC_LINK_TTL_MIN))
    conn.execute("INSERT INTO login_tokens (token,email,expires_at) VALUES (?,?,?)",
                 (token, email, expires))
    conn.commit()
    link = f"{config.BASE_URL}/auth?token={token}"
    email_send.send_magic_link(email, link)
    print(f"  [auth] magic link for {email}: {link}")   # visible for local testing
    return link


def consume_login(conn, token: str) -> str:
    """Validate a magic-link token; on success create a session and return its
    cookie token. Returns '' on invalid/expired/used token."""
    row = conn.execute("SELECT * FROM login_tokens WHERE token=?", (token,)).fetchone()
    if not row or row["used"]:
        return ""
    try:
        if datetime.fromisoformat(row["expires_at"]) < _now():
            return ""
    except Exception:  # noqa: BLE001
        return ""
    conn.execute("UPDATE login_tokens SET used=1 WHERE token=?", (token,))
    email = row["email"]
    session = secrets.token_urlsafe(32)
    expires = _iso(_now() + timedelta(days=config.SESSION_TTL_DAYS))
    conn.execute("INSERT INTO sessions (token,email,expires_at) VALUES (?,?,?)",
                 (session, email, expires))
    db.touch_login(conn, email)
    conn.commit()
    return session


def session_email(conn, token: str) -> str:
    if not token:
        return ""
    row = conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    if not row:
        return ""
    try:
        if datetime.fromisoformat(row["expires_at"]) < _now():
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return row["email"]


def logout(conn, token: str):
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
