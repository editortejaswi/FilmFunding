"""
HTTP + RSS/Atom plumbing. Stdlib only. Failures return empty — never raise.
"""

import gzip
import io
import socket
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
_CTX = ssl.create_default_context()


def fetch_url(url: str, timeout: int = 25, retries: int = 2) -> str:
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", "replace")
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, Exception):  # noqa: BLE001
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
    return ""


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buf = []

    def handle_data(self, d):
        self.buf.append(d)


def strip_html(s: str, limit: int = 900) -> str:
    if not s:
        return ""
    p = _Stripper()
    try:
        p.feed(s)
    except Exception:  # noqa: BLE001
        return s[:limit]
    return " ".join("".join(p.buf).split())[:limit]


def to_iso(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt:
            return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:len(fmt) + 4], fmt).replace(
                tzinfo=timezone.utc).isoformat(timespec="seconds")
        except Exception:  # noqa: BLE001
            continue
    return ""


def hours_since(iso: str) -> float:
    if not iso:
        return 1e6
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return 1e6


def _tag(el):
    return el.tag.split("}")[-1]


def parse_feed(xml_text: str, source: str) -> list:
    """Parse RSS 2.0 or Atom into raw item dicts. Returns [] on junk."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text.encode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return []
    items = []
    for el in root.iter():
        if _tag(el) not in ("item", "entry"):
            continue
        d = {"title": "", "url": "", "summary": "", "published": "", "source": source}
        for c in el:
            t = _tag(c)
            if t == "title":
                d["title"] = (c.text or "").strip()
            elif t == "link":
                href = c.get("href")
                d["url"] = (href or c.text or "").strip()
            elif t in ("description", "summary", "content", "encoded"):
                d["summary"] = strip_html(c.text or "", 600)
            elif t in ("pubDate", "published", "updated", "date"):
                d["published"] = to_iso(c.text or "")
        if d["title"] and d["url"]:
            items.append(d)
    return items


def fetch_feed(url: str, source: str, timeout: int = 25) -> list:
    return parse_feed(fetch_url(url, timeout=timeout), source)
