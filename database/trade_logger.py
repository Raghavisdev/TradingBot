"""
Trade Logger
------------

Persistent paper/live-trade accounting layer.

Important distinction:

    strategy P&L
        = market-price based P&L used by trading logic

    realized net P&L
        = actual proceeds
          - allocated entry cost
          - execution fees
          - execution slippage

Fees and slippage are therefore accounting values and
are NOT treated as price impact.
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
            timeout=30,
            check_same_thread=False,
        )

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                "PRAGMA journal_mode=WAL;"
            )

            cursor.execute(
                "PRAGMA busy_timeout=30000;"
            )

            # LAPC-v2 schema migrations
            try: cursor.execute("ALTER TABLE paper_trades ADD COLUMN probe_entry_time REAL;")
            except Exception: pass

            try: cursor.execute("ALTER TABLE paper_trades ADD COLUMN probe_entry_market_cap REAL;")
            except Exception: pass

            try: cursor.execute("ALTER TABLE paper_trades ADD COLUMN scale_in_completed INTEGER DEFAULT 0;")
            except Exception: pass

            try: cursor.execute("ALTER TABLE paper_trades ADD COLUMN post_probe_snapshot_count INTEGER DEFAULT 0;")
            except Exception: pass

        finally:
            cursor.close()

    # ==================================================
    # OPEN TRADE
    # ==================================================

    def open_trade(self, position) -> bool:

        cursor = self.connection.cursor()

        try:

            now = time.time()

            cursor.execute(
                """
                INSERT OR IGNORE INTO paper_trades(
                    trade_id,
                    session_id,
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
                    cost_mode,
                    network_fee,
                    commission,
                    updated_at,
                    probe_entry_time,
                    probe_entry_market_cap,
                    scale_in_completed,
                    post_probe_snapshot_count
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    getattr(
                        position,
                        "trade_id",
                        None,
                    ),

                    __import__('os').getenv("PAPER_SESSION_ID", "S6_RUNTIME_PAPER"),

                    getattr(
                        position,
                        "strategy_id",
                        "default",
                    ),

                    getattr(
                        position,
                        "strategy_version",
                        "1.0",
                    ),

                    getattr(
                        position,
                        "signal_id",
                        None,
                    ),

                    getattr(
                        position,
                        "symbol",
                        None,
                    ),

                    getattr(
                        position,
                        "contract",
                        None,
                    ),

                    "OPEN",

                    getattr(
                        position,
                        "entry_time",
                        now,
                    ),

                    getattr(
                        position,
                        "entry_price",
                        0.0,
                    ),

                    getattr(
                        position,
                        "entry_market_cap",
                        0.0,
                    ),

                    getattr(
                        position,
                        "invested_amount",
                        0.0,
                    ),

                    getattr(
                        position,
                        "tokens",
                        0.0,
                    ),

                    100.0,

                    None,
                    None,
                    None,
                    None,

                    0.0,
                    0.0,

                    getattr(
                        position,
                        "mfe",
                        0.0,
                    ),

                    getattr(
                        position,
                        "mae",
                        0.0,
                    ),

                    # Total execution fees at entry.
                    getattr(
                        position,
                        "entry_fees",
                        0.0,
                    ),

                    # Entry execution slippage.
                    getattr(
                        position,
                        "entry_slippage",
                        0.0,
                    ),

                    getattr(
                        position,
                        "cost_mode",
                        "MODELED_COST",
                    ),

                    getattr(
                        position,
                        "network_fee",
                        0.0,
                    ),

                    getattr(
                        position,
                        "commission",
                        0.0,
                    ),

                    now,

                    getattr(position, "probe_entry_time", 0.0),
                    getattr(position, "probe_entry_market_cap", 0.0),
                    getattr(position, "scale_in_completed", 0),
                    getattr(position, "post_probe_snapshot_count", 0),
                ),
            )

            self.connection.commit()

            return True

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[TRADE LOGGER] open_trade failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # ==================================================
    # EXECUTION ACCOUNTING UPDATE
    # ==================================================

    def update_execution_costs(
        self,
        trade_id,
        fees=None,
        slippage=None,
    ) -> bool:

        cursor = self.connection.cursor()

        try:

            fields = []
            values = []

            if fees is not None:

                fields.append(
                    "fees = ?"
                )

                values.append(
                    float(fees)
                )

            if slippage is not None:

                fields.append(
                    "slippage = ?"
                )

                values.append(
                    float(slippage)
                )

            if not fields:

                return True

            fields.append(
                "updated_at = ?"
            )

            values.append(
                time.time()
            )

            values.append(
                trade_id
            )

            cursor.execute(
                f"""
                UPDATE paper_trades
                   SET {", ".join(fields)}
                 WHERE trade_id = ?
                """,
                values,
            )

            self.connection.commit()

            return cursor.rowcount > 0

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[TRADE LOGGER] update_execution_costs failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    def update_probe_state(self, trade_id, scale_in_completed, post_probe_snapshot_count):
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                UPDATE paper_trades
                   SET scale_in_completed = ?,
                       post_probe_snapshot_count = ?,
                       updated_at = ?
                 WHERE trade_id = ?
                """,
                (
                    int(scale_in_completed),
                    int(post_probe_snapshot_count),
                    time.time(),
                    trade_id
                )
            )
            self.connection.commit()
            return True
        except Exception as exc:
            self.connection.rollback()
            logger.error("[TRADE LOGGER] update_probe_state failed: %s", exc)
            return False
        finally:
            cursor.close()

    # ==================================================
    # SCALE IN
    # ==================================================

    def record_scale_in(self, position, amount, fees, slippage, cost_mode, network_fee):
        cursor = self.connection.cursor()
        try:
            now = time.time()
            cursor.execute(
                """
                UPDATE paper_trades
                   SET invested = ?,
                       tokens = ?,
                       entry_price = ?,
                       fees = fees + ?,
                       slippage = slippage + ?,
                       network_fee = network_fee + ?,
                       scale_in_completed = ?,
                       updated_at = ?
                 WHERE trade_id = ?
                """,
                (
                    getattr(position, "invested_amount", 0.0),
                    getattr(position, "tokens", 0.0),
                    getattr(position, "entry_price", 0.0),
                    float(fees),
                    float(slippage),
                    float(network_fee),
                    getattr(position, "scale_in_completed", 1),
                    now,
                    getattr(position, "trade_id", None)
                )
            )
            self.connection.commit()
            return True
        except Exception as exc:
            self.connection.rollback()
            logger.error("[TRADE LOGGER] record_scale_in failed: %s", exc)
            return False
        finally:
            cursor.close()

    # ==================================================
    # PARTIAL SELL
    # ==================================================

    def record_partial_sell(
        self,
        position,
        percent,
        proceeds,
        partial_pnl,
        exit_reason,
        fees=0.0,
        slippage=0.0,
        cost_mode="MODELED_COST",
        network_fee=0.0,
        commission=0.0,
    ) -> bool:

        trade_id = getattr(
            position,
            "trade_id",
            None,
        )

        if not trade_id:

            return False

        cursor = self.connection.cursor()

        try:

            now = time.time()

            invested = float(
                getattr(
                    position,
                    "invested_amount",
                    0.0,
                )
                or 0.0
            )

            percent = float(percent)

            slice_cost = (
                invested *
                percent /
                100.0
            )

            # ------------------------------------------------
            # Gross P&L for this slice.
            # ------------------------------------------------

            gross_pnl = (
                float(proceeds)
                - slice_cost
            )

            # ------------------------------------------------
            # Net P&L after execution costs.
            # ------------------------------------------------

            net_pnl = (
                gross_pnl
                - float(fees or 0.0)
                - float(slippage or 0.0)
            )

            partial_pct = (
                net_pnl /
                slice_cost *
                100.0
                if slice_cost > 0
                else 0.0
            )

            sell_mc = (
                getattr(
                    position,
                    "current_market_cap",
                    None,
                )
                or
                getattr(
                    position,
                    "entry_market_cap",
                    0.0,
                )
            )

            # ------------------------------------------------
            # Append exit event.
            # ------------------------------------------------

            cursor.execute(
                """
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
                    exit_reason,
                    cost_mode,
                    network_fee,
                    commission
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trade_id,

                    getattr(
                        position,
                        "signal_id",
                        None,
                    ),

                    getattr(
                        position,
                        "strategy_id",
                        "default",
                    ),

                    now,

                    getattr(
                        position,
                        "current_price",
                        0.0,
                    ),

                    sell_mc,

                    percent,

                    float(proceeds),

                    net_pnl,

                    partial_pct,

                    exit_reason,

                    cost_mode,

                    float(network_fee),

                    float(commission),
                ),
            )

            # ------------------------------------------------
            # Parent trade accounting.
            # ------------------------------------------------

            current_fees = float(
                getattr(
                    position,
                    "entry_fees",
                    0.0,
                )
                or 0.0
            )

            current_exit_fees = float(
                getattr(
                    position,
                    "exit_fees",
                    0.0,
                )
                or 0.0
            )

            current_entry_slippage = float(
                getattr(
                    position,
                    "entry_slippage",
                    0.0,
                )
                or 0.0
            )

            current_exit_slippage = float(
                getattr(
                    position,
                    "exit_slippage",
                    0.0,
                )
                or 0.0
            )

            total_fees = (
                current_fees
                + current_exit_fees
            )

            total_slippage = (
                current_entry_slippage
                + current_exit_slippage
            )

            realized = float(
                getattr(
                    position,
                    "realized_profit",
                    0.0,
                )
                or 0.0
            )

            # ------------------------------------------------
            # Trade-level realized P&L
            #
            # Partial-sell events already contain their own
            # exit friction. Entry friction belongs to the
            # complete trade and must not be deducted again
            # from every partial-sell event.
            #
            # Therefore:
            #
            # cumulative exit P&L
            #       - entry execution costs
            #
            # = total net realized P&L
            # ------------------------------------------------

            net_realized = (
                realized
                - current_entry_slippage
                - current_fees
            )

            new_remaining = max(
                0.0,
                float(
                    getattr(
                        position,
                        "remaining_percent",
                        100.0,
                    )
                ),
            )

            if new_remaining <= 0.0001:
                realized_pct = (net_realized / invested * 100.0) if invested > 0 else 0.0
                cursor.execute(
                    """
                    UPDATE paper_trades
                       SET status = 'CLOSED',
                           remaining_pct = 0.0,
                           realized_pnl = ?,
                           realized_pct = ?,
                           exit_time = ?,
                           exit_price = ?,
                           exit_market_cap = ?,
                           exit_reason = ?,
                           fees = ?,
                           slippage = ?,
                           cost_mode = ?,
                           network_fee = ?,
                           commission = ?,
                           mfe = ?,
                           mae = ?,
                           updated_at = ?
                     WHERE trade_id = ?
                    """,
                    (
                        net_realized,
                        realized_pct,
                        now,
                        getattr(position, "current_price", 0.0),
                        sell_mc,
                        exit_reason,
                        total_fees,
                        total_slippage,
                        cost_mode,
                        float(network_fee or 0.0),
                        float(commission or 0.0),
                        getattr(position, "mfe", 0.0),
                        getattr(position, "mae", 0.0),
                        now,
                        trade_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE paper_trades
                       SET remaining_pct = ?,
                           realized_pnl = ?,
                           fees = ?,
                           slippage = ?,
                           mfe = ?,
                           mae = ?,
                           updated_at = ?
                     WHERE trade_id = ?
                    """,
                    (
                        new_remaining,
                        net_realized,
                        total_fees,
                        total_slippage,
                        getattr(position, "mfe", 0.0),
                        getattr(position, "mae", 0.0),
                        now,
                        trade_id,
                    ),
                )

            self.connection.commit()

            logger.info(
                "[PAPER PARTIAL SELL] %s | "
                "sold=%.2f%% | proceeds=$%.6f | "
                "net_pnl=$%.6f | fees=$%.6f | slippage=$%.6f",
                getattr(
                    position,
                    "symbol",
                    "?",
                ),
                percent,
                float(proceeds),
                net_pnl,
                float(fees or 0.0),
                float(slippage or 0.0),
            )

            return True

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[TRADE LOGGER] record_partial_sell failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # ==================================================
    # CLOSE TRADE
    # ==================================================

    def close_trade(
        self,
        position,
        exit_reason,
        fees=0.0,
        slippage=0.0,
        proceeds=None,
        cost_mode="MODELED_COST",
        network_fee=0.0,
        commission=0.0,
    ) -> bool:

        trade_id = getattr(
            position,
            "trade_id",
            None,
        )

        if not trade_id:

            return False

        cursor = self.connection.cursor()

        try:

            now = time.time()

            # -----------------------------------------------
            # Update cumulative execution costs.
            # -----------------------------------------------

            entry_fees = float(
                getattr(
                    position,
                    "entry_fees",
                    0.0,
                )
                or 0.0
            )

            exit_fees = float(
                getattr(
                    position,
                    "exit_fees",
                    0.0,
                )
                or 0.0
            )

            entry_slippage = float(
                getattr(
                    position,
                    "entry_slippage",
                    0.0,
                )
                or 0.0
            )

            exit_slippage = float(
                getattr(
                    position,
                    "exit_slippage",
                    0.0,
                )
                or 0.0
            )

            total_fees = (
                entry_fees
                + exit_fees
                + float(fees or 0.0)
            )

            total_slippage = (
                entry_slippage
                + exit_slippage
                + float(slippage or 0.0)
            )

            # -----------------------------------------------
            # Net realized P&L.
            # -----------------------------------------------

            net_realized = float(
                getattr(
                    position,
                    "net_realized_pnl",
                    getattr(
                        position,
                        "realized_profit",
                        0.0,
                    ),
                )
                or 0.0
            )

            invested = float(
                getattr(
                    position,
                    "invested_amount",
                    0.0,
                )
                or 0.0
            )

            realized_pct = (
                net_realized /
                invested *
                100.0
                if invested > 0
                else 0.0
            )

            exit_mc = (
                getattr(
                    position,
                    "current_market_cap",
                    None,
                )
                or
                getattr(
                    position,
                    "entry_market_cap",
                    0.0,
                )
            )

            cursor.execute(
                """
                UPDATE paper_trades
                   SET status = 'CLOSED',
                       exit_time = ?,
                       exit_price = ?,
                       exit_market_cap = ?,
                       exit_reason = ?,
                       realized_pnl = ?,
                       realized_pct = ?,
                       remaining_pct = 0.0,
                       mfe = ?,
                       mae = ?,
                       fees = ?,
                       slippage = ?,
                       cost_mode = ?,
                       network_fee = ?,
                       commission = ?,
                       updated_at = ?
                  WHERE trade_id = ?
                """,
                (
                    now,

                    getattr(
                        position,
                        "current_price",
                        0.0,
                    ),

                    exit_mc,

                    exit_reason,

                    net_realized,

                    realized_pct,

                    getattr(
                        position,
                        "mfe",
                        0.0,
                    ),

                    getattr(
                        position,
                        "mae",
                        0.0,
                    ),

                    total_fees,

                    total_slippage,

                    cost_mode,

                    float(network_fee or 0.0),

                    float(commission or 0.0),

                    now,

                    trade_id,
                ),
            )

            self.connection.commit()

            logger.info(
                "[PAPER SELL] %s | "
                "net_pnl=$%.6f | %.3f%% | "
                "fees=$%.6f | slippage=$%.6f",
                getattr(
                    position,
                    "symbol",
                    "?",
                ),
                net_realized,
                realized_pct,
                total_fees,
                total_slippage,
            )

            return True

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[TRADE LOGGER] close_trade failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # ==================================================
    # OPEN TRADES
    # ==================================================

    def get_open_trades(
        self,
        strategy_id="default",
    ) -> list:

        self.connection.row_factory = sqlite3.Row

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                SELECT *
                  FROM paper_trades
                 WHERE status = 'OPEN'
                   AND strategy_id = ?
                 ORDER BY entry_time ASC
                """,
                (
                    strategy_id,
                ),
            )

            rows = cursor.fetchall()

            return [
                dict(row)
                for row in rows
            ]

        except Exception as exc:

            logger.error(
                "[TRADE LOGGER] get_open_trades failed: %s",
                exc,
            )

            return []

        finally:

            cursor.close()

    # ==================================================
    # MFE / MAE
    # ==================================================

    def update_mfe_mae(
        self,
        trade_id,
        mfe,
        mae,
    ):

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE paper_trades
                   SET mfe = ?,
                       mae = ?,
                       updated_at = ?
                 WHERE trade_id = ?
                """,
                (
                    mfe,
                    mae,
                    time.time(),
                    trade_id,
                ),
            )

            self.connection.commit()

        except Exception as exc:

            self.connection.rollback()

            logger.warning(
                "[TRADE LOGGER] update_mfe_mae failed: %s",
                exc,
            )

        finally:

            cursor.close()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):

        self.connection.close()
