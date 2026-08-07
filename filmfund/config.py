"""
FilmFund Radar — configuration.

A film-funding-only radar for a group of filmmakers. Watches the world for
grants, funds, fellowships and festival open calls that pay to MAKE films —
worldwide — scores them, keeps the real ones, tracks their deadlines, and mails
each filmmaker a personal digest.

Stdlib Python only. No pip install. Gemini is optional (free tier) and only
sharpens ranking; the radar works without it.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(ROOT / "filmfund.db")
SECRETS = Path(__file__).parent / "secrets.json"

APP_NAME = "FilmFund Radar"
APP_TAGLINE = "Funding for your next film — worldwide, on time."
# Public base URL is filled in once we host it; local demo uses this.
BASE_URL = os.environ.get("FILMFUND_BASE_URL", "http://127.0.0.1:8090")
HTTP_HOST = os.environ.get("FILMFUND_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("FILMFUND_PORT", "8090"))

# ---------------------------------------------------------------- email
EMAIL_FROM = "tejas4friends@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
# Sender name shown in the inbox
EMAIL_SENDER_NAME = "FilmFund Radar"

# ---------------------------------------------------------------- currency (display)
USD_INR = 88.0
EUR_INR = 96.0
GBP_INR = 112.0

# ---------------------------------------------------------------- film taxonomy
# Core groups: money available to MAKE a film. A kept item MUST hit one of these,
# so the feed never fills with generic movie-news.
FILM_GROUPS = {
    "film_funding": {
        "weight": 12,
        "keywords": [
            "film grant", "film fund", "film funding", "production grant", "development grant",
            "co-production fund", "coproduction fund", "documentary grant", "documentary fund",
            "screenwriting grant", "script development fund", "feature film fund", "short film grant",
            "filmmaker grant", "filmmaker fellowship", "film fellowship", "post-production grant",
            "post-production fund", "film residency", "completion fund", "cinema fund",
            "film bursary", "moving image commission", "film production support", "seed fund film",
            "talent lab", "screenwriting lab", "co-production market", "pitching forum",
            "development fund", "production fund", "finishing fund", "grant for filmmakers",
        ],
    },
    "film_project": {
        "weight": 10,
        "keywords": [
            "documentary film", "feature film", "short film", "web series", "docuseries",
            "narrative feature", "fiction film", "animated film", "animation feature", "screenplay",
            "independent film", "indie film", "filmmaking", "film production", "co-production",
            "documentary series", "film project", "non-fiction film", "experimental film",
        ],
    },
}
CORE_WEIGHT = 10

# Funding intent — a body offering money / an open application window.
GRANT_INTENT = {
    "keywords": [
        "grant", "grants", "fellowship", "bursary", "funding opportunity", "development fund",
        "production fund", "completion fund", "co-production fund", "seed fund",
        "call for entries", "call for films", "call for projects", "apply for funding",
        "grant programme", "grant program", "applications open", "submissions open",
        "now accepting applications", "deadline to apply", "open call", "funding scheme",
    ],
    "weight": 11,
}

# Kill obvious noise (box office, reviews, gossip) that slips past the feeds.
NEGATIVE_KEYWORDS = [
    "box office", "movie review", "film review", "trailer", "teaser", "casting couch",
    "red carpet", "premiere photos", "ott release date", "first look", "song launch",
    "crypto", "token", "nft",
]

# ---------------------------------------------------------------- geography
# gl -> region key, for country-wise grouping in the app.
GL_TO_REGION = {
    "IN": "india", "US": "usa", "GB": "uk", "CA": "canada", "AU": "australia",
    "AE": "gulf", "SG": "singapore", "DE": "europe", "FR": "europe", "ES": "europe",
    "IT": "europe", "NL": "europe", "IE": "uk", "NZ": "australia", "ZA": "africa",
}
REGION_LABELS = {
    "india": "India", "usa": "United States", "uk": "UK & Ireland", "canada": "Canada",
    "australia": "Australia / NZ", "europe": "Europe", "gulf": "Gulf", "singapore": "Singapore",
    "africa": "Africa", "": "Global / Unspecified",
}
GEO_BONUS = {"india": 6, "gulf": 2}

# ---------------------------------------------------------------- discovery
# CORE regions every query runs against (English-language film markets).
GNEWS_REGIONS_CORE = [("en", "IN"), ("en", "US"), ("en", "GB"), ("en", "CA"), ("en", "AU")]

# Broad, film-funding queries. Kept broad on purpose — narrow multi-AND queries
# return empty feeds on Google News; the scorer does the filtering.
GNEWS_QUERIES = [
    '"film grant" filmmakers',
    '"documentary fund" open call',
    '"film fund" applications open',
    '"co-production fund" film',
    '"development grant" filmmakers',
    '"short film" grant deadline',
    '"feature film" funding open call',
    '"filmmaker fellowship" applications',
    '"screenwriting" lab call for entries',
    '"post-production" fund film',
    'film festival "call for entries"',
    '"documentary" grant foundation',
    '"film production" grant',
    '"development fund" cinema',
    'independent film financing grant',
]

# Curated film-grant / open-call feeds (verified live). Broad film-news feeds
# are included but scored down to only their grant/fund/call items.
FILM_GRANT_FEEDS = {
    "nofilmschool": "https://nofilmschool.com/rss.xml",
    "filmmaker_mag": "https://filmmakermagazine.com/feed/",
    "ida_documentary": "https://www.documentary.org/rss.xml",
    "film_independent": "https://www.filmindependent.org/feed/",
    "sundance": "https://www.sundance.org/feed/",
    "fundsforngos": "https://www2.fundsforngos.org/feed/",
    "variety_film": "https://variety.com/v/film/feed/",
    "indiewire_film": "https://www.indiewire.com/c/film/feed/",
}

# ---------------------------------------------------------------- thresholds
MIN_SCORE_KEEP = 12       # store above this
FRESH_HOURS = 48
FRESHNESS_BONUS = 4
INTENT_MULTIPLIER = 1.6
MULTI_GROUP_BONUS = 4
# Freshness reject: an open call reported long ago is almost always closed.
MAX_AGE_DAYS = 90
REQUIRE_PUBLISH_DATE = False   # feeds/news often undated; keep, mark undated

# ---------------------------------------------------------------- runtime
SCAN_INTERVAL_MIN = 180
DIGEST_HOUR = 8           # local hour for the daily per-user digest
HTTP_TIMEOUT = 25
FETCH_WORKERS = 8
MAGIC_LINK_TTL_MIN = 30   # magic-link validity
SESSION_TTL_DAYS = 60

# LLM (optional)
LLM_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.0-flash"]
USE_LLM = True
MAX_TRIAGE_PER_SCAN = 40


def get_secret(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    try:
        return json.loads(SECRETS.read_text()).get(key, default)
    except Exception:  # noqa: BLE001
        return default
