import threading

from database.signal_logger import SignalLogger
from database.snapshot_logger import SnapshotLogger
from database.outcome_logger import OutcomeLogger
from database.intelligence_logger import IntelligenceLogger
from database.trade_logger import TradeLogger


class DatabaseManager:

    def __init__(self):

        print("===================================")
        print("Initializing Database Manager")
        print("===================================")

        self.db_lock = threading.Lock()

        self.signal_logger = SignalLogger()
        self.snapshot_logger = SnapshotLogger()
        self.outcome_logger = OutcomeLogger()
        self.intelligence_logger = IntelligenceLogger()
        self.trade_logger = TradeLogger()

        print("[OK] Database Manager Ready\n")


    # ==================================================
    # CLOSE DATABASE CONNECTIONS
    # ==================================================

    def close(self):
        """
        Close all database logger connections cleanly.

        DatabaseManager owns the logger instances, so shutdown
        must close them through this single method.
        """

        with self.db_lock:

            loggers = (
                self.signal_logger,
                self.snapshot_logger,
                self.outcome_logger,
                self.intelligence_logger,
                self.trade_logger,
            )

            for logger_instance in loggers:

                try:
                    logger_instance.close()

                except Exception as exc:

                    print(
                        "[DB CLOSE WARNING]",
                        type(logger_instance).__name__,
                        exc,
                    )

        print("[DB] All database connections closed.")


    # ==================================================
    # SIGNALS
    # ==================================================

    def create_signal(self, coin):
        with self.db_lock:
            self.signal_logger.save(coin)

    def update_signal(self, coin):
        with self.db_lock:
            self.signal_logger.save(coin)

    # ==================================================
    # SNAPSHOTS
    # ==================================================

    def save_snapshot(self, snapshot):
        with self.db_lock:
            self.snapshot_logger.save(snapshot)

    # ==================================================
    # OUTCOMES
    # ==================================================

    def save_outcome(self, coin):
        with self.db_lock:
            self.outcome_logger.save(coin)

    # ==================================================
    # SNAPSHOTS READ
    # ==================================================

    def get_snapshots_for_signal(self, signal_id):
        """
        Return all snapshots belonging to a signal.

        TrackerManager uses this during startup recovery
        to restore SignalTracker state.
        """

        with self.db_lock:
            return self.snapshot_logger.get_by_signal_id(
                signal_id
            )

    # ==================================================
    # DATABASE COUNTS
    # ==================================================

    def get_counts(self):
        """
        Return lightweight row counts for runtime health monitoring.

        Uses COUNT(*) directly in SQLite instead of loading
        complete tables into Python memory.
        """

        with self.db_lock:

            connections = (
                self.signal_logger.connection,
                self.snapshot_logger.connection,
                self.outcome_logger.connection,
            )

            counts = []

            for connection, table_name in zip(
                connections,
                (
                    "signals",
                    "snapshots",
                    "outcomes",
                ),
            ):

                cursor = connection.cursor()

                try:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table_name}"
                    )

                    counts.append(
                        int(cursor.fetchone()[0])
                    )

                finally:
                    cursor.close()

            return tuple(counts)

    # ==================================================
    # OUTCOMES READ
    # ==================================================

    def get_outcomes(self):
        """
        Return all saved outcomes.

        TrackerManager uses this during startup recovery
        to determine how many signals have already completed.
        """

        with self.db_lock:
            return self.outcome_logger.get_all()

    # ==================================================
    # PAPER TRADES
    # ==================================================

    def open_paper_trade(
        self,
        position,
    ) -> bool:
        """
        Persist a newly opened paper position.
        """

        with self.db_lock:

            return self.trade_logger.open_trade(
                position
            )

    # ==================================================
    # EXECUTION COSTS
    # ==================================================

    def update_execution_costs(
        self,
        trade_id: str,
        fees: float = None,
        slippage: float = None,
    ) -> bool:
        """
        Update cumulative execution costs for a trade.

        Fees and slippage are tracked independently.

        Price impact is intentionally NOT passed here
        because price impact is an execution-quality metric,
        not a transaction fee.
        """

        with self.db_lock:

            return self.trade_logger.update_execution_costs(
                trade_id=trade_id,
                fees=fees,
                slippage=slippage,
            )

    # ==================================================
    # PARTIAL SELL
    # ==================================================

    def record_partial_sell(
        self,
        position,
        percent: float,
        proceeds: float,
        partial_pnl: float,
        exit_reason: str,
        fees: float = 0.0,
        slippage: float = 0.0,
    ) -> bool:
        """
        Persist a partial sell.

        `fees` and `slippage` are actual execution
        accounting values for this sell.

        `partial_pnl` is retained for compatibility
        with the existing trading system.
        """

        with self.db_lock:

            return self.trade_logger.record_partial_sell(
                position=position,
                percent=percent,
                proceeds=proceeds,
                partial_pnl=partial_pnl,
                exit_reason=exit_reason,
                fees=fees,
                slippage=slippage,
            )

    # ==================================================
    # FINAL CLOSE
    # ==================================================

    def close_paper_trade(
        self,
        position,
        exit_reason: str,
        fees: float = 0.0,
        slippage: float = 0.0,
        proceeds: float = None,
    ) -> bool:
        """
        Mark a paper trade as CLOSED.

        Execution costs are persisted separately from
        price impact.
        """

        with self.db_lock:

            return self.trade_logger.close_trade(
                position=position,
                exit_reason=exit_reason,
                fees=fees,
                slippage=slippage,
                proceeds=proceeds,
            )

    # ==================================================
    # OPEN TRADES
    # ==================================================

    def get_open_paper_trades(
        self,
        strategy_id: str = "default",
    ) -> list:
        """
        Return all OPEN paper trades.
        """

        with self.db_lock:

            return self.trade_logger.get_open_trades(
                strategy_id
            )

    # ==================================================
    # MFE / MAE
    # ==================================================

    def update_mfe_mae(
        self,
        trade_id: str,
        mfe: float,
        mae: float,
    ) -> None:
        """
        Update maximum favorable/adverse excursion.
        """

        with self.db_lock:

            self.trade_logger.update_mfe_mae(
                trade_id,
                mfe,
                mae,
            )

    # ==================================================
    # READ HELPERS
    # ==================================================

    def get_signals(self):

        return self.signal_logger.get_all()

    def get_uncompleted_signals(self):

        return self.signal_logger.get_uncompleted()
