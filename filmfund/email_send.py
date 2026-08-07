"""
Email delivery via Gmail SMTP (stdlib smtplib). Used for magic-link sign-in and
the per-user funding digest.
"""

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from . import config


def send_email(subject: str, html: str, to: str, text_fallback: str = "") -> bool:
    pw = config.get_secret("GMAIL_APP_PASSWORD")
    if not pw:
        print("  [email] GMAIL_APP_PASSWORD missing — cannot send.")
        return False
    to = (to or "").strip()
    if "@" not in to:
        print(f"  [email] invalid recipient {to!r}")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((config.EMAIL_SENDER_NAME, config.EMAIL_FROM))
    msg["To"] = to
    msg.set_content(text_fallback or "Open this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=45) as s:
            s.starttls()
            s.login(config.EMAIL_FROM, pw)
            s.send_message(msg)
        print(f"  [email] sent '{subject[:40]}' -> {to}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [email] failed: {type(e).__name__}: {e}")
        return False


_SHELL = """\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:620px;margin:0 auto;
padding:20px;color:#1a1a1a">
  <div style="font-size:20px;font-weight:800;color:#e11d2a">🎬 FilmFund Radar</div>
  <div style="color:#666;font-size:13px;margin-bottom:18px">{tagline}</div>
  {body}
  <hr style="border:none;border-top:1px solid #eee;margin:22px 0">
  <div style="color:#999;font-size:12px">You're receiving this because you signed up for FilmFund
  Radar. Open the app: <a href="{base}">{base}</a></div>
</div>"""


def shell(body: str) -> str:
    return _SHELL.format(tagline=config.APP_TAGLINE, body=body, base=config.BASE_URL)


def send_magic_link(to: str, link: str) -> bool:
    body = (f'<p style="font-size:15px">Tap the button to sign in to FilmFund Radar. '
            f'This link is valid for {config.MAGIC_LINK_TTL_MIN} minutes.</p>'
            f'<p><a href="{link}" style="display:inline-block;background:#e11d2a;color:#fff;'
            f'text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700">'
            f'Sign in to FilmFund Radar</a></p>'
            f'<p style="color:#888;font-size:12px">Or paste this link:<br>{link}</p>')
    return send_email("Your FilmFund Radar sign-in link", shell(body), to,
                      text_fallback=f"Sign in: {link}")
