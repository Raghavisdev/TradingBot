import sqlite3
from config import DATABASE


def create_tables():

    connection = sqlite3.connect(
        DATABASE,
        timeout=30.0,
        check_same_thread=False
    )

    cursor = connection.cursor()

    try:
        # Enable Write-Ahead Logging (WAL) for concurrent read/write safety
        cursor.execute("PRAGMA journal_mode=WAL;")
        wal_res = cursor.fetchone()
        cursor.execute("PRAGMA busy_timeout=30000;")
        jmode = wal_res[0].upper() if wal_res and isinstance(wal_res[0], str) else "UNKNOWN"
        print(f"[DB] SQLite Journal Mode: {jmode}")

        # ======================================================
        # SIGNALS
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS signals(

            signal_id TEXT PRIMARY KEY,

            timestamp TEXT,

            source TEXT,

            symbol TEXT,

            name TEXT,

            contract TEXT,

            telegram_message TEXT,

            signal_market_cap REAL,

            signal_price REAL,

            gt_score INTEGER,

            decision TEXT,

            final_score REAL,

            bot_version TEXT,

            bought INTEGER,

            buy_blocked_by TEXT,

            tracking_started REAL,

            tracking_completed REAL,

            decision_reason TEXT

        )

        """)

        # ======================================================
        # SNAPSHOTS
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS snapshots(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            signal_id TEXT,

            timestamp REAL,

            market_cap REAL,

            price REAL,

            liquidity REAL,

            volume REAL,

            buys INTEGER,

            sells INTEGER,

            holders INTEGER,

            market_health REAL,

            exit_action TEXT,

            exit_confidence REAL

        )

        """)

        # ======================================================
        # OUTCOMES
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS outcomes(

            signal_id TEXT PRIMARY KEY,

            peak_market_cap REAL,

            lowest_market_cap REAL,

            peak_price REAL,

            lowest_price REAL,

            max_return REAL,

            min_return REAL,

            time_to_peak INTEGER,

            rugged INTEGER,

            returned_2x INTEGER,

            returned_5x INTEGER,

            returned_10x INTEGER

        )

        """)

        # Add new columns to outcomes if they don't exist
        new_outcome_columns = [
            "ALTER TABLE outcomes ADD COLUMN snapshot_count INTEGER DEFAULT 0",
            "ALTER TABLE outcomes ADD COLUMN tracking_duration REAL DEFAULT 0",
            "ALTER TABLE outcomes ADD COLUMN tracking_end_reason TEXT DEFAULT 'NORMAL_24H'",
        ]

        for stmt in new_outcome_columns:
            try:
                cursor.execute(stmt)
            except Exception:
                pass  # Column already exists

        # ======================================================
        # TRADES
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS trades(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            signal_id TEXT,

            symbol TEXT,

            entry_price REAL,

            exit_price REAL,

            entry_market_cap REAL,

            exit_market_cap REAL,

            invested REAL,

            pnl REAL,

            pnl_percent REAL,

            holding_time INTEGER,

            exit_reason TEXT

        )

        """)

        connection.commit()
        print("[OK] Database Tables Ready")

    except Exception as e:
        connection.rollback()
        print(f"[DB ERROR] Error creating tables: {e}")
        raise e

    finally:
        cursor.close()
        connection.close()