from trading.position import Position


def calculate_market_health(position):

    score = 0

    breakdown = {}

    # ==========================================
    # LIQUIDITY (20)
    # ==========================================

    if position.liquidity >= 50000:

        liquidity = 20

    elif position.liquidity >= 30000:

        liquidity = 16

    elif position.liquidity >= 15000:

        liquidity = 12

    elif position.liquidity >= 5000:

        liquidity = 8

    else:

        liquidity = 2

    score += liquidity

    breakdown["Liquidity"] = liquidity

    # ==========================================
    # VOLUME (20)
    # ==========================================

    if position.volume_5m >= 100000:

        volume = 20

    elif position.volume_5m >= 50000:

        volume = 16

    elif position.volume_5m >= 10000:

        volume = 12

    elif position.volume_5m >= 1000:

        volume = 8

    else:

        volume = 2

    score += volume

    breakdown["Volume"] = volume

    # ==========================================
    # BUY PRESSURE (20)
    # ==========================================

    total = position.buys_5m + position.sells_5m

    if total == 0:

        buy_pressure = 10

    else:

        ratio = position.buys_5m / total

        if ratio >= 0.75:

            buy_pressure = 20

        elif ratio >= 0.60:

            buy_pressure = 16

        elif ratio >= 0.50:

            buy_pressure = 12

        elif ratio >= 0.40:

            buy_pressure = 8

        else:

            buy_pressure = 2

    score += buy_pressure

    breakdown["Buy Pressure"] = buy_pressure

    # ==========================================
    # MARKET CAP TREND (20)
    # ==========================================

    if position.current_market_cap >= position.entry_market_cap * 3:

        trend = 20

    elif position.current_market_cap >= position.entry_market_cap * 2:

        trend = 16

    elif position.current_market_cap >= position.entry_market_cap:

        trend = 12

    elif position.current_market_cap >= position.entry_market_cap * 0.7:

        trend = 8

    else:

        trend = 2

    score += trend

    breakdown["Trend"] = trend

    # ==========================================
    # MOMENTUM (20)
    # ==========================================

    if position.current_market_cap >= position.highest_market_cap * 0.95:

        momentum = 20

    elif position.current_market_cap >= position.highest_market_cap * 0.85:

        momentum = 16

    elif position.current_market_cap >= position.highest_market_cap * 0.70:

        momentum = 12

    elif position.current_market_cap >= position.highest_market_cap * 0.50:

        momentum = 8

    else:

        momentum = 2

    score += momentum

    breakdown["Momentum"] = momentum

    return score, breakdown