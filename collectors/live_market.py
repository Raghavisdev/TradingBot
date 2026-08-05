import requests
from config import DEXSCREENER_TIMEOUT


def update_market(obj):
    """
    Updates either a Coin or Position object
    with latest DexScreener data.
    """

    try:

        url = f"https://api.dexscreener.com/latest/dex/tokens/{obj.contract}"

        response = requests.get(url, timeout=DEXSCREENER_TIMEOUT)

        if response.status_code != 200:
            if hasattr(obj, "last_api_success"):
                obj.last_api_success = False
            print(f"[API ERROR] DexScreener HTTP {response.status_code} for {getattr(obj, 'contract', '')}")
            return obj

        data = response.json()

        pairs = data.get("pairs")

        if not pairs:
            if hasattr(obj, "last_api_success"):
                obj.last_api_success = False
            print(f"[API ERROR] DexScreener returned no trading pairs for {getattr(obj, 'contract', '')}")
            return obj

        pair = pairs[0]

        # ======================================
        # PRICE
        # ======================================

        price = float(pair.get("priceUsd") or 0)

        # ======================================
        # MARKET CAP
        # ======================================

        market_cap = float(pair.get("marketCap") or 0)

        # ======================================
        # LIQUIDITY
        # ======================================

        liquidity = float(
            pair.get("liquidity", {}).get("usd") or 0
        )

        # ======================================
        # VOLUME
        # ======================================

        volume = float(
            pair.get("volume", {}).get("m5") or 0
        )

        # ======================================
        # TRANSACTIONS
        # ======================================

        buys = int(
            pair.get("txns", {}).get("m5", {}).get("buys") or 0
        )

        sells = int(
            pair.get("txns", {}).get("m5", {}).get("sells") or 0
        )

        holders = pair.get("holders")

        # Flag successful API update
        if hasattr(obj, "last_api_success"):
            obj.last_api_success = True

        # ======================================
        # COIN OBJECT
        # ======================================

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

        # ======================================
        # POSITION OBJECT
        # ======================================

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

        return obj

    except Exception as e:

        if hasattr(obj, "last_api_success"):
            obj.last_api_success = False

        print(f"[API ERROR] DexScreener exception for {getattr(obj, 'contract', '')}: {e}")

        return obj