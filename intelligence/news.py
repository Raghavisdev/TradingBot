"""
Module 2 — News Intelligence Collector v2
-------------------------------------------
Collects recent news from CryptoPanic RSS and Google News RSS.

v2 improvements:
- Stricter decay schedule (>24h = 0 weight)
- Expanded credibility map with tiered sources
- Stores: news_source, freshness_score per article
- Aggregate: best freshness, top source, weighted news_score

Time decay schedule:
    0-30 min   → 1.00 (100%)
    30-60 min  → 0.90  (90%)
    1-3 hr     → 0.75  (75%)
    3-6 hr     → 0.50  (50%)
    6-12 hr    → 0.25  (25%)
    12-24 hr   → 0.10  (10%)
    > 24 hr    → 0.00  (ignored)

MODE: PASSIVE COLLECTION ONLY.
"""

import time
import requests
import xml.etree.ElementTree as ET


# ======================================================
# TIME DECAY v2
# ======================================================

def _time_decay(minutes_old: float) -> float:
    if minutes_old <= 30:    return 1.00
    if minutes_old <= 60:    return 0.90
    if minutes_old <= 180:   return 0.75
    if minutes_old <= 360:   return 0.50
    if minutes_old <= 720:   return 0.25
    if minutes_old <= 1440:  return 0.10
    return 0.00  # > 24 hours — ignored


def _freshness_score(minutes_old: float) -> float:
    """Returns freshness as 0-100 score (inverse of decay * 100)."""
    return round(_time_decay(minutes_old) * 100.0, 1)


# ======================================================
# CREDIBILITY MAP (tiered)
# ======================================================

CREDIBILITY_MAP = {
    # Tier 1 — Major financial/crypto media (85-95)
    "reuters.com":          95,
    "bloomberg.com":        93,
    "wsj.com":              92,
    "ft.com":               91,
    "coindesk.com":         88,
    "cointelegraph.com":    86,
    "theblock.co":          87,
    "decrypt.co":           84,

    # Tier 2 — Established crypto outlets (70-84)
    "cryptobriefing.com":   78,
    "beincrypto.com":       74,
    "cryptopanic.com":      72,
    "cryptoslate.com":      76,
    "u.today":              71,
    "coinjournal.net":      72,
    "newsbtc.com":          68,
    "bitcoinist.com":       67,

    # Tier 3 — Community and aggregators (50-66)
    "ambcrypto.com":        62,
    "coingape.com":         60,
    "zycrypto.com":         58,
    "nulltx.com":           55,
    "dailycoin.com":        54,
    "cryptodaily.co.uk":    52,
}

DEFAULT_CREDIBILITY = 45.0   # Unknown source


def _credibility(source_url: str) -> float:
    for domain, score in CREDIBILITY_MAP.items():
        if domain in source_url:
            return float(score)
    return DEFAULT_CREDIBILITY


def _source_domain(url: str) -> str:
    """Extracts domain from URL for storage."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or url[:60]
    except Exception:
        return ""


# ======================================================
# BASIC SENTIMENT KEYWORD SCORER
# ======================================================

POSITIVE_WORDS = {
    "surge", "rally", "bull", "pump", "moon", "gain", "rise", "launch",
    "partnership", "breakthrough", "adoption", "listed", "integration",
    "record", "milestone", "upgrade", "mainnet",
}
NEGATIVE_WORDS = {
    "dump", "crash", "bear", "rug", "scam", "hack", "ban", "fraud",
    "collapse", "plunge", "sell", "warning", "risk", "lawsuit", "concern",
    "exploit", "vulnerability", "liquidated",
}


def _quick_sentiment(text: str) -> str:
    lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in lower)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


# ======================================================
# CRYPTOPANIC RSS
# ======================================================

CRYPTOPANIC_RSS = "https://cryptopanic.com/news/rss/"


def _fetch_cryptopanic(symbol: str) -> list:
    articles = []
    try:
        response = requests.get(CRYPTOPANIC_RSS, timeout=8)
        if response.status_code != 200:
            return articles

        root = ET.fromstring(response.text)
        now = time.time()

        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            pub_el   = item.find("pubDate")
            if title_el is None:
                continue

            headline  = title_el.text or ""
            link      = link_el.text if link_el is not None else ""
            pub_text  = pub_el.text  if pub_el  is not None else ""

            if symbol.upper() not in headline.upper():
                continue

            minutes_old = 9999.0
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_text)
                minutes_old = (now - dt.timestamp()) / 60.0
            except Exception:
                pass

            decay = _time_decay(minutes_old)
            if decay == 0.0:
                continue  # Skip stale articles entirely

            articles.append({
                "headline":    headline,
                "source_url":  link,
                "source":      _source_domain(link),
                "minutes_old": round(minutes_old, 1),
                "sentiment":   _quick_sentiment(headline),
                "credibility": _credibility(link),
                "decay":       decay,
                "freshness":   _freshness_score(minutes_old),
            })

    except Exception:
        pass

    return articles


# ======================================================
# GOOGLE NEWS RSS
# ======================================================

def _fetch_google_news(symbol: str, name: str) -> list:
    articles = []
    try:
        query_enc = f"{symbol} {name} crypto".replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query_enc}&hl=en-US&gl=US&ceid=US:en"

        response = requests.get(url, timeout=8)
        if response.status_code != 200:
            return articles

        root = ET.fromstring(response.text)
        now = time.time()

        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            pub_el   = item.find("pubDate")
            if title_el is None:
                continue

            headline  = title_el.text or ""
            link      = link_el.text if link_el is not None else ""
            pub_text  = pub_el.text  if pub_el  is not None else ""

            minutes_old = 9999.0
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_text)
                minutes_old = (now - dt.timestamp()) / 60.0
            except Exception:
                pass

            decay = _time_decay(minutes_old)
            if decay == 0.0:
                continue  # Skip stale articles entirely

            articles.append({
                "headline":    headline,
                "source_url":  link,
                "source":      _source_domain(link),
                "minutes_old": round(minutes_old, 1),
                "sentiment":   _quick_sentiment(headline),
                "credibility": _credibility(link),
                "decay":       decay,
                "freshness":   _freshness_score(minutes_old),
            })

    except Exception:
        pass

    return articles


# ======================================================
# AGGREGATE
# ======================================================

def _aggregate(articles: list) -> dict:
    if not articles:
        return {
            "news_score": 0.0, "news_headline": "",
            "news_sentiment": "neutral", "news_minutes_old": 0.0,
            "news_credibility": 0.0, "news_source": "",
            "freshness_score": 0.0,
        }

    # Sort by freshness descending
    articles.sort(key=lambda a: a["decay"], reverse=True)

    total_weight = 0.0
    weighted_score = 0.0
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}

    for art in articles:
        weight = art["decay"] * (art["credibility"] / 100.0)
        weighted_score += weight * art["credibility"]
        total_weight += weight
        sentiments[art["sentiment"]] = sentiments.get(art["sentiment"], 0) + 1

    news_score = round((weighted_score / total_weight) if total_weight > 0 else 0.0, 2)
    dominant_sentiment = max(sentiments, key=sentiments.get)
    top = articles[0]  # freshest, best article

    return {
        "news_score":      min(news_score, 100.0),
        "news_headline":   top["headline"][:200],
        "news_sentiment":  dominant_sentiment,
        "news_minutes_old": top["minutes_old"],
        "news_credibility": top["credibility"],
        "news_source":     top["source"],
        "freshness_score": top["freshness"],
    }


# ======================================================
# MAIN COLLECTOR
# ======================================================

def collect_news(coin) -> dict:
    symbol = getattr(coin, "symbol", "") or ""
    name   = getattr(coin, "name", symbol) or symbol

    default = {
        "news_score": 0.0, "news_headline": "",
        "news_sentiment": "neutral", "news_minutes_old": 0.0,
        "news_credibility": 0.0, "news_source": "",
        "freshness_score": 0.0,
    }

    try:
        articles = []
        articles.extend(_fetch_cryptopanic(symbol))
        articles.extend(_fetch_google_news(symbol, name))
        return _aggregate(articles)
    except Exception as e:
        print(f"[INTELLIGENCE] News collection error for {symbol}: {e}")
        return default
