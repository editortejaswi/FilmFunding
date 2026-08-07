"""
Clean raw items, dedup, and extract a stated application deadline from text
(deterministic, stdlib-only — the same trigger-gated approach proven in pifiradar).
"""

import calendar
import hashlib
import re
import urllib.parse as up
from datetime import date

_WS = re.compile(r"\s+")
_PUB_SUFFIX = re.compile(r"\s+[-–—|]\s+[^-–—|]{2,45}$")
_TRACK = re.compile(r"^(utm_|fbclid|gclid|mc_|ref|amp|oc$|ved$|usg$)", re.I)


def clean_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = up.urlsplit(url.strip())
        q = [(k, v) for k, v in up.parse_qsl(p.query) if not _TRACK.match(k)]
        return up.urlunsplit((p.scheme or "https", p.netloc, p.path,
                              up.urlencode(q), ""))
    except Exception:  # noqa: BLE001
        return url


def clean_title(title: str) -> str:
    t = _WS.sub(" ", (title or "").strip())
    return _PUB_SUFFIX.sub("", t).strip()


def fingerprint(item: dict) -> str:
    url = clean_url(item.get("url", ""))
    if url:
        return "u:" + hashlib.sha1(url.encode()).hexdigest()[:16]
    sig = re.sub(r"[^a-z0-9 ]+", "", (item.get("title", "") or "").lower())
    return "t:" + hashlib.sha1(sig.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- deadline
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_MONTHS["sept"] = 9

_DL_TRIGGER = re.compile(
    r"(deadline|apply by|applications?\s+(?:close|closing|due|accepted until)|closing date|"
    r"last date|submit by|submissions?\s+close|submission deadline|entries?\s+close|"
    r"closes on|closes|due by|due on|no later than|final date|last day to apply)", re.I)
_D_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_D_DMY = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")
_D_DMON = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?(?:,?\s+(\d{4}))?", re.I)
_D_MOND = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", re.I)


def _resolve_year(month, day, today):
    for y in (today.year, today.year + 1):
        try:
            if (date(y, month, day) - today).days >= -30:
                return y
        except ValueError:
            return None
    return today.year


def _iso(y, m, d):
    try:
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return ""


def extract_deadline(text: str, today: date = None) -> str:
    if not text:
        return ""
    today = today or date.today()
    m = _DL_TRIGGER.search(text)
    if not m:
        return ""
    win = text[m.start():m.start() + 90]
    mi = _D_ISO.search(win)
    if mi:
        return _iso(int(mi.group(1)), int(mi.group(2)), int(mi.group(3)))
    md = _D_DMON.search(win)
    if md and md.group(2).lower() in _MONTHS:
        mo, day = _MONTHS[md.group(2).lower()], int(md.group(1))
        yr = int(md.group(3)) if md.group(3) else _resolve_year(mo, day, today)
        return _iso(yr, mo, day) if yr else ""
    mm = _D_MOND.search(win)
    if mm and mm.group(1).lower() in _MONTHS:
        mo, day = _MONTHS[mm.group(1).lower()], int(mm.group(2))
        yr = int(mm.group(3)) if mm.group(3) else _resolve_year(mo, day, today)
        return _iso(yr, mo, day) if yr else ""
    mn = _D_DMY.search(win)
    if mn:
        a, b, c = int(mn.group(1)), int(mn.group(2)), int(mn.group(3))
        c += 2000 if c < 100 else 0
        day, mo = a, b
        if mo > 12 and day <= 12:
            day, mo = b, a
        return _iso(c, mo, day)
    return ""


def normalize(item: dict) -> dict:
    title = clean_title(item.get("title", ""))
    summary = (item.get("summary") or "").strip()
    url = clean_url(item.get("url", "")) or item.get("url", "")
    return {
        "title": title,
        "summary": summary,
        "url": url,
        "org": (item.get("org") or "").strip(),
        "source": item.get("source", "unknown"),
        "country": item.get("country", ""),
        "published": item.get("published", ""),
        "deadline": item.get("deadline") or extract_deadline(f"{title}. {summary}"),
        "fingerprint": fingerprint({"title": title, "url": url}),
        "text": f"{title}. {summary}",
    }


def dedup(items: list) -> list:
    best = {}
    for it in items:
        fp = it["fingerprint"]
        cur = best.get(fp)
        if not cur or len(it.get("summary", "")) > len(cur.get("summary", "")):
            best[fp] = it
    return list(best.values())
