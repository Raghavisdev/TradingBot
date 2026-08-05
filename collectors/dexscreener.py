import requests
from knowledge.coin import Coin

BASE_URL = "https://api.dexscreener.com/latest/dex/tokens/"


def update_dex_data(coin: Coin) -> Coin:
    """
    Fetch live market data from DexScreener
    and update the Coin object.
    """

    if coin is None:
        print("❌ Coin object is None")
        return None

    try:

        print(f"\nFetching DexScreener data for {coin.contract}")

        response = requests.get(
            BASE_URL + coin.contract,
            timeout=10
        )

        print("Status Code:", response.status_code)

        if response.status_code != 200:
            print("❌ Failed to fetch DexScreener data.")
            return coin

        data = response.json()

        pairs = data.get("pairs", [])

        if not pairs:
            print("❌ No trading pairs found.")
            return coin

        # Use the first pair for now
        pair = pairs[0]

        # -----------------------------
        # Token Information
        # -----------------------------

        base = pair.get("baseToken", {})

        coin.symbol = base.get("symbol", coin.symbol)
        coin.name = base.get("name", coin.name)

        # -----------------------------
        # Price
        # -----------------------------

        coin.price = pair.get("priceUsd")

        # -----------------------------
        # Market
        # -----------------------------

        # LIVE market cap from Dex
        coin.live_market_cap = pair.get("marketCap")

        # Keep compatibility with existing code
        coin.market_cap = coin.live_market_cap

        coin.fdv = pair.get("fdv")

        liquidity = pair.get("liquidity", {})

        coin.liquidity = liquidity.get("usd")

        # -----------------------------
        # Volume
        # -----------------------------

        volume = pair.get("volume", {})

        coin.volume_5m = volume.get("m5", 0)
        coin.volume_1h = volume.get("h1", 0)
        coin.volume_24h = volume.get("h24", 0)

        # -----------------------------
        # Transactions
        # -----------------------------

        txns = pair.get("txns", {})
        m5 = txns.get("m5", {})

        coin.buys_5m = m5.get("buys", 0)
        coin.sells_5m = m5.get("sells", 0)

        # -----------------------------
        # Pair Info
        # -----------------------------

        coin.chain = pair.get("chainId")
        coin.dex = pair.get("dexId")
        coin.dex_url = pair.get("url")
        coin.pair_created = pair.get("pairCreatedAt")

        print("✅ DexScreener Updated Successfully")

        return coin

    except Exception as e:

        print("DexScreener Exception:", e)

        return coin