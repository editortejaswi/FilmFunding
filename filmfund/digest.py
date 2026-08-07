"""
Per-user email digest: each filmmaker gets the newest still-open funding calls
they haven't been mailed yet, soonest deadline first. Nothing repeats — every
sent item is recorded per user.
"""

from datetime import date

from . import config, db, email_send


def _days_left(deadline: str):
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline[:10]) - date.today()).days
    except Exception:  # noqa: BLE001
        return None


def _fmt_inr(v):
    try:
        v = int(v)
    except Exception:  # noqa: BLE001
        return ""
    if v >= 10_000_000:
        return f"₹{v/10_000_000:.1f} Cr"
    if v >= 100_000:
        return f"₹{v/100_000:.1f} L"
    return f"₹{v:,}"


def _row_html(r):
    dl = _days_left(r["deadline"])
    if dl is None:
        badge = '<span style="color:#888">deadline: see call</span>'
    elif dl < 0:
        badge = '<span style="color:#b00">closed</span>'
    else:
        color = "#b00020" if dl <= 7 else ("#b8860b" if dl <= 21 else "#0a7d33")
        badge = f'<span style="color:{color};font-weight:700">{dl} days left</span>'
    region = config.REGION_LABELS.get(r["country"], (r["country"] or "").title() or "Global")
    return (
        f'<div style="padding:12px 0;border-bottom:1px solid #eee">'
        f'<a href="{r["url"]}" style="font-size:15px;font-weight:700;color:#111;'
        f'text-decoration:none">{r["title"][:140]}</a>'
        f'<div style="color:#666;font-size:12px;margin:4px 0">'
        f'{badge} &middot; {region} &middot; {_fmt_inr(r["est_value_inr"])}'
        + (f' &middot; {r["org"][:50]}' if r["org"] else "") + '</div></div>')


def build_html(rows) -> str:
    body = ('<p style="font-size:15px">New film-funding opportunities for you — '
            'soonest deadline first:</p>' + "".join(_row_html(r) for r in rows)
            + f'<p style="margin-top:18px"><a href="{config.BASE_URL}" '
            f'style="display:inline-block;background:#e11d2a;color:#fff;text-decoration:none;'
            f'padding:11px 20px;border-radius:8px;font-weight:700">Open the app</a></p>')
    return email_send.shell(body)


def send_user_digest(conn, user, limit: int = 12) -> int:
    regions = [x for x in (user["regions"] or "").split(",") if x]
    rows = db.unsent_for(conn, user["email"], dl_bucket="open", limit=limit * 3)
    if regions:
        rows = [r for r in rows if r["country"] in regions]
    rows = rows[:limit]
    if not rows:
        return 0
    ok = email_send.send_email(
        f"🎬 {len(rows)} film-funding calls for you — apply before they close",
        build_html(rows), user["email"])
    if ok:
        db.mark_sent(conn, user["email"], [r["id"] for r in rows])
        return len(rows)
    return 0


def run_digests(conn=None) -> int:
    conn = conn or db.init_db(config.DB_PATH)
    users = db.all_users(conn, digest_only=True)
    total = 0
    for u in users:
        total += send_user_digest(conn, u)
    print(f"  [digest] mailed {total} items across {len(users)} users")
    return total
