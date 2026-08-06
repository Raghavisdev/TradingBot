"""
Module 6 — Narrative Heat Engine
----------------------------------
Measures how "hot" a narrative is right now — not just what
narrative a coin belongs to, but whether that narrative is TRENDING.

Strategy:
    Fetches CryptoPanic RSS and Google News headlines.
    Counts how many recent articles reference each narrative.
    Applies time-decay to emphasize very recent heat.

Returns:
    narrative_heat_score (float) : 0.0–100.0 score for the coin's primary narrative

MODE: PASSIVE COLLECTION ONLY.
"""

import time
import requests
import xml.etree.ElementTree as ET

from intelligence.narrative import NARRATIVE_KEYWORDS


# ======================================================
# NEWS FETCH (shared logic, lightweight)
# ======================================================

def _fetch_recent_headlines() -> list:
    """Fetches headlines from valid RSS feeds (CoinTelegraph, CoinDesk, CryptoSlate) for narrative heat calculation."""
    headlines = []
    now = time.time()
    valid_feeds = [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cryptoslate.com/feed/",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for feed_url in valid_feeds:
        try:
            res = requests.get(feed_url, headers=headers, timeout=6)
            if res.status_code != 200:
                continue

            # Validate XML structure (detect HTML redirects / Cloudflare pages)
            snippet = (res.text or "").strip()[:200].lower()
            if "<!doctype html" in snippet or "<html" in snippet:
                continue

            root = ET.fromstring(res.text)
            for item in root.iter("item"):
                title_el = item.find("title")
                pub_el   = item.find("pubDate")
                if title_el is None or not title_el.text:
                    continue

                headline = title_el.text.strip().lower()
                pub_text = pub_el.text.strip() if (pub_el is not None and pub_el.text) else ""

                minutes_old = 9999.0
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_text)
                    minutes_old = (now - dt.timestamp()) / 60.0
                except Exception:
                    pass

                headlines.append({
                    "text":        headline,
                    "minutes_old": minutes_old,
                })
        except Exception:
            continue

    return headlines


# ======================================================
# TIME DECAY (same schedule as news.py)
# ======================================================

def _time_decay(minutes_old: float) -> float:
    if minutes_old <= 15:
        return 1.00
    elif minutes_old <= 60:
        return 0.75
    elif minutes_old <= 180:
        return 0.50
    elif minutes_old <= 360:
        return 0.25
    elif minutes_old <= 1440:
        return 0.08
    else:
        return 0.01


# ======================================================
# NARRATIVE HEAT CALCULATOR
# ======================================================

def calculate_narrative_heat(primary_narrative: str) -> float:
    """
    Calculates the heat score for a given narrative based on recent news volume.
    Returns 0.0–100.0.
    """
    if not primary_narrative or primary_narrative == "Unknown":
        return 0.0

    keywords = NARRATIVE_KEYWORDS.get(primary_narrative, [])
    if not keywords:
        return 0.0

    headlines = _fetch_recent_headlines()
    if not headlines:
        return 0.0

    weighted_hits = 0.0
    for hl in headlines:
        decay = _time_decay(hl["minutes_old"])
        for kw in keywords:
            if kw in hl["text"]:
                weighted_hits += decay
                break  # count each headline once per narrative

    # Normalize: 10 weighted hits = full heat
    heat = min((weighted_hits / 10.0) * 100.0, 100.0)
    return round(heat, 2)


# ======================================================
# MAIN COLLECTOR
# ======================================================

def collect_narrative_heat(coin) -> dict:
    """
    Computes narrative heat score for the coin's primary narrative.
    Returns safe defaults on failure.
    """
    try:
        primary_narrative = getattr(coin, "_intelligence_primary_narrative", "Unknown")
        heat = calculate_narrative_heat(primary_narrative)
        return {"narrative_heat_score": heat}
    except Exception as e:
        symbol = getattr(coin, "symbol", "")
        print(f"[INTELLIGENCE] Narrative heat error for {symbol}: {e}")
        return {"narrative_heat_score": 0.0}
