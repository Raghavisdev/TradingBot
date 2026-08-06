"""
Module 2 — News Intelligence Collector v2 (Production Fixed)
-----------------------------------------------------------
Collects recent crypto news from multiple valid RSS feeds:
  - CoinTelegraph RSS
  - CoinDesk RSS
  - CryptoSlate RSS
  - Google News RSS (coin-specific + crypto market)

Features:
- Detects & skips invalid/HTML feeds automatically
- Removes duplicate articles using URL + title similarity
- Stricter decay schedule (>24h = 0 weight)
- Tiered credibility scoring
- Non-blocking error handling (never crashes TradingBot)

MODE: PASSIVE COLLECTION ONLY.
"""

import time
import re
import logging
import requests
import difflib
from urllib.parse import urlparse, quote_plus
import xml.etree.ElementTree as ET

logger = logging.getLogger("Intelligence")

# Default headers with standard browser User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

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
# RSS FEED VALIDATION & PARSING
# ======================================================

RSS_SOURCES = [
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "type": "rss"
    },
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "type": "rss"
    },
    {
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "type": "rss"
    },
]


def _is_valid_xml(text: str) -> bool:
    """Checks if response text is valid XML rather than HTML page."""
    if not text or not text.strip():
        return False
    snippet = text.strip()[:200].lower()
    if "<!doctype html" in snippet or "<html" in snippet:
        return False
    try:
        ET.fromstring(text)
        return True
    except Exception:
        return False


def _fetch_rss_feed(feed_name: str, feed_url: str) -> tuple:
    """
    Fetches and parses a single RSS feed.
    Detects and automatically skips HTML / invalid XML responses.
    Returns (status_str, list_of_raw_article_dicts).
    """
    articles = []
    try:
        res = requests.get(feed_url, headers=HEADERS, timeout=8)
        status_code = res.status_code

        if status_code != 200:
            logger.info(f"[NEWS] {feed_name} | {status_code} Error | 0 articles")
            return f"HTTP {status_code}", []

        # Validate XML structure (detect HTML redirects/Cloudflare pages)
        if not _is_valid_xml(res.text):
            logger.info(f"[NEWS] {feed_name} | 200 OK (HTML/Invalid XML Skipped) | 0 articles")
            return "200 Invalid XML", []

        root = ET.fromstring(res.text)
        now = time.time()

        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            pub_el   = item.find("pubDate")
            if title_el is None or not title_el.text:
                continue

            headline = title_el.text.strip()
            link     = link_el.text.strip() if (link_el is not None and link_el.text) else ""
            pub_text = pub_el.text.strip()  if (pub_el  is not None and pub_el.text)  else ""

            minutes_old = 9999.0
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_text)
                minutes_old = (now - dt.timestamp()) / 60.0
            except Exception:
                pass

            decay = _time_decay(minutes_old)
            if decay == 0.0:
                continue  # Skip stale articles (>24h)

            articles.append({
                "headline":    headline,
                "source_url":  link,
                "source":      _source_domain(link) or feed_name,
                "feed_name":   feed_name,
                "minutes_old": round(minutes_old, 1),
                "sentiment":   _quick_sentiment(headline),
                "credibility": _credibility(link if link else feed_url),
                "decay":       decay,
                "freshness":   _freshness_score(minutes_old),
            })

        logger.info(f"[NEWS] {feed_name} | 200 OK | {len(articles)} articles retrieved")
        return "200 OK", articles

    except Exception as e:
        logger.info(f"[NEWS] {feed_name} | Failed ({e}) | 0 articles")
        return f"Error: {e}", []


def _fetch_google_news_rss(symbol: str, name: str) -> tuple:
    """
    Queries Google News RSS for coin-specific headlines.
    Returns (status_str, list_of_article_dicts).
    """
    articles = []
    feed_name = "Google News"
    try:
        query_str = f'"{symbol}" crypto' if symbol else f'"{name}" crypto'
        url = f"https://news.google.com/rss/search?q={quote_plus(query_str)}&hl=en-US&gl=US&ceid=US:en"

        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code != 200 or not _is_valid_xml(res.text):
            logger.info(f"[NEWS] {feed_name} | HTTP {res.status_code} / Invalid | 0 articles")
            return f"HTTP {res.status_code}", []

        root = ET.fromstring(res.text)
        now = time.time()

        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            pub_el   = item.find("pubDate")
            if title_el is None or not title_el.text:
                continue

            headline = title_el.text.strip()
            link     = link_el.text.strip() if (link_el is not None and link_el.text) else ""
            pub_text = pub_el.text.strip()  if (pub_el  is not None and pub_el.text)  else ""

            minutes_old = 9999.0
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_text)
                minutes_old = (now - dt.timestamp()) / 60.0
            except Exception:
                pass

            decay = _time_decay(minutes_old)
            if decay == 0.0:
                continue

            articles.append({
                "headline":    headline,
                "source_url":  link,
                "source":      _source_domain(link) or feed_name,
                "feed_name":   feed_name,
                "minutes_old": round(minutes_old, 1),
                "sentiment":   _quick_sentiment(headline),
                "credibility": _credibility(link if link else url),
                "decay":       decay,
                "freshness":   _freshness_score(minutes_old),
            })

        logger.info(f"[NEWS] {feed_name} ({query_str}) | 200 OK | {len(articles)} articles retrieved")
        return "200 OK", articles

    except Exception as e:
        logger.info(f"[NEWS] {feed_name} | Failed ({e}) | 0 articles")
        return f"Error: {e}", []


# ======================================================
# DEDUPLICATION (URL + Title Similarity)
# ======================================================

def _clean_headline(title: str) -> str:
    """Normalizes title for similarity comparison."""
    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def _clean_url(url: str) -> str:
    """Strips query string tracking params from URL."""
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}".rstrip("/").lower()
    except Exception:
        return url.lower()


def _deduplicate_articles(articles: list) -> list:
    """
    Removes duplicate articles using:
    1. Clean URL exact match
    2. Title SequenceMatcher similarity > 0.85
    """
    seen_urls = set()
    unique_articles = []

    for art in articles:
        url_clean = _clean_url(art.get("source_url", ""))
        title_clean = _clean_headline(art.get("headline", ""))

        if not title_clean:
            continue

        if url_clean and url_clean in seen_urls:
            continue

        # Check title similarity against already kept articles
        is_dup = False
        for kept in unique_articles:
            kept_title = _clean_headline(kept.get("headline", ""))
            if kept_title == title_clean:
                is_dup = True
                break
            ratio = difflib.SequenceMatcher(None, title_clean, kept_title).ratio()
            if ratio > 0.85:
                is_dup = True
                break

        if not is_dup:
            if url_clean:
                seen_urls.add(url_clean)
            unique_articles.append(art)

    return unique_articles


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
    """
    Main entry point for News Collection.
    Collects from all valid RSS sources, deduplicates, and aggregates score.
    Never raises an unhandled exception.
    """
    symbol = getattr(coin, "symbol", "") or ""
    name   = getattr(coin, "name", symbol) or symbol

    default = {
        "news_score": 0.0, "news_headline": "",
        "news_sentiment": "neutral", "news_minutes_old": 0.0,
        "news_credibility": 0.0, "news_source": "",
        "freshness_score": 0.0,
    }

    try:
        all_articles = []
        symbol_upper = symbol.upper()

        # 1. Fetch from static RSS feeds (CoinTelegraph, CoinDesk, CryptoSlate)
        for feed in RSS_SOURCES:
            _, feed_articles = _fetch_rss_feed(feed["name"], feed["url"])
            all_articles.extend(feed_articles)

        # 2. Fetch from Google News RSS
        _, gn_articles = _fetch_google_news_rss(symbol, name)
        all_articles.extend(gn_articles)

        # 3. Filter articles matching coin symbol/name if specific match exists
        coin_specific = [
            a for a in all_articles
            if (symbol_upper and symbol_upper in a["headline"].upper()) or
               (name and name.lower() in a["headline"].lower())
        ]

        target_pool = coin_specific if coin_specific else all_articles

        # 4. Remove duplicates
        unique_articles = _deduplicate_articles(target_pool)

        # 5. Aggregate final news score
        return _aggregate(unique_articles)

    except Exception as e:
        logger.warning(f"[NEWS] Collection error for {symbol}: {e}")
        return default
