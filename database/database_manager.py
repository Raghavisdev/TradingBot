import threading
from database.signal_logger import SignalLogger
from database.snapshot_logger import SnapshotLogger
from database.outcome_logger import OutcomeLogger
from database.intelligence_logger import IntelligenceLogger

# Uncomment when implemented
# from database.trade_logger import TradeLogger


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

        # self.trade_logger = TradeLogger()

        print("[OK] Database Manager Ready\n")

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
    # TRADES
    # ==================================================

    # def save_trade(self, position):
    #     self.trade_logger.save(position)

    # ==================================================
    # READ HELPERS
    # ==================================================

    def get_signals(self):
        return self.signal_logger.get_all()

    def get_uncompleted_signals(self):
        return self.signal_logger.get_uncompleted()

    def get_snapshots(self):
        return self.snapshot_logger.get_all()

    def get_snapshots_for_signal(self, signal_id):
        return self.snapshot_logger.get_by_signal_id(signal_id)

    def get_outcomes(self):
        return self.outcome_logger.get_all()

    # ==================================================
    # CLOSE
    # ==================================================

    # ==================================================
    # INTELLIGENCE
    # ==================================================

    def save_intelligence(self, record: dict):
        with self.db_lock:
            self.intelligence_logger.save(record)

    def get_intelligence_for_signal(self, signal_id: str):
        return self.intelligence_logger.get_by_signal_id(signal_id)

    def get_all_intelligence_for_signal(self, signal_id: str):
        """Returns the full time-series of intelligence records for a signal."""
        return self.intelligence_logger.get_all_for_signal(signal_id)

    def get_all_intelligence(self):
        return self.intelligence_logger.get_all()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):

        self.signal_logger.close()
        self.snapshot_logger.close()
        self.outcome_logger.close()
        self.intelligence_logger.close()

        # self.trade_logger.close()


database = DatabaseManager()