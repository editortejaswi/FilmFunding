"""
FilmFund Radar — installable PWA served by stdlib http.server.

Routes:
  GET  /                     feed (if signed in) else the sign-in screen
  GET  /login                sign-in screen
  POST /login                request a magic link for an email
  GET  /auth?token=          consume magic link -> set session cookie -> /
  GET  /logout               end session
  GET  /api/opportunities    JSON feed (?dl=&region=)
  POST /prefs                update region filter / digest toggle
  GET  /manifest.webmanifest, /sw.js, /icon-192.png, /icon-512.png
"""

import http.cookies
import json
import urllib.parse as up
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import auth, config, db

STATIC = Path(__file__).parent / "static"
COOKIE = "ffr_session"


def _days_left(deadline):
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


_HEAD = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#e11d2a">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-192.png">
<title>FilmFund Radar</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;
background:#0f1115;color:#e9e9ee}a{color:inherit}
.top{position:sticky;top:0;background:#15181f;padding:14px 16px;border-bottom:1px solid #262a33;
display:flex;align-items:center;gap:10px}
.brand{font-weight:800;color:#e11d2a;font-size:18px}.brand span{color:#e9e9ee}
.sub{color:#8b90a0;font-size:12px}
.wrap{max-width:720px;margin:0 auto;padding:14px 14px 90px}
.tabs{display:flex;gap:6px;overflow-x:auto;padding:10px 0}
.tab{white-space:nowrap;padding:7px 13px;border-radius:20px;background:#1b1f28;color:#c7ccd8;
font-size:13px;text-decoration:none;border:1px solid #262a33}
.tab.on{background:#e11d2a;color:#fff;border-color:#e11d2a}
.tab b{opacity:.7;font-weight:600;margin-left:4px}
.card{background:#161a21;border:1px solid #232833;border-radius:14px;padding:14px;margin:10px 0}
.card h3{margin:0 0 6px;font-size:15px;line-height:1.3}
.meta{color:#8b90a0;font-size:12px;margin:2px 0}
.dl{font-weight:700;font-size:12px;padding:3px 9px;border-radius:20px;display:inline-block}
.dl.u{background:#3a1113;color:#ff8a8a}.dl.s{background:#3a3111;color:#ffd68a}
.dl.o{background:#0f2f1b;color:#8ff0b5}.dl.c{background:#26262a;color:#9a9aa2}
.dl.n{background:#26262a;color:#9a9aa2}
.go{display:inline-block;margin-top:8px;background:#e11d2a;color:#fff;text-decoration:none;
padding:9px 16px;border-radius:9px;font-weight:700;font-size:13px}
.empty{color:#8b90a0;text-align:center;padding:40px 10px}
.auth{max-width:420px;margin:8vh auto;padding:24px;text-align:center}
.auth h1{color:#e11d2a;font-size:26px;margin:.2em 0}.auth p{color:#9aa0af}
.auth input{width:100%;padding:13px;border-radius:10px;border:1px solid #2a2f3a;background:#161a21;
color:#fff;font-size:16px;margin:10px 0}
.auth button{width:100%;padding:13px;border:0;border-radius:10px;background:#e11d2a;color:#fff;
font-weight:800;font-size:16px}
.note{background:#0f2f1b;color:#8ff0b5;padding:12px;border-radius:10px;margin-top:12px;font-size:14px}
.foot{position:fixed;bottom:0;left:0;right:0;background:#15181f;border-top:1px solid #262a33;
padding:9px 16px;display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#8b90a0}
</style></head><body>"""

_SW_REG = ("<script>if('serviceWorker' in navigator){navigator.serviceWorker"
           ".register('/sw.js').catch(()=>{})}</script>")


def _login_page(sent=""):
    note = f'<div class="note">Check <b>{escape(sent)}</b> for your sign-in link. It works on this phone.</div>' if sent else ""
    return _HEAD + f"""<div class="auth">
<h1>🎬 FilmFund Radar</h1>
<p>{escape(config.APP_TAGLINE)}</p>
<form method="post" action="/login">
<input name="email" type="email" inputmode="email" autocomplete="email" required
 placeholder="your@email.com" value="{escape(sent)}">
<button>Email me a sign-in link</button></form>
{note}
<p style="font-size:12px;margin-top:18px">No password. We email you a magic link — tap it and you're in.
Add this app to your home screen for one-tap access.</p>
</div>{_SW_REG}</body></html>"""


_TABS = [("", "Live"), ("open", "Open"), ("d7", "≤7 days"), ("d30", "≤30 days"),
         ("undated", "No date"), ("closed", "Closed"), ("all", "All")]


def _card(r):
    dl = _days_left(r["deadline"])
    if dl is None:
        chip = '<span class="dl n">deadline: see call</span>'
    elif dl < 0:
        chip = '<span class="dl c">closed</span>'
    else:
        cls = "u" if dl <= 7 else ("s" if dl <= 21 else "o")
        chip = f'<span class="dl {cls}">{dl} days left</span>'
    region = config.REGION_LABELS.get(r["country"], (r["country"] or "").title() or "Global")
    org = f' &middot; {escape(r["org"][:50])}' if r["org"] else ""
    return (f'<div class="card"><h3>{escape(r["title"][:150])}</h3>'
            f'<div class="meta">{chip}</div>'
            f'<div class="meta">{escape(region)} &middot; {_fmt_inr(r["est_value_inr"])}'
            f' &middot; {escape((r["kind"] or "grant").replace("_"," "))}{org}</div>'
            f'<a class="go" href="{escape(r["url"])}" target="_blank" rel="noopener">View & apply →</a></div>')


def _feed_page(conn, email, dl, region):
    counts = db.bucket_counts(conn)
    rows = db.feed(conn, dl=dl, region=region, limit=200)
    tabs = "".join(
        f'<a class="tab{" on" if dl==v else ""}" href="/?dl={v}{("&region="+region) if region else ""}">'
        f'{escape(lbl)}<b>{counts.get(v,0)}</b></a>' for v, lbl in _TABS)
    regions = [("", "🌍 All")] + [(k, v) for k, v in config.REGION_LABELS.items() if k]
    rtabs = "".join(
        f'<a class="tab{" on" if region==k else ""}" href="/?dl={dl}{("&region="+k) if k else ""}">'
        f'{escape(v)}</a>' for k, v in regions)
    cards = "".join(_card(r) for r in rows) or '<div class="empty">No calls in this bucket yet.</div>'
    return _HEAD + f"""<div class="top"><div class="brand">🎬 FilmFund<span> Radar</span></div>
<div class="sub">Signed in as {escape(email)}</div></div>
<div class="wrap">
<div class="tabs">{tabs}</div>
<div class="tabs">{rtabs}</div>
{cards}
</div>
<div class="foot"><span>{len(rows)} opportunities</span><a href="/logout">Sign out</a></div>
{_SW_REG}</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    @property
    def cfg(self):
        return config

    def _conn(self):
        return db.connect(config.DB_PATH)

    def _cookie_email(self, conn):
        c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        tok = c[COOKIE].value if COOKIE in c else ""
        return auth.session_email(conn, tok)

    def _send(self, body, code=200, ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _static(self, name, ctype):
        f = STATIC / name
        if not f.exists():
            return self._send("not found", 404, "text/plain")
        self._send(f.read_bytes(), 200, ctype)

    def do_GET(self):
        u = up.urlsplit(self.path)
        qs = up.parse_qs(u.query)
        # static / pwa assets (no auth)
        if u.path == "/manifest.webmanifest":
            return self._static("manifest.webmanifest", "application/manifest+json")
        if u.path == "/sw.js":
            return self._static("sw.js", "application/javascript")
        if u.path == "/icon-192.png":
            return self._static("icon-192.png", "image/png")
        if u.path == "/icon-512.png":
            return self._static("icon-512.png", "image/png")
        if u.path == "/.well-known/assetlinks.json":
            return self._static("assetlinks.json", "application/json")
        if u.path == "/app.apk":
            return self._static("app.apk", "application/vnd.android.package-archive")
        conn = self._conn()
        try:
            if u.path == "/auth":
                tok = (qs.get("token") or [""])[0]
                sess = auth.consume_login(conn, tok)
                if not sess:
                    return self._send(_login_page(), 200)
                ck = http.cookies.SimpleCookie()
                ck[COOKIE] = sess
                ck[COOKIE]["path"] = "/"
                ck[COOKIE]["max-age"] = str(config.SESSION_TTL_DAYS * 86400)
                ck[COOKIE]["httponly"] = True
                ck[COOKIE]["samesite"] = "Lax"
                return self._send("", 303, headers={
                    "Location": "/", "Set-Cookie": ck[COOKIE].OutputString()})
            if u.path == "/logout":
                c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
                if COOKIE in c:
                    auth.logout(conn, c[COOKIE].value)
                return self._send("", 303, headers={"Location": "/login"})
            if u.path == "/login":
                return self._send(_login_page())

            email = self._cookie_email(conn)
            if u.path == "/api/opportunities":
                if not email:
                    return self._send(json.dumps({"error": "auth required"}), 401,
                                      "application/json")
                dl = (qs.get("dl") or [""])[0]
                region = (qs.get("region") or [""])[0]
                rows = [dict(r) for r in db.feed(conn, dl=dl, region=region, limit=200)]
                return self._send(json.dumps(rows, default=str), 200, "application/json")
            if u.path == "/":
                if not email:
                    return self._send(_login_page())
                dl = (qs.get("dl") or [""])[0]
                region = (qs.get("region") or [""])[0]
                return self._send(_feed_page(conn, email, dl, region))
            return self._send("not found", 404, "text/plain")
        finally:
            conn.close()

    def do_POST(self):
        u = up.urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        form = up.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        conn = self._conn()
        try:
            if u.path == "/login":
                email = (form.get("email") or [""])[0].strip().lower()
                try:
                    auth.request_login(conn, email)
                except ValueError:
                    return self._send(_login_page(), 200)
                return self._send(_login_page(sent=email))
            if u.path == "/prefs":
                email = self._cookie_email(conn)
                if not email:
                    return self._send("", 303, headers={"Location": "/login"})
                regions = (form.get("regions") or [""])[0]
                digest_on = 1 if (form.get("digest") or ["1"])[0] == "1" else 0
                db.set_prefs(conn, email, regions=regions, digest_on=digest_on)
                return self._send("", 303, headers={"Location": "/"})
            return self._send("not found", 404, "text/plain")
        finally:
            conn.close()


def serve(host=None, port=None):
    host = host or config.HTTP_HOST
    port = port or config.HTTP_PORT
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"FilmFund Radar serving on http://{host}:{port}  (base {config.BASE_URL})")
    httpd.serve_forever()
