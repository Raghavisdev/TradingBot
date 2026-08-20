import os
import config


# ============================================================
# S6 CAPITAL-AWARE POSITION SIZER
# ============================================================

REFERENCE_CAPITAL_USD = float(
    os.getenv("S6_REFERENCE_CAPITAL_USD", "100.0")
)

MIN_TRADE_USD = float(
    os.getenv("S6_MIN_TRADE_USD", "1.0")
)

MAX_TRADE_USD = float(
    os.getenv("S6_MAX_TRADE_USD", "7.0")
)


def get_s6_base_size(coin):
    """
    Original S6 allocation logic.

    IMPORTANT:
    This function intentionally preserves the existing
    confidence -> dollar allocation relationship.
    """

    confidence = (
        coin.gemtools_score * 0.45 +
        coin.fundamental_score * 0.35 +
        coin.market_health * 0.20
    )

    # -----------------------------
    # Existing hard filters
    # -----------------------------

    if confidence < 70:
        return 0.0

    if coin.dev > 15:
        return 0.0

    if coin.top10 > 40:
        return 0.0

    if coin.bundled > 10:
        return 0.0

    if coin.liquidity < 15000:
        return 0.0

    # -----------------------------
    # Existing S6 sizing
    # -----------------------------

    if confidence >= 95:
        return 7.0

    elif confidence >= 90:
        return 6.0

    elif confidence >= 85:
        return 5.0

    elif confidence >= 80:
        return 4.0

    elif confidence >= 75:
        return 3.0

    else:
        return 2.0


def get_position_size(coin, portfolio):
    """
    Capital-aware S6 position sizing.

    The S6 decision and confidence structure remain unchanged.

    Example with $100 reference capital:

        S6 base = $5

        $20 capital:
            $5 * 20/100 = $1

        $100 capital:
            $5 * 100/100 = $5

        $500 capital:
            raw = $25
            capped by MAX_TRADE_USD
    """

    base_amount = get_s6_base_size(coin)

    if base_amount <= 0:
        return 0.0

    # --------------------------------------------------------
    # Determine actual trading capital
    #
    # portfolio.initial_balance is used rather than assuming
    # $100 forever.
    # --------------------------------------------------------

    capital = float(
        getattr(
            portfolio,
            "initial_balance",
            0.0
        )
        or 0.0
    )

    if capital <= 0:
        return 0.0

    # --------------------------------------------------------
    # Scale S6 allocation relative to actual capital
    # --------------------------------------------------------

    capital_multiplier = (
        capital /
        REFERENCE_CAPITAL_USD
    )

    amount = (
        base_amount *
        capital_multiplier
    )

    # --------------------------------------------------------
    # Never exceed available cash
    # --------------------------------------------------------

    cash = float(
        getattr(
            portfolio,
            "cash",
            0.0
        )
        or 0.0
    )

    amount = min(
        amount,
        cash
    )

    # --------------------------------------------------------
    # Absolute safety cap
    # --------------------------------------------------------

    amount = min(
        amount,
        MAX_TRADE_USD *
        capital_multiplier
    )

    # --------------------------------------------------------
    # Avoid meaningless dust trades
    # --------------------------------------------------------

    if amount < MIN_TRADE_USD:
        return 0.0

    return round(
        amount,
        2
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("S6 CAPITAL-AWARE POSITION SIZER")
    print("=" * 70)

    print(
        "Reference capital : $",
        REFERENCE_CAPITAL_USD
    )

    print(
        "Minimum trade     : $",
        MIN_TRADE_USD
    )

    print(
        "Maximum reference : $",
        MAX_TRADE_USD
    )

    print()
    print("Scaling examples:")

    for capital in [20, 44, 100, 500, 1000]:

        print(
            f"Capital ${capital:7.2f} -> "
            f"S6 $5 allocation = "
            f"${5 * capital / REFERENCE_CAPITAL_USD:.2f}"
        )
