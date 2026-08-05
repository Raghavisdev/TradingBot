import sqlite3
from config import DATABASE


class SnapshotLogger:

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
    # SAVE SNAPSHOT
    # ==================================================

    def save(self, snapshot):

        cursor = self.connection.cursor()

        try:
            cursor.execute("""

            INSERT INTO snapshots(

                signal_id,
                timestamp,
                market_cap,
                price,
                liquidity,
                volume,
                buys,
                sells,
                holders,
                market_health,
                exit_action,
                exit_confidence

            )

            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)

            """, (

                snapshot.get("signal_id"),
                snapshot.get("timestamp"),
                snapshot.get("market_cap"),
                snapshot.get("price"),
                snapshot.get("liquidity"),
                snapshot.get("volume"),
                snapshot.get("buys"),
                snapshot.get("sells"),
                snapshot.get("holders"),
                snapshot.get("market_health"),
                snapshot.get("exit_action"),
                snapshot.get("exit_confidence")

            ))

            self.connection.commit()

        except Exception as e:

            self.connection.rollback()

            print(f"[DB ERROR] Snapshot Save Failed for {snapshot.get('signal_id')}: {e}")

            raise e

        finally:

            cursor.close()

    # ==================================================
    # GET ALL
    # ==================================================

    def get_all(self):

        cursor = self.connection.cursor()

        try:

            cursor.execute("SELECT * FROM snapshots")

            return cursor.fetchall()

        finally:

            cursor.close()

    # ==================================================
    # GET BY SIGNAL ID
    # ==================================================

    def get_by_signal_id(self, signal_id):

        self.connection.row_factory = sqlite3.Row

        cursor = self.connection.cursor()

        try:

            cursor.execute(

                "SELECT * FROM snapshots WHERE signal_id = ? ORDER BY id ASC",

                (signal_id,)

            )

            rows = cursor.fetchall()

            return [dict(r) for r in rows]

        finally:

            cursor.close()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):

        self.connection.close()