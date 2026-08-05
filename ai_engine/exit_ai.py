from ai_engine.trend import trend


def get_exit_decision(position):

    score = 0
    reasons = []

    # =====================================
    # HARD STOP LOSS
    # =====================================

    if position.pnl_percent <= -45:

        return (
            "SELL_ALL",
            100,
            "Hard Stop Loss"
        )

    # =====================================
    # PROFIT SCORE
    # =====================================

    if position.pnl_percent >= 300:
        score += 35
        reasons.append("Huge profit")

    elif position.pnl_percent >= 200:
        score += 30
        reasons.append("Excellent profit")

    elif position.pnl_percent >= 100:
        score += 20
        reasons.append("Good profit")

    elif position.pnl_percent >= 60:
        score += 15

    elif position.pnl_percent >= 30:
        score += 10

    # =====================================
    # MARKET HEALTH
    # =====================================

    health = position.market_health

    if health < 20:

        score += 25
        reasons.append("Health collapsed")

    elif health < 40:

        score += 18

    elif health < 60:

        score += 10

    elif health < 80:

        score += 5

    # =====================================
    # BUY PRESSURE
    # =====================================

    total = position.buys_5m + position.sells_5m

    if total > 0:

        buy_ratio = position.buys_5m / total

        if buy_ratio < 0.40:

            score += 20
            reasons.append("Heavy selling")

        elif buy_ratio < 0.50:

            score += 15

        elif buy_ratio < 0.60:

            score += 10

    # =====================================
    # LIQUIDITY
    # =====================================

    if position.liquidity < 5000:

        score += 20
        reasons.append("Very low liquidity")

    elif position.liquidity < 10000:

        score += 10
        reasons.append("Low liquidity")

    # =====================================
    # HEALTH TREND
    # =====================================

    if len(position.health_history) >= 5:

        t = trend(position.health_history)

        if t < -15:

            score += 15
            reasons.append("Health falling")

    # =====================================
    # LIQUIDITY TREND
    # =====================================

    if len(position.liquidity_history) >= 5:

        t = trend(position.liquidity_history)

        if t < 0:

            score += 10
            reasons.append("Liquidity dropping")

    # =====================================
    # VOLUME TREND
    # =====================================

    if len(position.volume_history) >= 5:

        t = trend(position.volume_history)

        if t < 0:

            score += 10
            reasons.append("Volume decreasing")

    # =====================================
    # BUY PRESSURE TREND
    # =====================================

    if len(position.buy_ratio_history) >= 5:

        t = trend(position.buy_ratio_history)

        if t < -0.10:

            score += 15
            reasons.append("Buy pressure weakening")

    # =====================================
    # PANIC EXIT
    # =====================================

    if len(position.health_history) >= 10:

        if position.health_history[-10] - position.health_history[-1] >= 40:

            return (
                "SELL_ALL",
                100,
                "Panic Exit"
            )

    # =====================================
    # DECISION
    # =====================================

    if score >= 85:

        return (
            "SELL_ALL",
            score,
            ", ".join(reasons)
        )

    elif score >= 65:

        return (
            "SELL_70",
            score,
            ", ".join(reasons)
        )

    elif score >= 45:

        return (
            "SELL_40",
            score,
            ", ".join(reasons)
        )

    elif score >= 25:

        return (
            "SELL_20",
            score,
            ", ".join(reasons)
        )

    return (
        "HOLD",
        score,
        "Healthy trend"
    )