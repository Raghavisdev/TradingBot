from collectors.dexscreener import update_dex_data


def collect_all(coin):

    print("\n==============================")
    print("Collecting Market Data...")
    print("==============================")

    coin = update_dex_data(coin)

    print("✓ DexScreener Finished")

    return coin