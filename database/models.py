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

        # ======================================================
        # PAPER TRADES
        # One row per paper trade open event.
        # Updated in-place as the trade progresses (status, P&L, MFE, MAE).
        # strategy_id / strategy_version enable multi-strategy portfolios later.
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS paper_trades(

            id                  INTEGER PRIMARY KEY AUTOINCREMENT,

            trade_id            TEXT UNIQUE,

            strategy_id         TEXT DEFAULT 'default',

            strategy_version    TEXT DEFAULT '1.0',

            signal_id           TEXT,

            symbol              TEXT,

            contract            TEXT,

            status              TEXT DEFAULT 'OPEN',

            entry_time          REAL,

            entry_price         REAL,

            entry_market_cap    REAL,

            invested            REAL,

            tokens              REAL,

            remaining_pct       REAL DEFAULT 100.0,

            exit_time           REAL,

            exit_price          REAL,

            exit_market_cap     REAL,

            exit_reason         TEXT,

            realized_pnl        REAL DEFAULT 0.0,

            realized_pct        REAL DEFAULT 0.0,

            mfe                 REAL DEFAULT 0.0,

            mae                 REAL DEFAULT 0.0,

            fees                REAL DEFAULT 0.0,

            slippage            REAL DEFAULT 0.0,

            updated_at          REAL

        )

        """)

        new_paper_trade_cols = [
            "ALTER TABLE paper_trades ADD COLUMN cost_mode TEXT DEFAULT 'MODELED_COST'",
            "ALTER TABLE paper_trades ADD COLUMN network_fee REAL DEFAULT 0.0",
            "ALTER TABLE paper_trades ADD COLUMN commission REAL DEFAULT 0.0"
        ]
        for stmt in new_paper_trade_cols:
            try:
                cursor.execute(stmt)
            except Exception:
                pass

        # ======================================================
        # PAPER PARTIAL SELLS
        # Append-only — one row per partial exit event.
        # trade_id links back to paper_trades.
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS paper_partial_sells(

            id              INTEGER PRIMARY KEY AUTOINCREMENT,

            trade_id        TEXT,

            signal_id       TEXT,

            strategy_id     TEXT DEFAULT 'default',

            sell_time       REAL,

            sell_price      REAL,

            sell_market_cap REAL,

            percent_sold    REAL,

            proceeds        REAL,

            partial_pnl     REAL,

            partial_pct     REAL,

            exit_reason     TEXT

        )

        """)

        new_paper_partial_cols = [
            "ALTER TABLE paper_partial_sells ADD COLUMN cost_mode TEXT DEFAULT 'MODELED_COST'",
            "ALTER TABLE paper_partial_sells ADD COLUMN network_fee REAL DEFAULT 0.0",
            "ALTER TABLE paper_partial_sells ADD COLUMN commission REAL DEFAULT 0.0"
        ]
        for stmt in new_paper_partial_cols:
            try:
                cursor.execute(stmt)
            except Exception:
                pass

        # ======================================================
        # INTELLIGENCE (AI V2 — Passive Collection Layer)
        # ======================================================

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS intelligence(

            id                     INTEGER PRIMARY KEY AUTOINCREMENT,

            signal_id              TEXT,
            collected_at           REAL,

            -- Time-series tracking
            collection_index       INTEGER DEFAULT 0,
            collection_minutes     REAL DEFAULT 0,

            -- Social
            social_mentions        INTEGER DEFAULT 0,
            social_velocity        REAL DEFAULT 0,
            mentions_per_minute    REAL DEFAULT 0,
            growth_rate            REAL DEFAULT 0,
            viral_acceleration     REAL DEFAULT 0,
            engagement_velocity    REAL DEFAULT 0,
            engagement_score       REAL DEFAULT 0,
            viral_score            REAL DEFAULT 0,

            -- News
            news_score             REAL DEFAULT 0,
            news_headline          TEXT DEFAULT '',
            news_sentiment         TEXT DEFAULT 'neutral',
            news_minutes_old       REAL DEFAULT 0,
            news_credibility       REAL DEFAULT 0,
            news_source            TEXT DEFAULT '',
            freshness_score        REAL DEFAULT 0,

            -- Sentiment
            sentiment_positive     REAL DEFAULT 0,
            sentiment_neutral      REAL DEFAULT 0,
            sentiment_negative     REAL DEFAULT 0,
            sentiment_confidence   REAL DEFAULT 0,
            sentiment_strength     REAL DEFAULT 0,

            -- Sarcasm
            sarcasm_probability    REAL DEFAULT 0,

            -- Narrative
            primary_narrative      TEXT DEFAULT 'Unknown',
            secondary_narrative    TEXT DEFAULT '',
            narrative_confidence   REAL DEFAULT 0,
            narrative_heat_score   REAL DEFAULT 0,

            -- KOL
            kol_mentions           INTEGER DEFAULT 0,
            kol_score              REAL DEFAULT 0,

            -- Community
            telegram_members       INTEGER DEFAULT 0,
            twitter_followers      INTEGER DEFAULT 0,
            community_growth_rate  REAL DEFAULT 0,
            message_rate           REAL DEFAULT 0,
            active_users           INTEGER DEFAULT 0,

            -- Momentum velocity
            mc_velocity            REAL DEFAULT 0,
            holder_velocity        REAL DEFAULT 0,
            volume_velocity        REAL DEFAULT 0,
            buy_velocity           REAL DEFAULT 0,
            liquidity_change       REAL DEFAULT 0,

            -- Momentum acceleration
            mc_acceleration        REAL DEFAULT 0,
            holder_acceleration    REAL DEFAULT 0,
            volume_acceleration    REAL DEFAULT 0,
            buy_sell_ratio         REAL DEFAULT 0

        )

        """)

        # Add new columns to intelligence if they don't exist (migration for existing DBs)
        new_intelligence_columns = [
            "ALTER TABLE intelligence ADD COLUMN collection_index INTEGER DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN collection_minutes REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN mentions_per_minute REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN growth_rate REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN viral_acceleration REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN engagement_velocity REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN news_source TEXT DEFAULT ''",
            "ALTER TABLE intelligence ADD COLUMN freshness_score REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN sentiment_strength REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN message_rate REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN active_users INTEGER DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN mc_acceleration REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN holder_acceleration REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN volume_acceleration REAL DEFAULT 0",
            "ALTER TABLE intelligence ADD COLUMN buy_sell_ratio REAL DEFAULT 0",
        ]

        for stmt in new_intelligence_columns:
            try:
                cursor.execute(stmt)
            except Exception:
                pass  # Column already exists

        # ======================================================
        # PAPER LAB TRADES (Phase 3 Multi-Strategy Lab)
        # ======================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_lab_trades(
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id            TEXT UNIQUE,
            strategy_id         TEXT DEFAULT 'S1',
            strategy_version    TEXT DEFAULT '1.0',
            signal_id           TEXT,
            symbol              TEXT,
            contract            TEXT,
            status              TEXT DEFAULT 'OPEN',
            entry_time          REAL,
            entry_price         REAL,
            entry_market_cap    REAL,
            invested            REAL,
            tokens              REAL,
            remaining_pct       REAL DEFAULT 100.0,
            exit_time           REAL,
            exit_price          REAL,
            exit_market_cap     REAL,
            exit_reason         TEXT,
            realized_pnl        REAL DEFAULT 0.0,
            realized_pct        REAL DEFAULT 0.0,
            mfe                 REAL DEFAULT 0.0,
            mae                 REAL DEFAULT 0.0,
            fees                REAL DEFAULT 0.0,
            slippage            REAL DEFAULT 0.0,
            fired_levels        TEXT DEFAULT '',
            highest_stop_pnl    REAL DEFAULT -20.0,
            peak_multiple       REAL DEFAULT 1.0,
            updated_at          REAL
        )
        """)

        # Add new columns to paper_lab_trades if they don't exist
        new_paper_lab_columns = [
            "ALTER TABLE paper_lab_trades ADD COLUMN fired_levels TEXT DEFAULT ''",
            "ALTER TABLE paper_lab_trades ADD COLUMN highest_stop_pnl REAL DEFAULT -20.0",
            "ALTER TABLE paper_lab_trades ADD COLUMN peak_multiple REAL DEFAULT 1.0",
        ]
        for stmt in new_paper_lab_columns:
            try:
                cursor.execute(stmt)
            except Exception:
                pass

        # ======================================================
        # PAPER LAB PARTIAL SELLS
        # ======================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_lab_partial_sells(
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id        TEXT,
            signal_id       TEXT,
            strategy_id     TEXT DEFAULT 'S1',
            sell_time       REAL,
            sell_price      REAL,
            sell_market_cap REAL,
            percent_sold    REAL,
            proceeds        REAL,
            partial_pnl     REAL,
            partial_pct     REAL,
            exit_reason     TEXT
        )
        """)

        # ======================================================
        # PAPER LAB EQUITY
        # ======================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_lab_equity(
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id     TEXT,
            timestamp       REAL,
            cash            REAL,
            position_value  REAL,
            equity          REAL
        )
        """)

        # ======================================================
        # S7 SHADOW ENGINE DECISIONS
        # ======================================================
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS s7_shadow_decisions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE,
            symbol TEXT,
            decision_timestamp REAL,
            model_version TEXT NOT NULL,
            opportunity_score REAL,
            execution_risk_score REAL,
            net_score REAL,
            shadow_allocation REAL,
            estimated_entry_impact REAL NULL,
            estimated_exit_impact REAL NULL,
            estimated_round_trip_cost REAL NULL,
            s6_decision TEXT,
            s6_allocation REAL,
            feature_version TEXT NOT NULL,
            feature_snapshot_json TEXT NOT NULL,
            execution_snapshot_json TEXT,
            t0_timestamp REAL,
            intel_source_timestamp REAL,
            snapshot_source_timestamp REAL,
            dataset_version TEXT,
            p_rug REAL,
            p_2x REAL,
            p_5x REAL,
            p_10x REAL,
            expected_return REAL,
            rank_percentile REAL,
            confidence REAL,
            recommendation TEXT,
            ml_shadow_allocation REAL,
            created_at REAL
        )
        """)

        try:
            cursor.execute("ALTER TABLE s7_shadow_decisions ADD COLUMN execution_snapshot_json TEXT")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE s7_shadow_decisions ADD COLUMN t0_timestamp REAL")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE s7_shadow_decisions ADD COLUMN intel_source_timestamp REAL")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE s7_shadow_decisions ADD COLUMN snapshot_source_timestamp REAL")
        except Exception:
            pass

        # ML Canonical Additions
        ml_cols = [
            "dataset_version TEXT", "p_rug REAL", "p_2x REAL", "p_5x REAL", "p_10x REAL",
            "expected_return REAL", "rank_percentile REAL", "confidence REAL",
            "recommendation TEXT", "ml_shadow_allocation REAL"
        ]
        for col_def in ml_cols:
            try:
                cursor.execute(f"ALTER TABLE s7_shadow_decisions ADD COLUMN {col_def}")
            except Exception:
                pass

        # ======================================================
        # EXECUTION ORDERS (P0 Readiness)
        # ======================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_orders(
            order_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            signal_id TEXT,
            symbol TEXT,
            side TEXT,
            requested_amount REAL,
            executed_amount REAL,
            status TEXT,
            created_at REAL,
            updated_at REAL,
            error TEXT
        )
        """)
        
        try:
            cursor.execute("ALTER TABLE execution_orders ADD COLUMN transaction_signature TEXT")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE execution_orders ADD COLUMN confirmation_status TEXT")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE execution_orders ADD COLUMN confirmed_slot INTEGER")
        except Exception:
            pass

        connection.commit()
        print("[OK] Database Tables Ready")

    except Exception as e:
        connection.rollback()
        print(f"[DB ERROR] Error creating tables: {e}")
        raise e

    finally:
        cursor.close()
        connection.close()
