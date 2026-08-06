"""
Intelligence Database Logger
----------------------------
Persists all passive intelligence records to the `intelligence` SQLite table.
Follows the exact same connection pattern as SignalLogger/SnapshotLogger.

v2: Supports time-series records (multiple rows per signal_id), new velocity,
    acceleration, freshness, community, and composite metrics.

Zero impact on existing tables or pipeline.
"""

import sqlite3
import logging
from config import DATABASE

logger = logging.getLogger("IntelligenceLogger")


class IntelligenceLogger:

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
    # SAVE INTELLIGENCE RECORD
    # ==================================================

    def save(self, record: dict):
        """
        Saves one intelligence record. Each call creates a NEW row (INSERT only).
        Records are linked by signal_id + collection_index for time-series.
        """
        signal_id = record.get("signal_id")
        if not signal_id:
            return

        cursor = self.connection.cursor()

        try:
            cursor.execute("""
            INSERT INTO intelligence(
                signal_id,
                collected_at,
                collection_index,
                collection_minutes,

                social_mentions,
                social_velocity,
                mentions_per_minute,
                growth_rate,
                viral_acceleration,
                engagement_velocity,
                engagement_score,
                viral_score,

                news_score,
                news_headline,
                news_sentiment,
                news_minutes_old,
                news_credibility,
                news_source,
                freshness_score,

                sentiment_positive,
                sentiment_neutral,
                sentiment_negative,
                sentiment_confidence,
                sentiment_strength,

                sarcasm_probability,

                primary_narrative,
                secondary_narrative,
                narrative_confidence,
                narrative_heat_score,

                kol_mentions,
                kol_score,

                telegram_members,
                twitter_followers,
                community_growth_rate,
                message_rate,
                active_users,

                mc_velocity,
                holder_velocity,
                volume_velocity,
                buy_velocity,
                liquidity_change,

                mc_acceleration,
                holder_acceleration,
                volume_acceleration,
                buy_sell_ratio
            )
            VALUES(
                ?,?,?,?,
                ?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,
                ?,?,?,?,?,
                ?,
                ?,?,?,?,
                ?,?,
                ?,?,?,?,?,
                ?,?,?,?,?,
                ?,?,?,?
            )
            """, (
                signal_id,
                record.get("collected_at", 0.0),
                record.get("collection_index", 0),
                record.get("collection_minutes", 0.0),

                record.get("social_mentions", 0),
                record.get("social_velocity", 0.0),
                record.get("mentions_per_minute", 0.0),
                record.get("growth_rate", 0.0),
                record.get("viral_acceleration", 0.0),
                record.get("engagement_velocity", 0.0),
                record.get("engagement_score", 0.0),
                record.get("viral_score", 0.0),

                record.get("news_score", 0.0),
                record.get("news_headline", "")[:200],
                record.get("news_sentiment", "neutral"),
                record.get("news_minutes_old", 0.0),
                record.get("news_credibility", 0.0),
                record.get("news_source", ""),
                record.get("freshness_score", 0.0),

                record.get("sentiment_positive", 0.0),
                record.get("sentiment_neutral", 1.0),
                record.get("sentiment_negative", 0.0),
                record.get("sentiment_confidence", 0.0),
                record.get("sentiment_strength", 0.0),

                record.get("sarcasm_probability", 0.0),

                record.get("primary_narrative", "Unknown"),
                record.get("secondary_narrative", ""),
                record.get("narrative_confidence", 0.0),
                record.get("narrative_heat_score", 0.0),

                record.get("kol_mentions", 0),
                record.get("kol_score", 0.0),

                record.get("telegram_members", 0),
                record.get("twitter_followers", 0),
                record.get("community_growth_rate", 0.0),
                record.get("message_rate", 0.0),
                record.get("active_users", 0),

                record.get("mc_velocity", 0.0),
                record.get("holder_velocity", 0.0),
                record.get("volume_velocity", 0.0),
                record.get("buy_velocity", 0.0),
                record.get("liquidity_change", 0.0),

                record.get("mc_acceleration", 0.0),
                record.get("holder_acceleration", 0.0),
                record.get("volume_acceleration", 0.0),
                record.get("buy_sell_ratio", 0.0),
            ))

            self.connection.commit()

        except Exception as e:
            self.connection.rollback()
            logger.error("[INTELLIGENCE DB] Save failed for %s idx=%s: %s",
                         signal_id[:8], record.get("collection_index", "?"), e)

        finally:
            cursor.close()

    # ==================================================
    # GET BY SIGNAL ID (most recent)
    # ==================================================

    def get_by_signal_id(self, signal_id):
        """Returns the most recent intelligence record for a given signal."""
        self.connection.row_factory = sqlite3.Row
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT * FROM intelligence WHERE signal_id = ? ORDER BY collection_index DESC LIMIT 1",
                (signal_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else {}
        finally:
            cursor.close()

    # ==================================================
    # GET ALL RECORDS FOR SIGNAL (time-series)
    # ==================================================

    def get_all_for_signal(self, signal_id):
        """Returns all time-series records for a signal, ordered by collection_index."""
        self.connection.row_factory = sqlite3.Row
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT * FROM intelligence WHERE signal_id = ? ORDER BY collection_index ASC",
                (signal_id,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            cursor.close()

    # ==================================================
    # GET ALL
    # ==================================================

    def get_all(self):
        self.connection.row_factory = sqlite3.Row
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT * FROM intelligence ORDER BY signal_id, collection_index")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            cursor.close()

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):
        self.connection.close()
