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
    Legacy base sizing (Preserved for non-S6 strategies).
    """
    confidence = (
        getattr(coin, "gemtools_score", 0) * 0.45 +
        getattr(coin, "fundamental_score", 0) * 0.35 +
        getattr(coin, "market_health", 0) * 0.20
    )

    if confidence < 70: return 0.0
    if (getattr(coin, "dev", 0) or 0) > 15: return 0.0
    if (getattr(coin, "top10", 0) or 0) > 40: return 0.0
    if (getattr(coin, "bundled", 0) or 0) > 10: return 0.0
    if (getattr(coin, "liquidity", 0) or 0) < 15000: return 0.0

    if confidence >= 95: return 7.0
    elif confidence >= 90: return 6.0
    elif confidence >= 85: return 5.0
    elif confidence >= 80: return 4.0
    elif confidence >= 75: return 3.0
    else: return 2.0


def get_position_size(coin, portfolio):
    strategy_id = getattr(coin, "strategy_id", "S6_Moonshot_Ladder")

    cash = float(getattr(portfolio, "cash", 0.0) or 0.0)

    # ========================================================
    # S6_Moonshot_Ladder (LAPC-v2)
    # ========================================================
    if strategy_id == "S6_Moonshot_Ladder":
        final_score = getattr(coin, "final_score", 0)
        if final_score < 62:
            return 0.0

        from ai_engine.validator import validate_s6_execution
        is_valid_s6, s6_reason = validate_s6_execution(coin, strategy_id)
        if not is_valid_s6:
            return 0.0

        amount = 2.0  # EXACT $2 probe, no capital scaling

        # S6 PORTFOLIO LIMITS
        open_positions = portfolio.get_open_positions()
        s6_count = sum(1 for p in open_positions if getattr(p, "strategy_id", "default") == "S6_Moonshot_Ladder")

        if s6_count >= 5:
            return 0.0

        s6_deployed = sum(
            getattr(p, "invested_amount", 0) + getattr(p, "entry_fees", 0) + getattr(p, "entry_slippage", 0) + getattr(p, "network_fee", 0)
            for p in open_positions if getattr(p, "strategy_id", "default") == "S6_Moonshot_Ladder"
        )

        if s6_deployed >= 35.0:
            return 0.0

        if s6_deployed + amount > 35.0:
            amount = 35.0 - s6_deployed

        amount = min(amount, cash)
        return round(amount, 2)

    # ========================================================
    # LEGACY / OTHER STRATEGIES
    # ========================================================
    base_amount = get_s6_base_size(coin)

    if base_amount <= 0:
        return 0.0

    capital = float(getattr(portfolio, "initial_balance", 0.0) or 0.0)
    if capital <= 0:
        return 0.0

    capital_multiplier = capital / REFERENCE_CAPITAL_USD
    amount = base_amount * capital_multiplier

    amount = min(amount, cash)
    amount = min(amount, MAX_TRADE_USD * capital_multiplier)

    if amount < MIN_TRADE_USD:
        return 0.0

    return round(amount, 2)


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
