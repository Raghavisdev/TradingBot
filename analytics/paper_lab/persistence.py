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
import threading
from functools import wraps
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.abspath(os.path.join(_HERE, "..", "..", "database", "trading.db"))


def _synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class PaperLabPersistence:
    """Manages SQLite storage for Paper Lab trades, partial sells, equity, and forward metadata."""

    def __init__(self, db_path=None):
        self.db_path = db_path or _DB_PATH
        self._lock = threading.RLock()

        self._conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row

        cur = self._conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA busy_timeout=30000;")
        finally:
            cur.close()

        self._init_metadata_table()

    def _get_conn(self):
        return self._conn

    def _init_metadata_table(self):
        """Creates paper_lab_s6_forward_metadata and new forward ledger tables if they do not exist."""
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS paper_lab_s6_forward_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT UNIQUE,
                    signal_id TEXT,
                    experiment_id TEXT,
                    run_type TEXT DEFAULT 'forward',
                    timestamp REAL,
                    symbol TEXT,
                    contract TEXT,
                    entry_price REAL,
                    final_score REAL,
                    gt_score REAL,
                    liquidity REAL,
                    effective_entry_mc REAL,
                    buys INTEGER,
                    sells INTEGER,
                    buy_sell_ratio REAL,
                    computed_Q REAL,
                    base_allocation REAL,
                    multiplier REAL,
                    final_allocation REAL,
                    portfolio_equity REAL,
                    deployed_capital REAL,
                    entry_reason TEXT,
                    created_at REAL
                );
            """)
            
            # 1. Forward Signal Ledger
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forward_signal_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    timestamp REAL,
                    symbol TEXT,
                    contract TEXT,
                    final_score REAL,
                    gt_score REAL,
                    liquidity REAL,
                    buys INTEGER,
                    sells INTEGER,
                    effective_entry_mc REAL,
                    current_price REAL,
                    portfolio_equity_before REAL,
                    cash_before REAL,
                    active_s6_exposure REAL,
                    requested_amount REAL,
                    final_amount REAL,
                    all_sizing_inputs TEXT,
                    sizing_formula_version TEXT,
                    experiment_id TEXT,
                    strategy_id TEXT
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fsl_sig_id ON forward_signal_ledger(signal_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fsl_ts ON forward_signal_ledger(timestamp);")
            
            # 2. Forward Execution Ledger
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forward_execution_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT,
                    timestamp REAL,
                    quote_1 REAL,
                    quote_2 REAL,
                    quoted_price REAL,
                    executable_price REAL,
                    deterioration REAL,
                    attempt_count INTEGER,
                    failure_class TEXT,
                    retry_eligible INTEGER,
                    execution_result TEXT,
                    execution_price REAL,
                    execution_source TEXT,
                    fees REAL,
                    slippage REAL,
                    network_fee REAL,
                    commission REAL,
                    experiment_id TEXT,
                    strategy_id TEXT
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fel_trade_id ON forward_execution_ledger(trade_id);")
            
            # 3. Forward Tick Ledger
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forward_tick_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT,
                    timestamp REAL,
                    price REAL,
                    market_cap REAL,
                    liquidity REAL,
                    volume REAL,
                    buys INTEGER,
                    sells INTEGER,
                    hwm REAL,
                    current_retracement REAL,
                    strategy_state TEXT,
                    experiment_id TEXT,
                    strategy_id TEXT
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ftl_trade_id ON forward_tick_ledger(trade_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ftl_ts ON forward_tick_ledger(timestamp);")
            
            # 4. Forward Exit Ledger
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forward_exit_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT,
                    exit_timestamp REAL,
                    exit_price REAL,
                    hwm REAL,
                    trailing_threshold REAL,
                    retracement REAL,
                    exit_reason TEXT,
                    profit_booking_state TEXT,
                    gross_proceeds REAL,
                    entry_costs REAL,
                    exit_costs REAL,
                    network_fees REAL,
                    commission REAL,
                    net_pnl REAL,
                    experiment_id TEXT,
                    strategy_id TEXT
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fexl_trade_id ON forward_exit_ledger(trade_id);")
            
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"[PAPER LAB PERSISTENCE] Metadata table setup notice: {e}")

    @_synchronized
    def save_forward_signal(self, sig_dict):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO forward_signal_ledger (
                    signal_id, timestamp, symbol, contract, final_score, gt_score, liquidity, 
                    buys, sells, effective_entry_mc, current_price, portfolio_equity_before, 
                    cash_before, active_s6_exposure, requested_amount, final_amount, 
                    all_sizing_inputs, sizing_formula_version, experiment_id, strategy_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sig_dict.get('signal_id'), sig_dict.get('timestamp'), sig_dict.get('symbol'), sig_dict.get('contract'),
                sig_dict.get('final_score'), sig_dict.get('gt_score'), sig_dict.get('liquidity'),
                sig_dict.get('buys'), sig_dict.get('sells'), sig_dict.get('effective_entry_mc'),
                sig_dict.get('current_price'), sig_dict.get('portfolio_equity_before'),
                sig_dict.get('cash_before'), sig_dict.get('active_s6_exposure'),
                sig_dict.get('requested_amount'), sig_dict.get('final_amount'),
                sig_dict.get('all_sizing_inputs'), sig_dict.get('sizing_formula_version'),
                sig_dict.get('experiment_id'), sig_dict.get('strategy_id')
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_forward_signal failed: {e}")
        finally:
            cur.close()

    @_synchronized
    def save_forward_execution(self, exec_dict):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO forward_execution_ledger (
                    trade_id, timestamp, quote_1, quote_2, quoted_price, executable_price,
                    deterioration, attempt_count, failure_class, retry_eligible, execution_result,
                    execution_price, execution_source, fees, slippage, network_fee, commission,
                    experiment_id, strategy_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exec_dict.get('trade_id'), exec_dict.get('timestamp', time.time()), exec_dict.get('quote_1'),
                exec_dict.get('quote_2'), exec_dict.get('quoted_price'), exec_dict.get('executable_price'),
                exec_dict.get('deterioration'), exec_dict.get('attempt_count'), exec_dict.get('failure_class'),
                1 if exec_dict.get('retry_eligible') else 0, exec_dict.get('execution_result'),
                exec_dict.get('execution_price'), exec_dict.get('execution_source'),
                exec_dict.get('fees'), exec_dict.get('slippage'), exec_dict.get('network_fee'),
                exec_dict.get('commission', 0.0), exec_dict.get('experiment_id'), exec_dict.get('strategy_id')
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_forward_execution failed: {e}")
        finally:
            cur.close()

    @_synchronized
    def save_forward_tick(self, tick_dict):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO forward_tick_ledger (
                    trade_id, timestamp, price, market_cap, liquidity, volume, buys, sells,
                    hwm, current_retracement, strategy_state, experiment_id, strategy_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tick_dict.get('trade_id'), tick_dict.get('timestamp', time.time()), tick_dict.get('price'),
                tick_dict.get('market_cap'), tick_dict.get('liquidity'), tick_dict.get('volume'),
                tick_dict.get('buys'), tick_dict.get('sells'), tick_dict.get('hwm'),
                tick_dict.get('current_retracement'), tick_dict.get('strategy_state'),
                tick_dict.get('experiment_id'), tick_dict.get('strategy_id')
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_forward_tick failed: {e}")
        finally:
            cur.close()

    @_synchronized
    def save_forward_exit(self, exit_dict):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO forward_exit_ledger (
                    trade_id, exit_timestamp, exit_price, hwm, trailing_threshold,
                    retracement, exit_reason, profit_booking_state, gross_proceeds,
                    entry_costs, exit_costs, network_fees, commission, net_pnl,
                    experiment_id, strategy_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exit_dict.get('trade_id'), exit_dict.get('exit_timestamp', time.time()),
                exit_dict.get('exit_price'), exit_dict.get('hwm'), exit_dict.get('trailing_threshold'),
                exit_dict.get('retracement'), exit_dict.get('exit_reason'), exit_dict.get('profit_booking_state'),
                exit_dict.get('gross_proceeds'), exit_dict.get('entry_costs'), exit_dict.get('exit_costs'),
                exit_dict.get('network_fees'), exit_dict.get('commission', 0.0), exit_dict.get('net_pnl'),
                exit_dict.get('experiment_id'), exit_dict.get('strategy_id')
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_forward_exit failed: {e}")
        finally:
            cur.close()

    # ============================================================
    # TRADES PERSISTENCE
    # ============================================================

    @_synchronized
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

    @_synchronized
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

    @_synchronized
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

    @_synchronized
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

    # ============================================================
    # RECOVERY & FETCH
    # ============================================================

    @_synchronized
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

    @_synchronized
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

    @_synchronized
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

    @_synchronized
    def save_s6_forward_metadata(self, meta_dict):
        """
        Saves forward S6 entry metadata audit row into paper_lab_s6_forward_metadata.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        now = time.time()
        try:
            cur.execute("""
                INSERT OR REPLACE INTO paper_lab_s6_forward_metadata (
                    trade_id, signal_id, experiment_id, run_type, timestamp,
                    symbol, contract, entry_price, final_score, gt_score,
                    liquidity, effective_entry_mc, buys, sells, buy_sell_ratio,
                    computed_Q, base_allocation, multiplier, final_allocation,
                    portfolio_equity, deployed_capital, entry_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                meta_dict.get("trade_id"),
                meta_dict.get("signal_id"),
                meta_dict.get("experiment_id", "S6_V12_FORWARD_DEFAULT"),
                meta_dict.get("run_type", "forward"),
                meta_dict.get("timestamp", now),
                meta_dict.get("symbol"),
                meta_dict.get("contract", ""),
                meta_dict.get("entry_price"),
                meta_dict.get("final_score"),
                meta_dict.get("gt_score"),
                meta_dict.get("liquidity"),
                meta_dict.get("effective_entry_mc"),
                meta_dict.get("buys"),
                meta_dict.get("sells"),
                meta_dict.get("buy_sell_ratio"),
                meta_dict.get("computed_Q"),
                meta_dict.get("base_allocation"),
                meta_dict.get("multiplier"),
                meta_dict.get("final_allocation"),
                meta_dict.get("portfolio_equity"),
                meta_dict.get("deployed_capital"),
                meta_dict.get("entry_reason", "Qualified S6 Entry"),
                now
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PAPER LAB PERSISTENCE ERROR] save_s6_forward_metadata failed: {e}")
        finally:
            cur.close()


    @_synchronized
    def close(self):
        """Close the persistent Paper Lab SQLite connection."""
        with self._lock:
            if getattr(self, "_conn", None) is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None
