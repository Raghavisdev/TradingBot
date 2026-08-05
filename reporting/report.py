from knowledge.coin import Coin


def print_report(coin: Coin):

    print("\n" + "=" * 60)
    print("🚀 NEW GEMTOOLS SIGNAL")
    print("=" * 60)

    print(f"Coin              : {coin.symbol}")
    print(f"Name              : {coin.name}")
    print(f"Contract          : {coin.contract}")

    print()

    print(f"Signal MC         : ${coin.signal_market_cap:,.0f}")

    if coin.live_market_cap:

        print(f"Live MC           : ${coin.live_market_cap:,.0f}")

        growth = coin.live_market_cap / coin.signal_market_cap

        print(f"Growth            : {growth:.2f}x")

    print("\n" + "=" * 60)

    print(f"GemTools Score    : {coin.gemtools_score}/100")
    print(f"Fundamental Score : {coin.fundamental_score}/100")
    print(f"Final Score       : {coin.final_score}/100")

    print()

    print(f"Decision          : {coin.decision}")

    print("\n" + "=" * 60)

    print("Strengths")

    if len(coin.strengths) == 0:

        print("  None")

    else:

        for item in coin.strengths:
            print(f"  ✔ {item}")

    print()

    print("Weaknesses")

    if len(coin.weaknesses) == 0:

        print("  None")

    else:

        for item in coin.weaknesses:
            print(f"  ✖ {item}")

    print("\n" + "=" * 60)

    print("GemTools Breakdown")

    for k, v in coin.gemtools_breakdown.items():
        print(f"  {k:<15} {v}")

    print()

    print("Fundamental Breakdown")

    for k, v in coin.fundamental_breakdown.items():
        print(f"  {k:<15} {v}")

    print("=" * 60)