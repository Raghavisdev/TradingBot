import time
import logging
from datetime import datetime

from trading.position import Position
from database.database import database

logger = logging.getLogger("PaperTrader")


class PaperTrader:

    def __init__(self, portfolio):

        self.portfolio = portfolio

    # ==========================================
    # BUY
    # ==========================================

    def buy(self, coin, amount):

        if amount <= 0:
            logger.warning("[PAPER BUY] Invalid investment amount for %s", getattr(coin, "symbol", "?"))
            return None

        if self.portfolio.cash < amount:
            logger.warning("[PAPER BUY] Not enough cash for %s (need $%.2f, have $%.2f)",
                           getattr(coin, "symbol", "?"), amount, self.portfolio.cash)
            return None

        position = Position()

        position.symbol        = coin.symbol
        position.contract      = coin.contract
        position.signal_id     = getattr(coin, "signal_id", None)   # link to signals table

        position.entry_price      = coin.price
        position.entry_market_cap = coin.live_market_cap
        position.entry_time       = time.time()                      # UNIX timestamp for DB

        position.invested_amount = amount

        position.buy_time = datetime.now()

        # Copy AI scores for reference
        position.market_health    = getattr(coin, "market_health",     0)
        position.gemtools_score   = getattr(coin, "gemtools_score",    0)
        position.fundamental_score = getattr(coin, "fundamental_score", 0)

        if coin.price > 0:
            position.tokens = amount / coin.price

        position.initialize()

        self.portfolio.cash -= amount
        self.portfolio.add_position(position)

        # ── Persist to database ──────────────────────────────────
        try:
            database.open_paper_trade(position)
        except Exception as e:
            logger.error("[PAPER BUY] DB persist failed for %s: %s", position.symbol, e)

        print("\n==============================")
        print("✅ PAPER BUY EXECUTED")
        print("==============================")
        print("Coin        :", position.symbol)
        print("Trade ID    :", position.trade_id)
        print("Investment  : $", amount)
        print("Entry Price :", position.entry_price)
        print("Entry MC    :", position.entry_market_cap)
        print("Cash Left   : $", round(self.portfolio.cash, 2))
        print("==============================\n")

        return position

    # ==========================================
    # SELL ALL
    # ==========================================

    def sell_all(self, position, exit_reason: str = ""):

        if position.status == "CLOSED":
            return

        position.sell_time = datetime.now()

        position.holding_time = (
            position.sell_time -
            position.buy_time
        ).total_seconds() / 60

        proceeds = position.invested_amount + position.pnl_dollars

        self.portfolio.cash += proceeds

        position.remaining_percent = 0
        position.sold_percent      = 100

        position.realized_profit = position.pnl_dollars

        position.status = "CLOSED"

        # ── Persist to database ──────────────────────────────────
        reason = exit_reason or getattr(position, "exit_reason", "Manual")
        try:
            database.close_paper_trade(position, exit_reason=reason)
        except Exception as e:
            logger.error("[PAPER SELL] DB persist failed for %s: %s", position.symbol, e)

        self.portfolio.close_position(position)

        print("\n==============================")
        print("✅ PAPER SELL")
        print("==============================")
        print("Coin         :", position.symbol)
        print("Trade ID     :", position.trade_id)
        print("Profit ($)   :", round(position.pnl_dollars, 2))
        print("Profit (%)   :", round(position.pnl_percent, 2))
        print("Held (mins)  :", round(position.holding_time, 2))
        print("Reason       :", reason)
        print("Cash Balance : $", round(self.portfolio.cash, 2))
        print("==============================\n")

    # ==========================================
    # PARTIAL SELL
    # ==========================================

    def partial_sell(self, position, percent, exit_reason: str = ""):

        if percent <= 0:
            return

        if percent > position.remaining_percent:
            percent = position.remaining_percent

        current_value = (
            position.invested_amount +
            position.pnl_dollars
        )

        sold_value = current_value * percent / 100

        # P&L on this slice:
        # cost of the slice = invested * percent / 100
        # profit = sold_value - cost_of_slice
        slice_cost  = position.invested_amount * percent / 100.0
        partial_pnl = sold_value - slice_cost

        self.portfolio.cash += sold_value

        position.remaining_percent -= percent
        position.sold_percent      += percent

        position.realized_profit += partial_pnl

        # ── Persist to database ──────────────────────────────────
        reason = exit_reason or getattr(position, "exit_reason", "Partial")
        try:
            database.record_partial_sell(
                position,
                percent     = percent,
                proceeds    = sold_value,
                partial_pnl = partial_pnl,
                exit_reason = reason,
            )
        except Exception as e:
            logger.error("[PAPER PARTIAL SELL] DB persist failed for %s: %s", position.symbol, e)

        print("\n==============================")
        print("💰 PARTIAL SELL")
        print("==============================")
        print("Coin          :", position.symbol)
        print("Trade ID      :", position.trade_id)
        print("Sold          :", percent, "%")
        print("Received      : $", round(sold_value, 2))
        print("Partial PnL   : $", round(partial_pnl, 2))
        print("Remaining     :", position.remaining_percent, "%")
        print("Cash Balance  : $", round(self.portfolio.cash, 2))
        print("==============================\n")

