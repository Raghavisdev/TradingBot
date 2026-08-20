import time
import threading

import requests

from config import DEXSCREENER_TIMEOUT


# ============================================================
# DEXSCREENER REQUEST CONTROL
# ============================================================

# Minimum time between outgoing DexScreener requests.
# This protects the API when many trackers are active.
MIN_REQUEST_INTERVAL = 1.0

# Cache lifetime. A cached response is considered fresh enough
# for another object requesting the same contract during this
# short window.
CACHE_TTL = 2.0

# Maximum backoff after HTTP 429.
MAX_BACKOFF = 60.0

_request_lock = threading.Lock()
_last_request_time = 0.0

_cache_lock = threading.Lock()
_response_cache = {}

_backoff_until = 0.0
_consecutive_429 = 0


def _wait_for_request_slot():
    """
    Globally serialize DexScreener requests and enforce a minimum
    spacing between requests.
    """

    global _last_request_time

    with _request_lock:

        now = time.time()

        wait = (
            MIN_REQUEST_INTERVAL
            - (now - _last_request_time)
        )

        if wait > 0:
            time.sleep(wait)

        _last_request_time = time.time()


def _get_cached(contract):
    """
    Return a recent cached response for this contract, if present.
    """

    now = time.time()

    with _cache_lock:

        item = _response_cache.get(contract)

        if not item:
            return None

        timestamp, data = item

        if now - timestamp > CACHE_TTL:
            del _response_cache[contract]
            return None

        return data


def _set_cached(contract, data):

    with _cache_lock:
        _response_cache[contract] = (
            time.time(),
            data,
        )


def _fetch_dexscreener(contract):

    global _backoff_until
    global _consecutive_429

    if not contract:
        return None

    # --------------------------------------------------------
    # Recent cache
    # --------------------------------------------------------

    cached = _get_cached(contract)

    if cached is not None:
        return cached

    # --------------------------------------------------------
    # Respect current 429 backoff
    # --------------------------------------------------------

    now = time.time()

    if now < _backoff_until:

        remaining = _backoff_until - now

        print(
            f"[DEX RATE LIMIT] Backoff active "
            f"({remaining:.1f}s remaining) "
            f"for {contract}"
        )

        return None

    # --------------------------------------------------------
    # Request
    # --------------------------------------------------------

    _wait_for_request_slot()

    url = (
        "https://api.dexscreener.com/latest/dex/tokens/"
        + str(contract)
    )

    try:

        response = requests.get(
            url,
            timeout=DEXSCREENER_TIMEOUT
        )

        # ----------------------------------------------------
        # Rate limited
        # ----------------------------------------------------

        if response.status_code == 429:

            _consecutive_429 += 1

            retry_after = response.headers.get(
                "Retry-After"
            )

            try:
                retry_seconds = float(retry_after)
            except (TypeError, ValueError):
                retry_seconds = 0.0

            exponential = min(
                MAX_BACKOFF,
                2.0 ** min(
                    _consecutive_429,
                    6
                )
            )

            backoff = max(
                retry_seconds,
                exponential
            )

            _backoff_until = time.time() + backoff

            print(
                f"[DEX RATE LIMIT] HTTP 429 | "
                f"backoff={backoff:.1f}s | "
                f"contract={contract}"
            )

            return None

        # ----------------------------------------------------
        # Other HTTP errors
        # ----------------------------------------------------

        if response.status_code != 200:

            print(
                f"[API ERROR] DexScreener HTTP "
                f"{response.status_code} for {contract}"
            )

            return None

        data = response.json()

        # Successful request resets rate-limit state.
        _consecutive_429 = 0
        _backoff_until = 0.0

        _set_cached(contract, data)

        return data

    except Exception as e:

        print(
            f"[API ERROR] DexScreener exception "
            f"for {contract}: {e}"
        )

        return None


def update_market(obj):
    """
    Update either a Coin or Position object with fresh
    DexScreener market data.

    IMPORTANT:
    A failed API request never becomes a successful update.
    last_api_success is False on failure.
    """

    contract = getattr(
        obj,
        "contract",
        None
    )

    if not contract:

        if hasattr(obj, "last_api_success"):
            obj.last_api_success = False

        print(
            "[API ERROR] Missing contract"
        )

        return obj

    # Always reset success before attempting a new update.
    if hasattr(obj, "last_api_success"):
        obj.last_api_success = False

    data = _fetch_dexscreener(contract)

    if data is None:
        return obj

    pairs = data.get("pairs")

    if not pairs:

        print(
            f"[API ERROR] DexScreener returned "
            f"no trading pairs for {contract}"
        )

        return obj

    pair = pairs[0]

    try:

        price = float(
            pair.get("priceUsd") or 0
        )

        market_cap = float(
            pair.get("marketCap") or 0
        )

        liquidity = float(
            pair.get(
                "liquidity",
                {}
            ).get("usd") or 0
        )

        volume = float(
            pair.get(
                "volume",
                {}
            ).get("m5") or 0
        )

        buys = int(
            pair.get(
                "txns",
                {}
            ).get(
                "m5",
                {}
            ).get("buys") or 0
        )

        sells = int(
            pair.get(
                "txns",
                {}
            ).get(
                "m5",
                {}
            ).get("sells") or 0
        )

        holders = pair.get("holders")

        # Reject structurally invalid market responses.
        if price <= 0:

            print(
                f"[API ERROR] Invalid price "
                f"for {contract}"
            )

            return obj

        # ====================================================
        # COIN OBJECT
        # ====================================================

        if hasattr(obj, "live_market_cap"):

            obj.price = price
            obj.live_market_cap = market_cap
            obj.market_cap = market_cap

            obj.liquidity = liquidity
            obj.volume_5m = volume

            obj.buys_5m = buys
            obj.sells_5m = sells

            if holders is not None:
                obj.holders = holders

        # ====================================================
        # POSITION OBJECT
        # ====================================================

        if hasattr(obj, "current_market_cap"):

            obj.current_price = price
            obj.current_market_cap = market_cap

            obj.liquidity = liquidity
            obj.volume_5m = volume

            obj.buys_5m = buys
            obj.sells_5m = sells

            obj.update_price(
                price,
                market_cap
            )

        # Mark successful only after the entire update
        # has completed successfully.
        if hasattr(obj, "last_api_success"):
            obj.last_api_success = True

        return obj

    except Exception as e:

        if hasattr(obj, "last_api_success"):
            obj.last_api_success = False

        print(
            f"[API ERROR] DexScreener data "
            f"processing failed for {contract}: {e}"
        )

        return obj
