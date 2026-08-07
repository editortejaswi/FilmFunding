"""
Free, deterministic film-funding scorer. An item is KEPT only if it hits a core
film group (so the feed is funding, not movie gossip). Grant intent + freshness +
geography adjust the rank; a stated deadline is a strong positive signal.
"""

import re

from . import config

_CACHE = {}


def _matcher(name, keywords):
    key = (name, len(keywords))
    if key not in _CACHE:
        phrases = [k for k in keywords if " " in k or len(k) > 12]
        tokens = [re.escape(k) for k in keywords if k not in phrases]
        token_re = re.compile(r"(?<![a-z0-9])(" + "|".join(tokens) + r")(?![a-z0-9])") if tokens else None
        _CACHE[key] = (tuple(phrases), token_re)
    return _CACHE[key]


def _hits(low, name, keywords):
    phrases, token_re = _matcher(name, keywords)
    if any(p in low for p in phrases):
        return True
    return bool(token_re and token_re.search(low))


def _classify(low) -> str:
    if "fellowship" in low:
        return "fellowship"
    if "call for" in low or "open call" in low or "submissions" in low or "entries" in low:
        return "open_call"
    if "fund" in low:
        return "fund"
    return "grant"


def score_item(item: dict) -> dict:
    low = (item.get("text") or f"{item.get('title','')} {item.get('summary','')}").lower()
    result = {"score": 0, "kept": False, "kind": "grant", "fit_note": ""}

    groups = []
    score = 0
    for name, grp in config.FILM_GROUPS.items():
        if _hits(low, f"g:{name}", grp["keywords"]):
            groups.append(name)
            score += grp["weight"]
    if not groups:
        return result  # not film-funding -> drop

    if len(groups) >= 2:
        score += config.MULTI_GROUP_BONUS

    intent = _hits(low, "intent", config.GRANT_INTENT["keywords"])
    if intent:
        score += config.GRANT_INTENT["weight"]
        score = int(score * config.INTENT_MULTIPLIER)

    neg = [k for k in config.NEGATIVE_KEYWORDS if k in low]
    if neg:
        score -= 8 * len(neg)

    geo = config.GEO_BONUS.get(item.get("country", ""), 0)
    score += geo

    from .fetch import hours_since
    if item.get("published") and hours_since(item["published"]) <= config.FRESH_HOURS:
        score += config.FRESHNESS_BONUS
    if item.get("deadline"):
        score += 5  # a concrete deadline means it's a real, actionable call

    result["score"] = max(0, int(score))
    result["kept"] = result["score"] >= config.MIN_SCORE_KEEP
    result["kind"] = _classify(low)
    result["fit_note"] = ("matches: " + ", ".join(groups)
                          + ("; grant intent" if intent else ""))
    return result
