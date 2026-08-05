from trading.position import Position
import strategy


def manage_position(position: Position):

    action = "HOLD"

    reason = "Trend is healthy"

    # ==========================================
    # STOP LOSS
    # ==========================================

    if position.pnl_percent <= strategy.STOP_LOSS:

        action = "SELL_ALL"

        reason = "Stop Loss Hit"

        return action, reason

    # ==========================================
    # TAKE PROFIT LEVEL 1
    # ==========================================

    if (
        position.pnl_percent >= 100
        and position.sold_percent == 0
    ):

        action = "SELL_70"

        reason = "Reached 2x"

        return action, reason

    # ==========================================
    # TAKE PROFIT LEVEL 2
    # ==========================================

    if (
        position.pnl_percent >= 200
        and position.sold_percent == 70
    ):

        action = "SELL_15"

        reason = "Reached 3x"

        return action, reason

    # ==========================================
    # TAKE PROFIT LEVEL 3
    # ==========================================

    if (
        position.pnl_percent >= 300
        and position.sold_percent == 85
    ):

        action = "SELL_15"

        reason = "Reached 4x"

        return action, reason

    # ==========================================
    # TRAILING STOP
    # ==========================================

    drawdown = (
        position.highest_profit -
        position.pnl_percent
    )

    if (
        position.highest_profit >= 100
        and
        drawdown >= strategy.TRAILING_STOP
    ):

        action = "SELL_ALL"

        reason = "Trailing Stop Hit"

        return action, reason

    return action, reason