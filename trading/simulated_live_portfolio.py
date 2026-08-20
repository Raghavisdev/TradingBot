from trading.portfolio import Portfolio


class SimulatedLivePortfolio(Portfolio):

    """
    Controlled capital environment for live-execution preflight.

    Uses simulated capital while still allowing the live executor
    to use the real wallet public key for Jupiter transaction
    construction.

    IMPORTANT:
        No private key.
        No signing.
        No transaction submission.
        No funds moved.
    """

    def __init__(
        self,
        wallet_public_key,
        initial_capital=20.0,
    ):

        super().__init__()

        self.wallet_public_key = wallet_public_key

        self.initial_balance = float(
            initial_capital
        )

        self.cash = float(
            initial_capital
        )

        # Critical:
        # LiveTrader must NOT replace our simulated
        # capital with the actual wallet balance.
        self.refresh_before_trade = False
