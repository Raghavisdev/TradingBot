from datetime import datetime

from trading.position import Position
from database.database import database


class PaperTrader:

    def __init__(self, portfolio):

        self.portfolio = portfolio

    # ==========================================
    # BUY
    # ==========================================

    def buy(self, coin, amount):

        if amount <= 0:
            print("Invalid investment amount.")
            return None

        if self.portfolio.cash < amount:

            print("❌ Not enough cash")

            return None

        position = Position()

        position.symbol = coin.symbol
        position.contract = coin.contract

        position.entry_price = coin.price
        position.entry_market_cap = coin.live_market_cap

        position.invested_amount = amount

        position.buy_time = datetime.now()

        # Copy AI scores for database
        position.market_health = getattr(coin, "market_health", 0)
        position.gemtools_score = getattr(coin, "gemtools_score", 0)
        position.fundamental_score = getattr(coin, "fundamental_score", 0)

        if coin.price > 0:
            position.tokens = amount / coin.price

        position.initialize()

        self.portfolio.cash -= amount

        self.portfolio.add_position(position)

        print("\n==============================")
        print("✅ PAPER BUY EXECUTED")
        print("==============================")
        print("Coin        :", position.symbol)
        print("Investment  : $", amount)
        print("Entry Price :", position.entry_price)
        print("Entry MC    :", position.entry_market_cap)
        print("Cash Left   : $", round(self.portfolio.cash, 2))
        print("==============================\n")

        return position

    # ==========================================
    # SELL ALL
    # ==========================================

    def sell_all(self, position):

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
        position.sold_percent = 100

        position.realized_profit = position.pnl_dollars

        position.status = "CLOSED"

        # Save trade before removing
        database.save_trade(position)

        self.portfolio.close_position(position)

        print("\n==============================")
        print("✅ PAPER SELL")
        print("==============================")
        print("Coin         :", position.symbol)
        print("Profit ($)   :", round(position.pnl_dollars, 2))
        print("Profit (%)   :", round(position.pnl_percent, 2))
        print("Held (mins)  :", round(position.holding_time, 2))
        print("Cash Balance : $", round(self.portfolio.cash, 2))
        print("==============================\n")

    # ==========================================
    # PARTIAL SELL
    # ==========================================

    def partial_sell(self, position, percent):

        if percent <= 0:
            return

        if percent > position.remaining_percent:
            percent = position.remaining_percent

        current_value = (
            position.invested_amount +
            position.pnl_dollars
        )

        sold_value = current_value * percent / 100

        self.portfolio.cash += sold_value

        position.remaining_percent -= percent
        position.sold_percent += percent

        position.realized_profit += (
            position.pnl_dollars * percent / 100
        )

        print("\n==============================")
        print("💰 PARTIAL SELL")
        print("==============================")
        print("Coin          :", position.symbol)
        print("Sold          :", percent, "%")
        print("Received      : $", round(sold_value, 2))
        print("Remaining     :", position.remaining_percent, "%")
        print("Cash Balance  : $", round(self.portfolio.cash, 2))
        print("==============================\n")