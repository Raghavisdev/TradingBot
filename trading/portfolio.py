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

    # ==========================================
    # ADD POSITION
    # ==========================================

    def add_position(self, position: Position):

        self.positions.append(position)

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