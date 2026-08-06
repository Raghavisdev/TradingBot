"""
Module 8 — Community Growth Collector v2
------------------------------------------
Tracks community size and activity.

v2 adds:
    message_rate   (float) : estimated messages per hour (proxy from available data)
    active_users   (int)   : estimated active users (proxy)
    community_growth_rate: percent change in members since last intel record

Twitter collection DISABLED until TWITTER_BEARER_TOKEN set.
Telegram async query runs safely only if Telethon is connected.

MODE: PASSIVE COLLECTION ONLY.
"""

import os
import requests

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_ENABLED = bool(TWITTER_BEARER_TOKEN)
TWITTER_USER_URL = "https://api.twitter.com/2/users/by/username/{username}"


def _fetch_twitter_followers(handle: str) -> dict:
    """Returns Twitter followers + following. Returns zeros if disabled/error."""
    if not TWITTER_ENABLED or not handle:
        return {"followers": 0, "following": 0}

    try:
        url = TWITTER_USER_URL.format(username=handle.lstrip("@"))
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
        params = {"user.fields": "public_metrics"}

        response = requests.get(url, headers=headers, params=params, timeout=6)
        if response.status_code == 200:
            data = response.json()
            metrics = data.get("data", {}).get("public_metrics", {})
            return {
                "followers": metrics.get("followers_count", 0),
                "following": metrics.get("following_count", 0),
            }
    except Exception:
        pass

    return {"followers": 0, "following": 0}


def _extract_twitter_handle(coin) -> str:
    """Extracts twitter handle from coin social fields if available."""
    return getattr(coin, "twitter", None) or ""


def _fetch_telegram_members_sync(coin) -> int:
    """
    Sync Telegram member fetch — returns 0 (safe fallback).
    Async Telegram calls conflict with background thread event loops.
    Full async Telegram integration is a future enhancement.
    """
    return 0


def _estimate_message_rate(telegram_members: int, twitter_followers: int) -> tuple:
    """
    Estimates message_rate and active_users from community size.
    Based on typical engagement ratios: ~2% of members are daily active.
    Returns (message_rate per hour, active_users estimate).
    """
    total_community = telegram_members + twitter_followers

    if total_community == 0:
        return 0.0, 0

    # Heuristic: 2% daily active users, ~0.5 messages per active user per hour
    active_ratio = 0.02
    messages_per_active_per_hour = 0.5

    active_users  = max(int(total_community * active_ratio), 0)
    message_rate  = round(active_users * messages_per_active_per_hour, 2)

    return message_rate, active_users


def collect_community(coin) -> dict:
    """
    Collects community growth intelligence.
    Returns safe defaults on failure.
    """
    default = {
        "telegram_members":     0,
        "twitter_followers":    0,
        "community_growth_rate": 0.0,
        "message_rate":         0.0,
        "active_users":         0,
    }

    try:
        twitter_handle   = _extract_twitter_handle(coin)
        tw               = _fetch_twitter_followers(twitter_handle)
        twitter_followers = tw["followers"]

        telegram_members = _fetch_telegram_members_sync(coin)

        message_rate, active_users = _estimate_message_rate(telegram_members, twitter_followers)

        # Growth rate: computed during dataset build from time-series delta.
        # Here we store 0.0 as baseline — the runner compares successive records.
        return {
            "telegram_members":      telegram_members,
            "twitter_followers":     twitter_followers,
            "community_growth_rate": 0.0,
            "message_rate":          message_rate,
            "active_users":          active_users,
        }

    except Exception as e:
        symbol = getattr(coin, "symbol", "")
        print(f"[INTELLIGENCE] Community collection error for {symbol}: {e}")
        return default
