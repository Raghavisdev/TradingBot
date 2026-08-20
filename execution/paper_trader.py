import time
import logging
from datetime import datetime

from trading.position import Position
from database.database import database

logger = logging.getLogger("PaperTrader")


# ============================================================
# PAPER EXECUTION MODEL
# ============================================================
#
# This is a configurable PAPER-TRADING friction assumption.
#
# It is NOT:
#   - a Jupiter fee
#   - a Solana network fee
#   - measured live slippage
#
# Live execution will use actual execution data instead.
#
PAPER_EXECUTION_FRICTION_RATE = 0.01


class PaperTrader:

    def __init__(self, portfolio):
        self.portfolio = portfolio

    # =========================================================
    # BUY
    # =========================================================

    def buy(self, coin, amount):

        amount = float(amount)

        if amount <= 0:
            logger.warning(
                "[PAPER BUY] Invalid investment amount for %s",
                getattr(coin, "symbol", "?"),
            )
            return None

        entry_friction = (
            amount *
            PAPER_EXECUTION_FRICTION_RATE
        )

        total_cash_required = (
            amount +
            entry_friction
        )

        if self.portfolio.cash < total_cash_required:
            logger.warning(
                "[PAPER BUY] Not enough cash for %s "
                "(need $%.6f including execution friction, "
                "have $%.6f)",
                getattr(coin, "symbol", "?"),
                total_cash_required,
                self.portfolio.cash,
            )
            return None

        position = Position()

        position.symbol = coin.symbol
        position.contract = coin.contract
        position.signal_id = getattr(
            coin,
            "signal_id",
            None,
        )

        position.entry_price = float(coin.price)
        position.entry_market_cap = float(
            coin.live_market_cap
        )
        position.entry_time = time.time()

        # Capital allocated to the asset itself.
        position.invested_amount = amount

        position.buy_time = datetime.now()

        # Preserve existing AI information.
        position.market_health = getattr(
            coin,
            "market_health",
            0,
        )

        position.gemtools_score = getattr(
            coin,
            "gemtools_score",
            0,
        )

        position.fundamental_score = getattr(
            coin,
            "fundamental_score",
            0,
        )

        if position.entry_price <= 0:
            logger.warning(
                "[PAPER BUY] Invalid price for %s",
                position.symbol,
            )
            return None

        position.tokens = (
            amount /
            position.entry_price
        )

        # Paper friction is tracked separately from
        # actual blockchain fees.
        position.entry_slippage = entry_friction

        position.entry_fees = 0.0
        position.exit_fees = 0.0
        position.exit_slippage = 0.0

        position.realized_proceeds = 0.0
        position.realized_cost = 0.0
        position.realized_profit = 0.0
        position.net_realized_pnl = 0.0

        position.initialize()

        # Asset capital + simulated entry friction.
        self.portfolio.cash -= total_cash_required

        self.portfolio.add_position(position)

        try:
            if not database.open_paper_trade(position):
                logger.error(
                    "[PAPER BUY] DB persist failed for %s",
                    position.symbol,
                )
        except Exception as exc:
            logger.error(
                "[PAPER BUY] DB persist exception for %s: %s",
                position.symbol,
                exc,
            )

        print()
        print("==============================")
        print("PAPER BUY EXECUTED")
        print("==============================")
        print("Coin              :", position.symbol)
        print("Trade ID          :", position.trade_id)
        print("Investment        : $", round(amount, 6))
        print("Entry friction    : $", round(entry_friction, 6))
        print("Total cash used   : $", round(total_cash_required, 6))
        print("Entry Price       :", position.entry_price)
        print("Cash Left         : $", round(self.portfolio.cash, 6))
        print("==============================")
        print()

        return position

    # =========================================================
    # PARTIAL SELL
    # =========================================================

    def partial_sell(
        self,
        position,
        percent,
        exit_reason: str = "",
    ):

        if position.status == "CLOSED":
            return False

        percent = float(percent)

        if percent <= 0:
            return False

        if position.remaining_percent <= 0:
            return False

        percent = min(
            percent,
            float(position.remaining_percent),
        )

        # Current gross market value of the entire position.
        current_value = (
            position.invested_amount +
            position.pnl_dollars
        )

        gross_proceeds = (
            current_value *
            percent /
            100.0
        )

        exit_friction = (
            gross_proceeds *
            PAPER_EXECUTION_FRICTION_RATE
        )

        net_proceeds = (
            gross_proceeds -
            exit_friction
        )

        # Original capital allocated to this slice.
        slice_cost = (
            position.invested_amount *
            percent /
            100.0
        )

        # Net result generated by this completed exit slice.
        net_slice_pnl = (
            gross_proceeds -
            slice_cost -
            exit_friction
        )

        self.portfolio.cash += net_proceeds

        position.remaining_percent = max(
            0.0,
            position.remaining_percent -
            percent,
        )

        position.sold_percent = min(
            100.0,
            position.sold_percent +
            percent,
        )

        position.realized_proceeds += net_proceeds
        position.realized_cost += slice_cost
        position.exit_slippage += exit_friction

        position.realized_profit += net_slice_pnl

        # Entry friction is a cost of the whole trade.
        position.net_realized_pnl = (
            position.realized_profit -
            position.entry_slippage
        )

        reason = (
            exit_reason or
            getattr(
                position,
                "exit_reason",
                "Partial",
            )
        )

        try:
            if not database.record_partial_sell(
                position,
                percent=percent,
                proceeds=gross_proceeds,
                partial_pnl=net_slice_pnl,
                exit_reason=reason,
                fees=0.0,
                slippage=exit_friction,
            ):
                logger.error(
                    "[PAPER PARTIAL SELL] "
                    "DB persist failed for %s",
                    position.symbol,
                )
        except Exception as exc:
            logger.error(
                "[PAPER PARTIAL SELL] "
                "DB persist exception for %s: %s",
                position.symbol,
                exc,
            )

        print()
        print("==============================")
        print("PAPER PARTIAL SELL")
        print("==============================")
        print("Coin              :", position.symbol)
        print("Trade ID          :", position.trade_id)
        print("Sold              :", percent, "%")
        print("Gross proceeds    : $", round(gross_proceeds, 6))
        print("Exit friction     : $", round(exit_friction, 6))
        print("Net proceeds      : $", round(net_proceeds, 6))
        print("Net slice P&L     : $", round(net_slice_pnl, 6))
        print("Remaining         :", position.remaining_percent, "%")
        print("Cash Balance      : $", round(self.portfolio.cash, 6))
        print("==============================")
        print()

        return True

    # =========================================================
    # SELL ALL
    # =========================================================

    def sell_all(
        self,
        position,
        exit_reason: str = "",
    ):

        if position.status == "CLOSED":
            return False

        if position.remaining_percent <= 0:
            return False

        position.sell_time = datetime.now()

        position.holding_time = (
            position.sell_time -
            position.buy_time
        ).total_seconds() / 60

        remaining_percent = float(
            position.remaining_percent
        )

        current_value = (
            position.invested_amount +
            position.pnl_dollars
        )

        gross_proceeds = (
            current_value *
            remaining_percent /
            100.0
        )

        exit_friction = (
            gross_proceeds *
            PAPER_EXECUTION_FRICTION_RATE
        )

        net_proceeds = (
            gross_proceeds -
            exit_friction
        )

        slice_cost = (
            position.invested_amount *
            remaining_percent /
            100.0
        )

        net_slice_pnl = (
            gross_proceeds -
            slice_cost -
            exit_friction
        )

        self.portfolio.cash += net_proceeds

        position.realized_proceeds += net_proceeds
        position.realized_cost += slice_cost
        position.exit_slippage += exit_friction

        position.realized_profit += net_slice_pnl

        position.net_realized_pnl = (
            position.realized_profit -
            position.entry_slippage
        )

        position.remaining_percent = 0.0
        position.sold_percent = 100.0
        position.status = "CLOSED"

        reason = (
            exit_reason or
            getattr(
                position,
                "exit_reason",
                "Manual",
            )
        )

        try:
            if not database.close_paper_trade(
                position,
                exit_reason=reason,
            ):
                logger.error(
                    "[PAPER SELL] "
                    "DB close failed for %s",
                    position.symbol,
                )
        except Exception as exc:
            logger.error(
                "[PAPER SELL] "
                "DB persist exception for %s: %s",
                position.symbol,
                exc,
            )

        self.portfolio.close_position(position)

        print()
        print("==============================")
        print("PAPER SELL")
        print("==============================")
        print("Coin              :", position.symbol)
        print("Trade ID          :", position.trade_id)
        print("Gross proceeds    : $", round(gross_proceeds, 6))
        print("Exit friction     : $", round(exit_friction, 6))
        print("Net proceeds      : $", round(net_proceeds, 6))
        print("Net trade P&L     : $", round(position.net_realized_pnl, 6))
        print("Profit (%)        :", round(position.pnl_percent, 4))
        print("Held (mins)       :", round(position.holding_time, 2))
        print("Reason            :", reason)
        print("Cash Balance      : $", round(self.portfolio.cash, 6))
        print("==============================")
        print()

        return True
