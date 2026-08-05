from datetime import datetime


class Position:

    def __init__(self):

                # ==========================================
        # HISTORY
        # ==========================================

        self.market_cap_history = []

        self.price_history = []

        self.health_history = []

        self.liquidity_history = []

        self.volume_history = []

        self.buy_ratio_history = []

        self.sell_time = None

        self.holding_time = 0
        
        # ==========================================
        # AI ENGINE
        # ==========================================

        self.market_health = 0
        self.market_health_breakdown = {}

        self.exit_confidence = 0
        self.exit_reason = ""

        self.recommended_action = "HOLD"

        self.health_history = []
        # ==========================================
        # MARKET HEALTH AI
        # ==========================================

        self.market_health = 0

        self.market_health_breakdown = {}

        # ==========================================
        # COIN INFORMATION
        # ==========================================

        self.symbol = ""
        self.contract = ""

        # ==========================================
        # ENTRY INFORMATION
        # ==========================================

        self.buy_time = datetime.now()

        self.entry_price = 0.0
        self.entry_market_cap = 0.0

        self.invested_amount = 0.0
        self.tokens = 0.0

        # ==========================================
        # LIVE MARKET
        # ==========================================

        self.current_price = 0.0
        self.current_market_cap = 0.0

        self.highest_price = 0.0
        self.highest_market_cap = 0.0

        self.lowest_price = 0.0
        self.lowest_market_cap = 0.0

        self.liquidity = 0.0

        self.volume_5m = 0.0
        self.volume_1h = 0.0
        self.volume_24h = 0.0

        self.buys_5m = 0
        self.sells_5m = 0

        # ==========================================
        # PROFIT
        # ==========================================

        self.pnl_percent = 0.0
        self.pnl_dollars = 0.0

        self.highest_profit = 0.0

        self.realized_profit = 0.0
        self.unrealized_profit = 0.0

        # ==========================================
        # POSITION
        # ==========================================

        self.remaining_percent = 100
        self.sold_percent = 0

        self.status = "OPEN"

        # ==========================================
        # RISK
        # ==========================================

        self.stop_loss = -50
        self.trailing_stop = 20

    # ===================================================
    # Initialize Position (Call Once After Buying)
    # ===================================================

    def initialize(self):

        self.current_price = self.entry_price
        self.current_market_cap = self.entry_market_cap

        self.highest_price = self.entry_price
        self.highest_market_cap = self.entry_market_cap

        self.lowest_price = self.entry_price
        self.lowest_market_cap = self.entry_market_cap

        self.pnl_percent = 0
        self.pnl_dollars = 0
        self.highest_profit = 0

    # ===================================================
    # Update Live Market
    # ===================================================

    def update_price(self, price, market_cap):

        price = float(price)
        market_cap = float(market_cap)

        self.current_price = price
        self.current_market_cap = market_cap

        # Highest Price

        if price > self.highest_price:
            self.highest_price = price

        # Lowest Price

        if price < self.lowest_price:
            self.lowest_price = price

        # Highest MC

        if market_cap > self.highest_market_cap:
            self.highest_market_cap = market_cap

        # Lowest MC

        if market_cap < self.lowest_market_cap:
            self.lowest_market_cap = market_cap

        # Avoid division by zero

        if self.entry_price <= 0:
            return

        # Profit %

        self.pnl_percent = (
            (price - self.entry_price)
            / self.entry_price
        ) * 100

        # Profit $

        self.pnl_dollars = (
            self.invested_amount
            * self.pnl_percent
            / 100
        )

        # Highest Profit Ever

        if self.pnl_percent > self.highest_profit:
            self.highest_profit = self.pnl_percent

    # ===================================================
    # Print Position
    # ===================================================

    def __str__(self):

        return f"""
========================================================
POSITION
========================================================

Coin                : {self.symbol}

Contract            : {self.contract}

Status              : {self.status}

--------------------------------------------------------

Investment          : ${self.invested_amount:.2f}

Entry Price         : ${self.entry_price:.10f}

Current Price       : ${self.current_price:.10f}

--------------------------------------------------------

Entry MC            : ${self.entry_market_cap:,.0f}

Current MC          : ${self.current_market_cap:,.0f}

Highest MC          : ${self.highest_market_cap:,.0f}

Lowest MC           : ${self.lowest_market_cap:,.0f}

--------------------------------------------------------

Liquidity           : ${self.liquidity:,.2f}

Volume (5m)         : ${self.volume_5m:,.2f}

Buys (5m)           : {self.buys_5m}

Sells (5m)          : {self.sells_5m}

--------------------------------------------------------

PnL                 : {self.pnl_percent:.2f}%

PnL ($)             : ${self.pnl_dollars:.2f}

Highest Profit      : {self.highest_profit:.2f}%

--------------------------------------------------------

Remaining Position  : {self.remaining_percent}%

Sold                : {self.sold_percent}%

========================================================
"""