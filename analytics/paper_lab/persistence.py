"""
analytics/paper_lab/persistence.py
------------------------------------
SQLite Persistence layer for Paper Lab (Phase 3).

Saves and updates:
  - paper_lab_trades
  - paper_lab_partial_sells
  - paper_lab_equity

Does NOT modify paper_trades, signals, snapshots, outcomes, or intelligence.
Uses SQLite WAL mode and busy timeouts for thread-safe operations.
"""

import sqlite3
import time
import os
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.abspath(os.path.join(_HERE, "..", "..", "database", "trading.db"))


class PaperLabPersistence:
    """Manages SQLite storage for Paper Lab trades, partial sells, and equity."""

    def __init__(self, db_path=None):
        self.db_path = db_path or _DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA busy_timeout=30000;")
        finally:
            cur.close()
        return conn

    # ============================================================
    # TRADES PERSISTENCE
    # ============================================================

    def save_trade_open(self, trade_dict):
        """
        Saves a new open trade to paper_lab_trades table.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        now = time.time()
        try:
            cur.execute("""
                INSERT OR REPLACE INTO paper_lab_trades (
                    trade_id, strategy_id, strategy_version, signal_id,
                    symbol, contract, status, entry_time, entry_price,
                    entry_market_cap, invested, tokens, remaining_pct,
                    exit_time, exit_price, exit_market_cap, exit_reason,
                    realized_pnl, realized_pct, mfe, mae, fees, slippage,
                    fired_levels, highest_stop_pnl, peak_multiple, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_dict.get("trade_id"),
                trade_dict.get("strategy_id"),
                trade_dict.get("strategy_version", "1.0"),
                trade_dict.get("signal_id"),
                trade_dict.get("symbol"),
                trade_dict.get("contract", ""),
                trade_dict.get("status", "OPEN"),
                trade_dict.get("entry_time"),
                trade_dict.get("entry_price"),
                trade_dict.get("entry_market_cap"),
                trade_dict.get("invested"),
                trade_dict.get("tokens", 0.0),
                trade_dict.get("remaining_pct", 100.0),
                trade_dict.get("exit_time"),
                trade_dict.get("exit_price"),
                trade_dict.get("exit_market_cap"),
                trade_dict.get("exit_reason", ""),
                trade_dict.get("realized_pnl", 0.0),
                trade_dict.get("realized_pct", 0.0),
                trade_dict.get("mfe", 0.0),
                trade_dict.get("mae", 0.0),
                trade_dict.get("fees", 0.0),
                trade_dict.get("slippage", 0.0),
                trade_dict.get("fired_levels", ""),
                trade_dict.get("highest_stop_pnl", -20.0),
                trade_dict.get("peak_multiple", 1.0),
                now
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_trade_open failed: {e}")
            raise e
        finally:
            cur.close()
            conn.close()

    def update_trade(self, trade_dict):
        """
        Updates an existing trade row in paper_lab_trades.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        now = time.time()
        try:
            cur.execute("""
                UPDATE paper_lab_trades
                SET status = ?,
                    remaining_pct = ?,
                    exit_time = ?,
                    exit_price = ?,
                    exit_market_cap = ?,
                    exit_reason = ?,
                    realized_pnl = ?,
                    realized_pct = ?,
                    mfe = ?,
                    mae = ?,
                    fired_levels = ?,
                    highest_stop_pnl = ?,
                    peak_multiple = ?,
                    updated_at = ?
                WHERE trade_id = ?
            """, (
                trade_dict.get("status"),
                trade_dict.get("remaining_pct"),
                trade_dict.get("exit_time"),
                trade_dict.get("exit_price"),
                trade_dict.get("exit_market_cap"),
                trade_dict.get("exit_reason"),
                trade_dict.get("realized_pnl"),
                trade_dict.get("realized_pct"),
                trade_dict.get("mfe"),
                trade_dict.get("mae"),
                trade_dict.get("fired_levels", ""),
                trade_dict.get("highest_stop_pnl", -20.0),
                trade_dict.get("peak_multiple", 1.0),
                now,
                trade_dict.get("trade_id")
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] update_trade failed: {e}")
            raise e
        finally:
            cur.close()
            conn.close()

    def save_partial_sell(self, partial_dict):
        """
        Saves a partial sell event to paper_lab_partial_sells table.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO paper_lab_partial_sells (
                    trade_id, signal_id, strategy_id, sell_time, sell_price,
                    sell_market_cap, percent_sold, proceeds, partial_pnl,
                    partial_pct, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                partial_dict.get("trade_id"),
                partial_dict.get("signal_id"),
                partial_dict.get("strategy_id"),
                partial_dict.get("sell_time"),
                partial_dict.get("sell_price"),
                partial_dict.get("sell_market_cap"),
                partial_dict.get("percent_sold"),
                partial_dict.get("proceeds"),
                partial_dict.get("partial_pnl"),
                partial_dict.get("partial_pct"),
                partial_dict.get("exit_reason")
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_partial_sell failed: {e}")
            raise e
        finally:
            cur.close()
            conn.close()

    def save_equity_snapshot(self, strategy_id, cash, position_value, equity, ts=None):
        """
        Saves a point-in-time equity snapshot for a strategy.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        ts = ts or time.time()
        try:
            cur.execute("""
                INSERT INTO paper_lab_equity (strategy_id, timestamp, cash, position_value, equity)
                VALUES (?, ?, ?, ?, ?)
            """, (strategy_id, ts, cash, position_value, equity))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_equity_snapshot failed: {e}")
        finally:
            cur.close()
            conn.close()

    # ============================================================
    # RECOVERY & FETCH
    # ============================================================

    def load_open_trades(self):
        """
        Loads all trades with status = 'OPEN' from paper_lab_trades across all strategies.
        Returns list of dicts.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM paper_lab_trades WHERE status = 'OPEN'")
            rows = [dict(r) for r in cur.fetchall()]
            return rows
        finally:
            cur.close()
            conn.close()

    def load_all_trades(self):
        """
        Loads all trades from paper_lab_trades table.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM paper_lab_trades ORDER BY id ASC")
            rows = [dict(r) for r in cur.fetchall()]
            return rows
        finally:
            cur.close()
            conn.close()

    def load_traded_signal_ids(self):
        """
        Returns a dict mapping strategy_id -> set of signal_ids that have EVER had a trade created.
        Used on startup to restore has_traded_signal status for each strategy.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        result = {}
        try:
            cur.execute("SELECT DISTINCT strategy_id, signal_id FROM paper_lab_trades")
            for row in cur.fetchall():
                strat = row["strategy_id"]
                sig   = row["signal_id"]
                if strat not in result:
                    result[strat] = set()
                result[strat].add(sig)
            return result
        finally:
            cur.close()
            conn.close()
