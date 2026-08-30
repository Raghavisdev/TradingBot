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
    LAPC-v2 SMART ENTRY PROBE SIZING
    """
    final_score = getattr(coin, "final_score", 0)

    if final_score < 62:
        return 0.0

    # MCx filter
    if getattr(coin, "signal_market_cap", 0) and getattr(coin, "live_market_cap", 0):
        if coin.signal_market_cap > 0:
            mcx = coin.live_market_cap / coin.signal_market_cap
            if mcx > 2.0:
                return 0.0

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
    # S6 PORTFOLIO LIMITS (LAPC-v2)
    # --------------------------------------------------------

    open_positions = portfolio.get_open_positions()
    s6_count = sum(1 for p in open_positions if getattr(p, "strategy_id", "default") == "S6_Moonshot_Ladder")

    if s6_count >= 5:
        return 0.0

    s6_deployed = sum(
        getattr(p, "invested_amount", 0) + getattr(p, "entry_fees", 0) + getattr(p, "entry_slippage", 0) + getattr(p, "network_fee", 0)
        for p in open_positions if getattr(p, "strategy_id", "default") == "S6_Moonshot_Ladder"
    )

    # Also include the projected entry fees/slippage for THIS trade in the cap?
    # We don't know the exact fees here, but we know deployed must not exceed 35.
    # The actual fees will be deducted by paper_trader, but to be strictly under 35 deployed:
    if s6_deployed >= 35.0:
        return 0.0

    if s6_deployed + amount > 35.0:
        amount = 35.0 - s6_deployed

    amount = min(amount, MAX_TRADE_USD)

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
