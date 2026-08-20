from trading.portfolio import Portfolio
from trading.live_capital import LiveCapitalManager


class LivePortfolio(Portfolio):

    def __init__(self, wallet_public_key):

        super().__init__()

        self.wallet_public_key = wallet_public_key

        self.capital_manager = (
            LiveCapitalManager(
                wallet_public_key
            )
        )

        self.sync_capital()

    def sync_capital(self):

        capital = (
            self.capital_manager
            .get_capital()
        )

        available = float(
            capital.available_capital_usd
        )

        total = float(
            capital.wallet_value_usd
        )

        # Live S6 sizing reads initial_balance.
        # Keep it synchronized with actual wallet capital.
        self.initial_balance = total
        self.cash = available

        return capital

    def refresh(self):

        return self.sync_capital()

    def available_capital(self):

        return float(self.cash)
