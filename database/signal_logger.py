import sqlite3
from config import DATABASE


class SignalLogger:

    def __init__(self):

        self.connection = sqlite3.connect(
            DATABASE,
            timeout=30.0,
            check_same_thread=False
        )

        # Set PRAGMAs on connection initialization
        init_cursor = self.connection.cursor()
        try:
            init_cursor.execute("PRAGMA journal_mode=WAL;")
            init_cursor.execute("PRAGMA busy_timeout=30000;")
        finally:
            init_cursor.close()

    # ==================================================
    # SAVE SIGNAL
    # ==================================================

    def save(self, coin):

        cursor = self.connection.cursor()

        try:
            # decision_reason is a list on Coin — join to a single string for storage
            decision_reason = ", ".join(
                getattr(coin, "decision_reasons", []) or []
            )

            cursor.execute("""

            INSERT OR REPLACE INTO signals(

                signal_id,
                timestamp,
                source,
                symbol,
                name,
                contract,
                telegram_message,
                signal_market_cap,
                signal_price,
                gt_score,
                decision,
                final_score,
                bot_version,
                bought,
                buy_blocked_by,
                tracking_started,
                tracking_completed,
                decision_reason

            )

            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)

            """, (

                getattr(coin, "signal_id", None),
                getattr(coin, "signal_time", None),
                getattr(coin, "source", "GemTools"),
                getattr(coin, "symbol", None),
                getattr(coin, "name", None),
                getattr(coin, "contract", None),
                getattr(coin, "raw_message", None),
                getattr(coin, "signal_market_cap", 0),
                getattr(coin, "signal_price", 0),
                getattr(coin, "gt_score", 0),
                getattr(coin, "decision", ""),
                getattr(coin, "final_score", 0),
                getattr(coin, "bot_version", "v1"),
                int(getattr(coin, "bought", False)),
                getattr(coin, "buy_blocked_by", ""),
                getattr(coin, "tracking_started", 0),
                getattr(coin, "tracking_finished", 0),
                decision_reason

            ))

            self.connection.commit()

            print(f"[DB] Signal Saved : {coin.symbol}")

        except Exception as e:

            self.connection.rollback()

            print(f"[DB ERROR] Signal Save Failed for {getattr(coin, 'symbol', '')}: {e}")

            raise e

        finally:

            cursor.close()

    # ==================================================
    # GET ALL
    # ==================================================

    def get_all(self):

        cursor = self.connection.cursor()

        try:

            cursor.execute("SELECT * FROM signals")

            return cursor.fetchall()

        finally:

            cursor.close()

    # ==================================================
    # GET UNCOMPLETED SIGNALS
    # ==================================================

    def get_uncompleted(self):

        self.connection.row_factory = sqlite3.Row

        cursor = self.connection.cursor()

        try:

            cursor.execute("""

            SELECT s.* FROM signals s

            LEFT JOIN outcomes o ON s.signal_id = o.signal_id

            WHERE o.signal_id IS NULL

            """)

            rows = cursor.fetchall()

            return [dict(r) for r in rows]

        finally:

            cursor.close()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):

        self.connection.close()