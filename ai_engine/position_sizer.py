import config


def get_position_size(coin, portfolio):

    # ===============================
    # Overall Confidence
    # ===============================

    confidence = (
        coin.gemtools_score * 0.45 +
        coin.fundamental_score * 0.35 +
        coin.market_health * 0.20
    )

    # ===============================
    # Hard Filters
    # ===============================

    if confidence < 70:
        return 0

    if coin.dev > 15:
        return 0

    if coin.top10 > 40:
        return 0

    if coin.bundled > 10:
        return 0

    if coin.liquidity < 15000:
        return 0

    # ===============================
    # Dynamic Position Size
    # ===============================

    cash = portfolio.cash

    if confidence >= 95:
        amount = 7

    elif confidence >= 90:
        amount = 6

    elif confidence >= 85:
        amount = 5

    elif confidence >= 80:
        amount = 4

    elif confidence >= 75:
        amount = 3

    else:
        amount = 2

    # Never invest more than available cash
    amount = min(amount, cash)

    return round(amount, 2)