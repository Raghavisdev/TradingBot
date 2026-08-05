import sqlite3
from config import DATABASE


class OutcomeLogger:

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
    # SAVE OUTCOME
    # ==================================================

    def save(self, coin):

        signal_id = getattr(coin, "signal_id", None)
        if not signal_id:
            return

        cursor = self.connection.cursor()

        try:
            # Check if outcome already exists for this signal
            cursor.execute("SELECT signal_id FROM outcomes WHERE signal_id = ?", (signal_id,))
            if cursor.fetchone():
                print(f"[OUTCOME SKIPPED] Outcome already exists for {getattr(coin, 'symbol', signal_id)}")
                return

            # Compute tracking_duration from timestamps on the coin
            tracking_started = getattr(coin, "tracking_started", 0) or 0
            tracking_finished = getattr(coin, "tracking_finished", 0) or 0
            tracking_duration = tracking_finished - tracking_started if tracking_finished else 0

            cursor.execute("""

            INSERT OR REPLACE INTO outcomes(

                signal_id,
                peak_market_cap,
                lowest_market_cap,
                peak_price,
                lowest_price,
                max_return,
                min_return,
                time_to_peak,
                rugged,
                returned_2x,
                returned_5x,
                returned_10x,
                snapshot_count,
                tracking_duration,
                tracking_end_reason

            )

            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)

            """, (

                getattr(coin, "signal_id", None),

                getattr(coin, "peak_market_cap", 0),

                getattr(coin, "lowest_market_cap", 0),

                getattr(coin, "peak_price", 0),

                getattr(coin, "lowest_price", 0),

                getattr(coin, "max_return", 0),

                getattr(coin, "min_return", 0),

                getattr(coin, "time_to_peak", 0),

                int(getattr(coin, "rugged", False)),

                int(getattr(coin, "returned_2x", False)),

                int(getattr(coin, "returned_5x", False)),

                int(getattr(coin, "returned_10x", False)),

                getattr(coin, "snapshot_count", 0),

                tracking_duration,

                getattr(coin, "tracking_end_reason", "NORMAL_24H")

            ))

            self.connection.commit()

            print(f"[DB] Outcome Saved : {coin.symbol}")

        except Exception as e:

            self.connection.rollback()

            print(f"[DB ERROR] Outcome Save Failed for {getattr(coin, 'symbol', '')}: {e}")

            raise e

        finally:

            cursor.close()

    # ==================================================
    # GET ALL
    # ==================================================

    def get_all(self):

        cursor = self.connection.cursor()

        try:

            cursor.execute("SELECT * FROM outcomes")

            return cursor.fetchall()

        finally:

            cursor.close()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):

        self.connection.close()