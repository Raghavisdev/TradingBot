import os

from trading.position import Position


class Portfolio:

    def __init__(self):

        self.positions = []

        self.closed_positions = []

        self.initial_balance = float(
            os.getenv("PAPER_INITIAL_BALANCE", "100.0")
        )

        self.cash = self.initial_balance

        self.total_profit = 0.0

        # Risk Settings
        self.max_open_positions = 10
        self.minimum_cash = 10.0

        # Peak equity tracking for S6 compatibility
        self._peak_val = self.initial_balance

    # ==========================================
    # ADD POSITION
    # ==========================================

    def add_position(self, position: Position):

        self.positions.append(position)
        self.update_peak_equity()

    # ==========================================
    # CLOSE POSITION
    # ==========================================

    def close_position(self, position: Position):

        if position in self.positions:

            self.positions.remove(position)

            self.closed_positions.append(position)

            # Portfolio profit must use the net realized result
            # after execution costs when available.
            net_profit = float(
                getattr(
                    position,
                    "net_realized_pnl",
                    position.pnl_dollars,
                )
                or 0.0
            )

            self.total_profit += net_profit
            self.update_peak_equity()

    # ==========================================
    # OPEN POSITIONS
    # ==========================================

    def get_open_positions(self):

        return [
            p
            for p in self.positions
            if p.status == "OPEN"
        ]

    # ==========================================
    # DUPLICATE CHECK
    # ==========================================

    def has_position(self, contract):

        for position in self.get_open_positions():

            if position.contract == contract:
                return True

        return False

    # ==========================================
    # CAN OPEN NEW TRADE
    # ==========================================

    def can_open_trade(self, amount):

        if len(self.get_open_positions()) >= self.max_open_positions:
            return False

        if self.cash - amount < self.minimum_cash:
            return False

        return True

    # ==========================================
    # PORTFOLIO VALUE
    # ==========================================

    def portfolio_value(self):

        total = self.cash

        for position in self.get_open_positions():

            total += (
                position.invested_amount +
                position.pnl_dollars
            )

        return round(total, 2)

    # ==========================================
    # ROI
    # ==========================================

    def roi(self):

        return (
            (self.portfolio_value() - self.initial_balance)
            / self.initial_balance
        ) * 100

    # ==========================================
    # PRINT
    # ==========================================

    def __str__(self):

        return f"""
==================================================
PORTFOLIO
==================================================

Initial Balance   : ${self.initial_balance:.2f}

Cash              : ${self.cash:.2f}

Portfolio Value   : ${self.portfolio_value():.2f}

ROI               : {self.roi():.2f}%

Total Profit      : ${self.total_profit:.2f}

Open Trades       : {len(self.get_open_positions())}

Closed Trades     : {len(self.closed_positions)}

==================================================
"""

    # ==========================================
    # S6 API COMPATIBILITY BRIDGES
    # ==========================================

    def update_peak_equity(self):
        """Explicitly update the peak equity value to the current portfolio value if it is a new high."""
        val = self.portfolio_value()
        if val > self._peak_val:
            self._peak_val = val

    @property
    def _peak_equity(self):
        """Read-only property returning the tracked peak equity without side effects."""
        return self._peak_val

    @property
    def total_equity(self):
        """Compatibility bridge to return current total portfolio value."""
        return self.portfolio_value()

    @property
    def initial_cash(self):
        """Compatibility bridge to return starting balance."""
        return self.initial_balance

    def can_open(self, amount):
        """Compatibility bridge to delegate to can_open_trade."""
        return self.can_open_trade(amount)