"""
Film-funding scan: Google News film-grant queries (country-wise) + curated
film-grant feeds -> normalize -> score -> keep -> store.

Also a one-time seeder that imports the film-funding rows pifiradar already
discovered, so the app has real content on day one.
"""

import concurrent.futures as cf
import random
import sqlite3
import time
import urllib.parse as up

from . import config, db, fetch, normalize, score

_RELEVANT_FEED = (
    "grant", "fund", "funding", "fellowship", "bursary", "call for", "open call",
    "submission", "apply", "application", "deadline", "lab", "residency",
    "co-production", "coproduction", "pitch", "scheme", "financing", "award",
)

_VALUE_INR = {"fund": 2_000_000, "grant": 800_000, "fellowship": 600_000, "open_call": 500_000}


def _gnews_url(query, hl, gl):
    q = up.quote(query)
    return (f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}"
            f"&ceid={gl}:{hl}")


def _fetch_gnews():
    jobs = [(q, hl, gl) for q in config.GNEWS_QUERIES for hl, gl in config.GNEWS_REGIONS_CORE]
    out = []

    def one(job):
        q, hl, gl = job
        time.sleep(random.uniform(0, 0.3))
        items = fetch.parse_feed(fetch.fetch_url(_gnews_url(q, hl, gl), timeout=config.HTTP_TIMEOUT),
                                 source="gnews")
        region = config.GL_TO_REGION.get(gl, "")
        for it in items:
            it["country"] = region
        return items

    with cf.ThreadPoolExecutor(max_workers=config.FETCH_WORKERS) as ex:
        for got in ex.map(one, jobs):
            out.extend(got)
    print(f"  [gnews] {len(jobs)} fetches -> {len(out)} raw")
    return out


def _fetch_feeds():
    feeds = list(config.FILM_GRANT_FEEDS.items())
    out = []

    def one(item):
        name, url = item
        kept = []
        for it in fetch.fetch_feed(url, source=name, timeout=20):
            blob = f"{it.get('title','')} {it.get('summary','')}".lower()
            if any(k in blob for k in _RELEVANT_FEED):
                kept.append(it)
        return kept

    with cf.ThreadPoolExecutor(max_workers=min(config.FETCH_WORKERS, len(feeds))) as ex:
        for got in ex.map(one, feeds):
            out.extend(got)
    print(f"  [feeds] {len(feeds)} feeds -> {len(out)} relevant")
    return out


def scan(conn=None) -> int:
    conn = conn or db.init_db(config.DB_PATH)
    print("Fetching film-funding sources...")
    raw = _fetch_gnews() + _fetch_feeds()
    normed = normalize.dedup([normalize.normalize(r) for r in raw])
    print(f"  {len(normed)} unique after dedup")
    kept = new = 0
    for item in normed:
        sc = score.score_item(item)
        if not sc["kept"]:
            continue
        kept += 1
        if db.opp_exists(conn, item["fingerprint"]):
            continue
        item.update({
            "score": sc["score"], "kind": sc["kind"], "fit_note": sc["fit_note"],
            "est_value_inr": _VALUE_INR.get(sc["kind"], 800_000),
        })
        if db.insert_opp(conn, item):
            new += 1
    print(f"  {kept} passed the filter, {new} new")
    return new


def seed_from_pifiradar(conn=None, pifi_db="/home/dashcam70/pifiradar/radar.db") -> int:
    """Import the film-funding rows pifiradar already found (one-time bootstrap)."""
    conn = conn or db.init_db(config.DB_PATH)
    try:
        src = sqlite3.connect(pifi_db)
        src.row_factory = sqlite3.Row
    except Exception as e:  # noqa: BLE001
        print(f"  [seed] pifiradar db unavailable: {e}")
        return 0
    rows = src.execute(
        "SELECT title,summary,url,org,country,published,deadline,score,est_value_inr,"
        "official_url,official_email FROM opportunities "
        "WHERE stream='Film Grants & Funding' AND status NOT IN ('dropped','lost')"
    ).fetchall()
    n = 0
    for r in rows:
        item = normalize.normalize({
            "title": r["title"], "summary": r["summary"] or "", "url": r["official_url"] or r["url"],
            "org": r["org"] or "", "source": "pifiradar-seed",
            "country": (r["country"] or "").lower(), "published": r["published"] or "",
            "deadline": r["deadline"] or "",
        })
        sc = score.score_item(item)
        item.update({
            "score": max(sc["score"], r["score"] or 0), "kind": sc["kind"] or "grant",
            "fit_note": sc["fit_note"], "est_value_inr": r["est_value_inr"] or 800_000,
        })
        if not db.opp_exists(conn, item["fingerprint"]) and db.insert_opp(conn, item):
            n += 1
    src.close()
    print(f"  [seed] imported {n} film-funding opportunities from pifiradar")
    return n
