"""
Module 7 — KOL Engine (Key Opinion Leaders)
---------------------------------------------
Tracks whether influential crypto accounts have mentioned the coin.

Twitter/X collection is DISABLED until TWITTER_BEARER_TOKEN is set.

When enabled, uses a curated KOL list and measures:
    - How many KOLs mentioned the coin
    - Combined influence weight
    - Engagement (likes + retweets on KOL posts)

Returns:
    kol_mentions (int)   : number of KOL accounts that mentioned the coin
    kol_score    (float) : 0.0–100.0 weighted influence score

MODE: PASSIVE COLLECTION ONLY.
"""

import os
import requests


# ======================================================
# TWITTER CONFIG
# ======================================================

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_ENABLED = bool(TWITTER_BEARER_TOKEN)

TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


# ======================================================
# CURATED KOL LIST
# (Twitter user IDs — public figures in crypto)
# Weights reflect approximate influence tiers
# ======================================================

KOL_LIST = [
    # High-tier KOLs (weight 10)
    {"handle": "elonmusk",       "weight": 10},
    {"handle": "cz_binance",     "weight": 10},
    {"handle": "VitalikButerin", "weight": 10},
    {"handle": "SBF_FTX",        "weight":  5},

    # Mid-tier KOLs (weight 7)
    {"handle": "cobie",          "weight": 7},
    {"handle": "lookonchain",    "weight": 7},
    {"handle": "gainzy222",      "weight": 7},
    {"handle": "DegenSpartan",   "weight": 7},
    {"handle": "inversebrah",    "weight": 7},

    # Community KOLs (weight 4)
    {"handle": "nansen_alpha",   "weight": 4},
    {"handle": "blknoiz06",      "weight": 4},
    {"handle": "GemHunterSol",   "weight": 4},
    {"handle": "solanafm",       "weight": 4},
]

MAX_WEIGHT = sum(k["weight"] for k in KOL_LIST)


# ======================================================
# TWITTER KOL SEARCH
# ======================================================

def _search_kol_mentions(symbol: str, name: str) -> dict:
    """
    Searches Twitter for mentions of the coin by KOL accounts.
    Returns {kol_mentions: int, kol_score: float}.
    Disabled safely if no TWITTER_BEARER_TOKEN.
    """
    if not TWITTER_ENABLED:
        return {"kol_mentions": 0, "kol_score": 0.0}

    handles = " OR ".join(
        f"from:{k['handle']}" for k in KOL_LIST
    )
    query = f"({symbol} OR {name}) ({handles}) lang:en -is:retweet"

    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
    params = {
        "query": query,
        "max_results": 100,
        "tweet.fields": "author_id,public_metrics",
        "expansions": "author_id",
        "user.fields": "username"
    }

    try:
        response = requests.get(
            TWITTER_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=8
        )
        if response.status_code != 200:
            return {"kol_mentions": 0, "kol_score": 0.0}

        data = response.json()
        tweets = data.get("data", [])
        users = {
            u["id"]: u["username"].lower()
            for u in data.get("includes", {}).get("users", [])
        }

        total_weight = 0.0
        kol_mention_count = 0

        for tweet in tweets:
            author_id = tweet.get("author_id", "")
            username = users.get(author_id, "").lower()

            for kol in KOL_LIST:
                if kol["handle"].lower() == username:
                    total_weight += kol["weight"]
                    kol_mention_count += 1
                    break

        kol_score = round((total_weight / MAX_WEIGHT) * 100.0, 2) if MAX_WEIGHT > 0 else 0.0
        kol_score = min(kol_score, 100.0)

        return {"kol_mentions": kol_mention_count, "kol_score": kol_score}

    except Exception:
        return {"kol_mentions": 0, "kol_score": 0.0}


# ======================================================
# MAIN COLLECTOR
# ======================================================

def collect_kol(coin) -> dict:
    """
    Collects KOL mention intelligence for a coin.
    Returns safe defaults on failure.
    """
    symbol = getattr(coin, "symbol", "") or ""
    name = getattr(coin, "name", symbol) or symbol

    try:
        return _search_kol_mentions(symbol, name)
    except Exception as e:
        print(f"[INTELLIGENCE] KOL collection error for {symbol}: {e}")
        return {"kol_mentions": 0, "kol_score": 0.0}
