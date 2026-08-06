"""
Module 1 — Social Intelligence Collector v2
---------------------------------------------
Collects social mentions and computes velocity + acceleration metrics.
Twitter/X DISABLED until TWITTER_BEARER_TOKEN is in .env.

Returns:
    social_mentions      (int)   : total raw mention count
    social_velocity      (float) : mentions per minute (rate)
    mentions_per_minute  (float) : same as social_velocity (explicit label)
    growth_rate          (float) : estimated % growth vs baseline (proxy)
    viral_acceleration   (float) : velocity change estimate (positive = accelerating)
    engagement_velocity  (float) : engagement score rate of change proxy
    engagement_score     (float) : 0-100 based on volume
    viral_score          (float) : composite (overridden by runner)

MODE: PASSIVE COLLECTION ONLY.
"""

import time
import requests
import os


# ======================================================
# TWITTER — auto-enabled when env var is set
# ======================================================

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_ENABLED = bool(TWITTER_BEARER_TOKEN)
TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


def _fetch_twitter_mentions(symbol: str, name: str) -> dict:
    """
    Queries Twitter v2 API for recent mentions.
    Returns {"count": int, "engagement": float}.
    Returns safe defaults if disabled or on error.
    """
    if not TWITTER_ENABLED:
        return {"count": 0, "engagement": 0.0}

    try:
        query = f"({symbol} OR {name}) (crypto OR sol OR solana OR token) lang:en -is:retweet"
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
        params = {
            "query": query,
            "max_results": 100,
            "tweet.fields": "created_at,public_metrics"
        }
        response = requests.get(TWITTER_SEARCH_URL, headers=headers, params=params, timeout=8)
        if response.status_code == 200:
            data = response.json()
            tweets = data.get("data", [])
            count = data.get("meta", {}).get("result_count", 0)
            # Sum engagement: likes + retweets
            total_engagement = sum(
                t.get("public_metrics", {}).get("like_count", 0) +
                t.get("public_metrics", {}).get("retweet_count", 0)
                for t in tweets
            )
            return {"count": count, "engagement": float(total_engagement)}
    except Exception:
        pass

    return {"count": 0, "engagement": 0.0}


def _fetch_duckduckgo_mentions(symbol: str, name: str) -> int:
    """Free-tier proxy: DuckDuckGo related topics count."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": f"{symbol} {name} crypto solana",
            "format": "json",
            "no_redirect": "1",
            "no_html": "1"
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return len(data.get("RelatedTopics", []))
    except Exception:
        pass
    return 0


# ======================================================
# ENGAGEMENT SCORE (logarithmic 0-100)
# ======================================================

def _engagement_score(total_mentions: int) -> float:
    if total_mentions == 0:   return 0.0
    if total_mentions < 5:    return 10.0
    if total_mentions < 20:   return 30.0
    if total_mentions < 50:   return 55.0
    if total_mentions < 100:  return 75.0
    if total_mentions < 300:  return 88.0
    return 95.0


# ======================================================
# MAIN COLLECTOR
# ======================================================

def collect_social(coin) -> dict:
    """
    Collects social intelligence for a coin.
    Always returns a valid dict with safe defaults.
    """
    symbol = getattr(coin, "symbol", "") or ""
    name   = getattr(coin, "name", symbol) or symbol

    default = {
        "social_mentions": 0, "social_velocity": 0.0,
        "mentions_per_minute": 0.0, "growth_rate": 0.0,
        "viral_acceleration": 0.0, "engagement_velocity": 0.0,
        "engagement_score": 0.0, "viral_score": 0.0,
    }

    try:
        start_time = time.time()

        # Twitter (if enabled)
        tw = _fetch_twitter_mentions(symbol, name)
        twitter_count = tw["count"]
        twitter_engagement = tw["engagement"]

        # Free-tier fallback — only used when X API is not available
        if TWITTER_ENABLED:
            ddg_count = 0
        else:
            ddg_count = _fetch_duckduckgo_mentions(symbol, name)

        total_mentions = twitter_count + ddg_count
        elapsed_seconds = max(time.time() - start_time, 0.1)
        elapsed_minutes = elapsed_seconds / 60.0

        # Velocity: raw mentions per minute of collection window
        mentions_per_minute = round(total_mentions / elapsed_minutes, 4)

        # Social velocity: normalize to 0-100 proxy
        social_velocity = round(min(mentions_per_minute * 5.0, 100.0), 2)

        # Growth rate: Twitter engagement as proxy for organic growth
        # Higher engagement relative to mentions = stronger growth signal
        if total_mentions > 0 and twitter_engagement > 0:
            growth_rate = round(min((twitter_engagement / total_mentions) * 10.0, 100.0), 2)
        else:
            growth_rate = 0.0

        # Engagement score (0-100 logarithmic)
        engagement = _engagement_score(total_mentions)

        # Viral acceleration: uses engagement growth vs velocity
        # A proxy — real acceleration needs prior snapshots (computed in dataset build)
        viral_acceleration = round(min((engagement * growth_rate) / 100.0, 100.0), 2)

        # Engagement velocity: change rate proxy
        engagement_velocity = round(mentions_per_minute * 2.0, 4)

        # Preliminary viral score (overridden by runner composite)
        viral_score = round(
            (engagement * 0.5) + (social_velocity * 0.3) + (growth_rate * 0.2), 2
        )

        return {
            "social_mentions":     total_mentions,
            "social_velocity":     social_velocity,
            "mentions_per_minute": mentions_per_minute,
            "growth_rate":         growth_rate,
            "viral_acceleration":  viral_acceleration,
            "engagement_velocity": engagement_velocity,
            "engagement_score":    engagement,
            "viral_score":         viral_score,
        }

    except Exception as e:
        print(f"[INTELLIGENCE] Social collection error for {symbol}: {e}")
        return default
