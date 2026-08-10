"""
analytics/paper_lab/lab_portfolio.py
--------------------------------------
Isolated simulation portfolio and position tracking for Paper Lab (Phase 3).

Classes:
    LabPosition   - active or closed paper position for a strategy
    LabPortfolio  - strategy portfolio ($100 starting capital, cash, trades, equity)
"""

import time
import uuid


class LabPosition:
    """
    Represents one paper position inside the Paper Lab.
    """

    def __init__(self, trade_id, strategy_id, strategy_version, signal_id,
                 symbol, contract, entry_time, entry_price, entry_mc, invested):

        self.trade_id         = trade_id or f"LAB_{strategy_id}_{uuid.uuid4().hex[:8]}"
        self.strategy_id      = strategy_id
        self.strategy_version = strategy_version or "1.0"
        self.signal_id        = signal_id
        self.symbol           = symbol
        self.contract         = contract or ""

        # Entry state
        self.entry_time  = float(entry_time or time.time())
        self.entry_price = float(entry_price or 0.0)
        self.entry_mc    = float(entry_mc or 0.0)
        self.invested    = float(invested or 0.0)

        # Tokens bought
        self.tokens = self.invested / self.entry_price if self.entry_price > 0 else 0.0

        # Live state
        self.current_price = self.entry_price
        self.current_mc    = self.entry_mc
        self.current_time  = self.entry_time

        # Partial sell tracking
        self.remaining_pct = 100.0
        self.realized_pnl  = 0.0
        self.partial_sells = []

        # Excursions & Trailing peak
        self.mfe              = 0.0
        self.mae              = 0.0
        self.highest_pnl_pct  = 0.0

        # Exit state
        self.status      = "OPEN"
        self.exit_time   = None
        self.exit_price  = None
        self.exit_mc     = None
        self.exit_reason = None

        # History for indicators/trends
        self.price_history     = [self.entry_price]
        self.health_history    = []
        self.volume_history    = []
        self.liquidity_history = []
        self.buy_ratio_history = []

    @property
    def pnl_pct(self):
        """Current unrealized P&L % on remaining portion."""
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price / self.entry_price - 1.0) * 100.0

    @property
    def pnl_dollars(self):
        """Current unrealized P&L in dollars on remaining portion."""
        remaining_cost = self.invested * (self.remaining_pct / 100.0)
        return remaining_cost * (self.pnl_pct / 100.0)

    @property
    def current_value(self):
        """Current value of remaining position."""
        remaining_cost = self.invested * (self.remaining_pct / 100.0)
        return remaining_cost + self.pnl_dollars

    @property
    def total_pnl(self):
        """Total P&L = realized + unrealized."""
        return self.realized_pnl + self.pnl_dollars

    @property
    def holding_seconds(self):
        end = self.exit_time or self.current_time
        return max(0.0, end - self.entry_time)

    def update_snapshot(self, snapshot):
        """Update position from a snapshot dict."""
        price = float(snapshot.get("price") or 0.0)
        mc    = float(snapshot.get("market_cap") or 0.0)
        ts    = float(snapshot.get("timestamp") or time.time())

        if price > 0:
            self.current_price = price
        if mc > 0:
            self.current_mc = mc
        if ts > 0:
            self.current_time = ts

        # Update MFE / MAE / Peak
        pnl = self.pnl_pct
        if pnl > self.mfe:
            self.mfe = pnl
        if pnl > self.highest_pnl_pct:
            self.highest_pnl_pct = pnl
        if pnl < self.mae:
            self.mae = pnl

        # History tracking
        health = float(snapshot.get("market_health") or 0.0)
        vol    = float(snapshot.get("volume") or 0.0)
        liq    = float(snapshot.get("liquidity") or 0.0)
        buys   = int(snapshot.get("buys") or 0)
        sells  = int(snapshot.get("sells") or 0)
        total  = buys + sells
        ratio  = (buys / total) if total > 0 else 0.5

        self.price_history.append(price)
        self.health_history.append(health)
        self.volume_history.append(vol)
        self.liquidity_history.append(liq)
        self.buy_ratio_history.append(ratio)

        for lst in [self.price_history, self.health_history, self.volume_history,
                    self.liquidity_history, self.buy_ratio_history]:
            if len(lst) > 30:
                del lst[0]

    def do_partial_sell(self, pct_of_remaining, reason, ts, price, mc):
        """Execute partial sell of pct_of_remaining %."""
        if pct_of_remaining <= 0 or self.remaining_pct <= 0:
            return None

        sell_frac = min(pct_of_remaining / 100.0, 1.0)
        slice_cost  = self.invested * (self.remaining_pct / 100.0) * sell_frac
        sell_price  = price if price > 0 else self.current_price
        sell_ratio  = sell_price / self.entry_price if self.entry_price > 0 else 1.0
        sold_value  = slice_cost * sell_ratio
        partial_pnl = sold_value - slice_cost
        partial_pct = (sell_ratio - 1.0) * 100.0

        self.remaining_pct -= self.remaining_pct * sell_frac
        self.realized_pnl  += partial_pnl

        record = {
            "trade_id":       self.trade_id,
            "signal_id":      self.signal_id,
            "strategy_id":    self.strategy_id,
            "sell_time":      ts,
            "sell_price":     sell_price,
            "sell_market_cap": mc if mc > 0 else self.current_mc,
            "percent_sold":   pct_of_remaining,
            "proceeds":       round(sold_value, 6),
            "sold_value":     round(sold_value, 6),
            "partial_pnl":    round(partial_pnl, 6),
            "partial_pct":    round(partial_pct, 4),
            "exit_reason":    reason,
        }
        self.partial_sells.append(record)
        return record

    def close(self, reason, ts, price, mc):
        """Close full remaining position."""
        if self.remaining_pct > 0:
            self.do_partial_sell(100.0, reason, ts, price, mc)
        self.status        = "CLOSED"
        self.exit_time     = ts
        self.exit_price    = price if price > 0 else self.current_price
        self.exit_mc       = mc if mc > 0 else self.current_mc
        self.exit_reason   = reason
        self.remaining_pct = 0.0

    def to_dict(self):
        """Returns dict matching database column layout."""
        realized_pct = (self.realized_pnl / self.invested * 100.0) if self.invested > 0 else 0.0
        return {
            "trade_id":         self.trade_id,
            "strategy_id":       self.strategy_id,
            "strategy_version":  self.strategy_version,
            "signal_id":        self.signal_id,
            "symbol":           self.symbol,
            "contract":         self.contract,
            "status":           self.status,
            "entry_time":       self.entry_time,
            "entry_price":      self.entry_price,
            "entry_market_cap": self.entry_mc,
            "invested":         round(self.invested, 4),
            "tokens":           round(self.tokens, 6),
            "remaining_pct":    round(self.remaining_pct, 4),
            "exit_time":        self.exit_time,
            "exit_price":       self.exit_price,
            "exit_market_cap":  self.exit_mc,
            "exit_reason":      self.exit_reason,
            "realized_pnl":     round(self.realized_pnl, 6),
            "realized_pct":     round(realized_pct, 4),
            "mfe":              round(self.mfe, 4),
            "mae":              round(self.mae, 4),
            "fees":             0.0,
            "slippage":         0.0,
        }


class LabPortfolio:
    """
    Isolated portfolio per strategy in Paper Lab.
    Starting cash = $100.00 by default.
    """

    def __init__(self, strategy_id, initial_cash=100.0, max_open=10, min_cash=2.0):
        self.strategy_id   = strategy_id
        self.initial_cash  = initial_cash
        self.cash          = initial_cash
        self.max_open      = max_open
        self.min_cash      = min_cash

        self.open_positions = []      # list of LabPosition
        self.closed_trades  = []      # list of trade dicts
        self.traded_signal_ids = set() # set of signal_ids ever traded by this strategy

        # Peak equity & max drawdown tracking
        self._peak_equity  = initial_cash
        self._max_drawdown = 0.0
        self.equity_curve  = [(time.time(), initial_cash)]

    def can_open(self, amount):
        """True if portfolio has room and cash for trade."""
        if len(self.open_positions) >= self.max_open:
            return False
        if self.cash - amount < self.min_cash:
            return False
        if amount <= 0:
            return False
        return True

    def has_position(self, signal_id):
        """Returns True if signal_id is currently open in open_positions."""
        return any(p.signal_id == signal_id for p in self.open_positions)

    def has_traded_signal(self, signal_id):
        """Returns True if signal_id has EVER had a position opened by this strategy."""
        return signal_id in self.traded_signal_ids

    def open_position(self, trade_id, strategy_version, signal_id, symbol,
                      contract, entry_time, entry_price, entry_mc, invested):
        """Open a new virtual position."""
        if not self.can_open(invested):
            return None

        pos = LabPosition(
            trade_id=trade_id,
            strategy_id=self.strategy_id,
            strategy_version=strategy_version,
            signal_id=signal_id,
            symbol=symbol,
            contract=contract,
            entry_time=entry_time,
            entry_price=entry_price,
            entry_mc=entry_mc,
            invested=invested
        )
        self.cash -= invested
        self.open_positions.append(pos)
        self.traded_signal_ids.add(signal_id)
        return pos

    def close_position(self, pos, reason, ts, price, mc):
        """Close full remaining position, return cash proceeds to portfolio."""
        pos.close(reason, ts, price, mc)
        last_sell = pos.partial_sells[-1] if pos.partial_sells else None
        if last_sell:
            self.cash += last_sell.get("proceeds", last_sell.get("sold_value", 0.0))

        if pos in self.open_positions:
            self.open_positions.remove(pos)
        self.closed_trades.append(pos.to_dict())
        return pos

    def close_position_by_partial_sell(self, pos, pct_of_remaining, reason, ts, price, mc):
        """Execute partial sell, add proceeds to cash."""
        record = pos.do_partial_sell(pct_of_remaining, reason, ts, price, mc)
        if record:
            self.cash += record["proceeds"]
        return record

    @property
    def total_position_value(self):
        """Sum of current values of all open positions."""
        return sum(p.current_value for p in self.open_positions)

    @property
    def total_equity(self):
        """Current total equity (cash + position values)."""
        return self.cash + self.total_position_value

    @property
    def max_drawdown_pct(self):
        return self._max_drawdown

    def record_equity(self, ts=None):
        """Update equity curve and max drawdown."""
        ts = ts or time.time()
        eq = self.total_equity
        self.equity_curve.append((ts, round(eq, 6)))

        if eq > self._peak_equity:
            self._peak_equity = eq
        if self._peak_equity > 0:
            dd = (self._peak_equity - eq) / self._peak_equity * 100.0
            if dd > self._max_drawdown:
                self._max_drawdown = dd
