"""
Trade Logger
-------------
Handles all SQLite reads/writes for the paper trading persistence layer.

Tables managed:
    paper_trades          — one row per open position; updated in-place
    paper_partial_sells   — append-only; one row per partial exit event

Follows the exact same SQLite connection pattern used by SignalLogger,
SnapshotLogger, OutcomeLogger, and IntelligenceLogger.

Version:  1.0
"""

import time
import logging
import sqlite3

from config import DATABASE

logger = logging.getLogger("TradeLogger")


class TradeLogger:

    def __init__(self):

        self.connection = sqlite3.connect(
            DATABASE,
            timeout=30.0,
            check_same_thread=False
        )

        init_cursor = self.connection.cursor()
        try:
            init_cursor.execute("PRAGMA journal_mode=WAL;")
            init_cursor.execute("PRAGMA busy_timeout=30000;")
        finally:
            init_cursor.close()

    # ==================================================
    # OPEN TRADE
    # Called immediately when a paper buy is executed.
    # ==================================================

    def open_trade(self, position) -> bool:
        """
        Inserts a new OPEN row into paper_trades.
        Returns True on success, False on failure.
        """
        cursor = self.connection.cursor()
        try:
            now = time.time()
            cursor.execute("""
            INSERT OR IGNORE INTO paper_trades(
                trade_id,
                strategy_id,
                strategy_version,
                signal_id,
                symbol,
                contract,
                status,
                entry_time,
                entry_price,
                entry_market_cap,
                invested,
                tokens,
                remaining_pct,
                exit_time,
                exit_price,
                exit_market_cap,
                exit_reason,
                realized_pnl,
                realized_pct,
                mfe,
                mae,
                fees,
                slippage,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                getattr(position, "trade_id",         None),
                getattr(position, "strategy_id",      "default"),
                getattr(position, "strategy_version", "1.0"),
                getattr(position, "signal_id",        None),
                getattr(position, "symbol",           None),
                getattr(position, "contract",         None),
                "OPEN",
                getattr(position, "entry_time",       now),
                getattr(position, "entry_price",      0.0),
                getattr(position, "entry_market_cap", 0.0),
                getattr(position, "invested_amount",  0.0),
                getattr(position, "tokens",           0.0),
                100.0,   # remaining_pct — starts at 100
                None,    # exit_time  — NULL until closed
                None,    # exit_price — NULL until closed
                None,    # exit_market_cap — NULL until closed
                None,    # exit_reason — NULL until closed
                0.0,     # realized_pnl
                0.0,     # realized_pct
                0.0,     # mfe
                0.0,     # mae
                0.0,     # fees (reserved)
                0.0,     # slippage (reserved)
                now,
            ))
            self.connection.commit()
            logger.info(
                "[PAPER BUY] %s | trade_id=%s | invested=$%.2f | entry=$%.8f | MC=$%,.0f",
                getattr(position, "symbol", "?"),
                getattr(position, "trade_id", "?"),
                getattr(position, "invested_amount", 0.0),
                getattr(position, "entry_price", 0.0),
                getattr(position, "entry_market_cap", 0.0),
            )
            return True

        except Exception as e:
            self.connection.rollback()
            logger.error("[TRADE LOGGER] open_trade failed for %s: %s",
                         getattr(position, "symbol", "?"), e)
            return False

        finally:
            cursor.close()

    # ==================================================
    # RECORD PARTIAL SELL
    # Appends a row to paper_partial_sells and updates
    # paper_trades in a single transaction.
    # ==================================================

    def record_partial_sell(self, position, percent: float, proceeds: float,
                            partial_pnl: float, exit_reason: str) -> bool:
        """
        Persists a partial sell event.
        Returns True on success, False on failure.
        """
        trade_id    = getattr(position, "trade_id",    None)
        signal_id   = getattr(position, "signal_id",   None)
        strategy_id = getattr(position, "strategy_id", "default")
        symbol      = getattr(position, "symbol",      "?")

        if not trade_id:
            logger.warning("[TRADE LOGGER] record_partial_sell: trade_id missing for %s", symbol)
            return False

        cursor = self.connection.cursor()
        try:
            now = time.time()

            # Compute partial_pct: return % on the slice being sold
            invested   = getattr(position, "invested_amount", 0.0) or 0.0
            slice_cost = invested * percent / 100.0
            partial_pct = (partial_pnl / slice_cost * 100.0) if slice_cost > 0 else 0.0

            # Current market cap for the sell snapshot
            sell_mc = (
                getattr(position, "current_market_cap", None) or
                getattr(position, "entry_market_cap", 0.0)
            )

            # 1. Append to paper_partial_sells
            cursor.execute("""
            INSERT INTO paper_partial_sells(
                trade_id,
                signal_id,
                strategy_id,
                sell_time,
                sell_price,
                sell_market_cap,
                percent_sold,
                proceeds,
                partial_pnl,
                partial_pct,
                exit_reason
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trade_id,
                signal_id,
                strategy_id,
                now,
                getattr(position, "current_price",    0.0),
                sell_mc,
                percent,
                proceeds,
                partial_pnl,
                partial_pct,
                exit_reason,
            ))

            # 2. Update parent trade row atomically
            new_remaining = max(0.0, getattr(position, "remaining_percent", 100.0))
            new_realized  = getattr(position, "realized_profit", 0.0)
            mfe           = getattr(position, "mfe", 0.0)
            mae           = getattr(position, "mae", 0.0)

            cursor.execute("""
            UPDATE paper_trades
               SET remaining_pct = ?,
                   realized_pnl  = ?,
                   mfe           = ?,
                   mae           = ?,
                   updated_at    = ?
             WHERE trade_id = ?
            """, (new_remaining, new_realized, mfe, mae, now, trade_id))

            self.connection.commit()

            logger.info(
                "[PAPER PARTIAL SELL] %s | trade_id=%s | sold=%.0f%% "
                "| proceeds=$%.2f | pnl=$%.2f (%.1f%%)",
                symbol, trade_id, percent, proceeds, partial_pnl, partial_pct,
            )
            return True

        except Exception as e:
            self.connection.rollback()
            logger.error("[TRADE LOGGER] record_partial_sell failed for %s: %s", symbol, e)
            return False

        finally:
            cursor.close()

    # ==================================================
    # CLOSE TRADE
    # Called on a full sell (sell_all).
    # Finalises the paper_trades row: status = CLOSED.
    # ==================================================

    def close_trade(self, position, exit_reason: str) -> bool:
        """
        Marks a paper_trades row as CLOSED.
        Returns True on success, False on failure.
        """
        trade_id = getattr(position, "trade_id", None)
        symbol   = getattr(position, "symbol",   "?")

        if not trade_id:
            logger.warning("[TRADE LOGGER] close_trade: trade_id missing for %s", symbol)
            return False

        cursor = self.connection.cursor()
        try:
            now = time.time()

            exit_mc = (
                getattr(position, "current_market_cap", None) or
                getattr(position, "entry_market_cap", 0.0)
            )

            realized_pnl = getattr(position, "realized_profit", 0.0)
            invested     = getattr(position, "invested_amount",  0.0) or 0.0
            realized_pct = (realized_pnl / invested * 100.0) if invested > 0 else 0.0

            mfe = getattr(position, "mfe", 0.0)
            mae = getattr(position, "mae", 0.0)

            cursor.execute("""
            UPDATE paper_trades
               SET status          = 'CLOSED',
                   exit_time       = ?,
                   exit_price      = ?,
                   exit_market_cap = ?,
                   exit_reason     = ?,
                   realized_pnl    = ?,
                   realized_pct    = ?,
                   remaining_pct   = 0.0,
                   mfe             = ?,
                   mae             = ?,
                   updated_at      = ?
             WHERE trade_id = ?
            """, (
                now,
                getattr(position, "current_price", 0.0),
                exit_mc,
                exit_reason,
                realized_pnl,
                realized_pct,
                mfe,
                mae,
                now,
                trade_id,
            ))

            self.connection.commit()

            holding_mins = getattr(position, "holding_time", 0.0) or 0.0
            logger.info(
                "[PAPER SELL] %s | trade_id=%s | pnl=$%.2f (%.1f%%) "
                "| held=%.1f min | reason=%s",
                symbol, trade_id, realized_pnl, realized_pct,
                holding_mins, exit_reason,
            )
            return True

        except Exception as e:
            self.connection.rollback()
            logger.error("[TRADE LOGGER] close_trade failed for %s: %s", symbol, e)
            return False

        finally:
            cursor.close()

    # ==================================================
    # GET OPEN TRADES — for startup recovery
    # ==================================================

    def get_open_trades(self, strategy_id: str = "default") -> list:
        """
        Returns all OPEN paper_trades rows for a given strategy as dicts.
        Used by TradeManager.recover_open_positions() on startup.
        """
        self.connection.row_factory = sqlite3.Row
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
            SELECT * FROM paper_trades
             WHERE status      = 'OPEN'
               AND strategy_id = ?
             ORDER BY entry_time ASC
            """, (strategy_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("[TRADE LOGGER] get_open_trades failed: %s", e)
            return []
        finally:
            cursor.close()

    # ==================================================
    # UPDATE MFE / MAE
    # Called periodically by TradeManager while a position
    # is open, to track best / worst excursion in the DB.
    # Non-critical — errors are suppressed.
    # ==================================================

    def update_mfe_mae(self, trade_id: str, mfe: float, mae: float) -> None:
        """Updates mfe and mae columns on the paper_trades row."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
            UPDATE paper_trades
               SET mfe        = ?,
                   mae        = ?,
                   updated_at = ?
             WHERE trade_id = ?
            """, (mfe, mae, time.time(), trade_id))
            self.connection.commit()
        except Exception as e:
            logger.warning("[TRADE LOGGER] update_mfe_mae failed for %s: %s", trade_id, e)
        finally:
            cursor.close()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):
        self.connection.close()
