"""
Intelligence Runner v2
-----------------------
Orchestrates all passive intelligence collection modules.
Schedules 9 collections over a signal's lifecycle via threading.Timer.

Collection schedule (minutes since signal):
    Index 0:  immediately
    Index 1:  5 min
    Index 2:  15 min
    Index 3:  30 min
    Index 4:  60 min (1 hr)
    Index 5:  120 min (2 hr)
    Index 6:  360 min (6 hr)
    Index 7:  720 min (12 hr)
    Index 8:  1440 min (24 hr)

Each collection → NEW row in intelligence table (never overwrites).
All timers are daemon — they die cleanly when the bot stops.

MODE: PASSIVE COLLECTION ONLY. Does NOT affect BUY decisions.
"""

import time
import logging
import threading

from intelligence.social         import collect_social
from intelligence.news           import collect_news
from intelligence.sentiment      import collect_sentiment
from intelligence.sarcasm        import collect_sarcasm
from intelligence.narrative      import collect_narrative
from intelligence.narrative_heat import collect_narrative_heat
from intelligence.kol            import collect_kol
from intelligence.community      import collect_community
from intelligence.momentum       import collect_momentum

logger = logging.getLogger("Intelligence")

# ======================================================
# COLLECTION SCHEDULE (minutes → seconds delay)
# ======================================================

COLLECTION_SCHEDULE = [
    (0,    0),          # Index 0: immediately
    (1,    5 * 60),     # Index 1: 5 min
    (2,    15 * 60),    # Index 2: 15 min
    (3,    30 * 60),    # Index 3: 30 min
    (4,    60 * 60),    # Index 4: 1 hr
    (5,    120 * 60),   # Index 5: 2 hr
    (6,    360 * 60),   # Index 6: 6 hr
    (7,    720 * 60),   # Index 7: 12 hr
    (8,    1440 * 60),  # Index 8: 24 hr
]

SCHEDULE_MINUTES = [0, 5, 15, 30, 60, 120, 360, 720, 1440]


class IntelligenceRunner:

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from database.database import database
            self._db = database
        return self._db

    # ==================================================
    # COLLECT — Non-blocking entry point
    # ==================================================

    def collect(self, coin):
        """
        Schedules all 9 intelligence collections for this signal.
        Returns immediately — does NOT block the main pipeline.
        """
        signal_id = getattr(coin, "signal_id", None)
        if not signal_id:
            return

        symbol = getattr(coin, "symbol", "?") or "?"

        for idx, delay_seconds in COLLECTION_SCHEDULE:
            minutes = SCHEDULE_MINUTES[idx]
            timer = threading.Timer(
                delay_seconds,
                self._collect_worker,
                args=(coin, idx, minutes)
            )
            timer.daemon = True
            timer.name = f"intel_{signal_id[:6]}_{idx}"
            timer.start()

        logger.info("[INTEL] %s | Scheduled 9 collections (0→1440 min)", symbol)

    # ==================================================
    # WORKER — Runs in timer thread at scheduled time
    # ==================================================

    def _collect_worker(self, coin, collection_index: int, collection_minutes: float):
        """
        Runs all intelligence modules, assembles a complete record,
        and saves it as a NEW row. Never overwrites previous records.

        All module failures are caught individually — the bot never crashes.
        """
        signal_id = getattr(coin, "signal_id", None)
        symbol    = getattr(coin, "symbol", "?") or "?"

        if not signal_id:
            return

        label = f"#{collection_index} ({int(collection_minutes)}m)"
        logger.info("[INTEL] %s | Collection %s starting", symbol, label)

        record = {
            "signal_id":          signal_id,
            "collected_at":       time.time(),
            "collection_index":   collection_index,
            "collection_minutes": collection_minutes,
        }

        # --------------------------------------------------
        # Module 3: Sentiment (fast — local only)
        # --------------------------------------------------
        try:
            record.update(collect_sentiment(coin))
            logger.debug("[INTEL] %s | %s | Sentiment: pos=%.2f neg=%.2f strength=%.2f",
                         symbol, label,
                         record.get("sentiment_positive", 0),
                         record.get("sentiment_negative", 0),
                         record.get("sentiment_strength", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Sentiment FAILED: %s", symbol, label, e)
            record.update({
                "sentiment_positive": 0.0, "sentiment_neutral": 1.0,
                "sentiment_negative": 0.0, "sentiment_confidence": 0.0,
                "sentiment_strength": 0.0,
            })

        # --------------------------------------------------
        # Module 4: Sarcasm (fast — local only)
        # --------------------------------------------------
        try:
            record.update(collect_sarcasm(coin))
            logger.debug("[INTEL] %s | %s | Sarcasm: %.2f",
                         symbol, label, record.get("sarcasm_probability", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Sarcasm FAILED: %s", symbol, label, e)
            record.update({"sarcasm_probability": 0.0})

        # --------------------------------------------------
        # Module 5: Narrative (fast — local only)
        # --------------------------------------------------
        try:
            narrative_result = collect_narrative(coin)
            record.update(narrative_result)
            coin._intelligence_primary_narrative = narrative_result.get("primary_narrative", "Unknown")
            logger.debug("[INTEL] %s | %s | Narrative: %s (%.2f)",
                         symbol, label,
                         record.get("primary_narrative", "Unknown"),
                         record.get("narrative_confidence", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Narrative FAILED: %s", symbol, label, e)
            record.update({
                "primary_narrative": "Unknown", "secondary_narrative": "",
                "narrative_confidence": 0.0,
            })
            coin._intelligence_primary_narrative = "Unknown"

        # --------------------------------------------------
        # Module 9: Momentum (uses existing snapshots — no network)
        # --------------------------------------------------
        try:
            db = self._get_db()
            record.update(collect_momentum(coin, db))
            logger.debug("[INTEL] %s | %s | Momentum: mc_vel=%.2f holder_vel=%.2f accel=%.2f",
                         symbol, label,
                         record.get("mc_velocity", 0),
                         record.get("holder_velocity", 0),
                         record.get("mc_acceleration", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Momentum FAILED: %s", symbol, label, e)
            record.update({
                "mc_velocity": 0.0, "holder_velocity": 0.0,
                "volume_velocity": 0.0, "buy_velocity": 0.0,
                "liquidity_change": 0.0, "mc_acceleration": 0.0,
                "holder_acceleration": 0.0, "volume_acceleration": 0.0,
                "buy_sell_ratio": 0.0,
            })

        # --------------------------------------------------
        # Module 1: Social (network)
        # --------------------------------------------------
        try:
            record.update(collect_social(coin))
            logger.debug("[INTEL] %s | %s | Social: mentions=%d velocity=%.2f viral=%.1f",
                         symbol, label,
                         record.get("social_mentions", 0),
                         record.get("social_velocity", 0),
                         record.get("viral_score", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Social FAILED: %s", symbol, label, e)
            record.update({
                "social_mentions": 0, "social_velocity": 0.0,
                "mentions_per_minute": 0.0, "growth_rate": 0.0,
                "viral_acceleration": 0.0, "engagement_velocity": 0.0,
                "engagement_score": 0.0, "viral_score": 0.0,
            })

        # --------------------------------------------------
        # Module 2: News (network)
        # --------------------------------------------------
        try:
            record.update(collect_news(coin))
            logger.debug("[INTEL] %s | %s | News: score=%.1f fresh=%.2f src=%s",
                         symbol, label,
                         record.get("news_score", 0),
                         record.get("freshness_score", 0),
                         record.get("news_source", "none"))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | News FAILED: %s", symbol, label, e)
            record.update({
                "news_score": 0.0, "news_headline": "", "news_sentiment": "neutral",
                "news_minutes_old": 0.0, "news_credibility": 0.0,
                "news_source": "", "freshness_score": 0.0,
            })

        # --------------------------------------------------
        # Module 6: Narrative Heat (network — CryptoPanic RSS)
        # --------------------------------------------------
        try:
            record.update(collect_narrative_heat(coin))
            logger.debug("[INTEL] %s | %s | Narrative heat: %.1f",
                         symbol, label, record.get("narrative_heat_score", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Narrative Heat FAILED: %s", symbol, label, e)
            record.update({"narrative_heat_score": 0.0})

        # --------------------------------------------------
        # Module 7: KOL (Twitter — disabled until key set)
        # --------------------------------------------------
        try:
            record.update(collect_kol(coin))
            logger.debug("[INTEL] %s | %s | KOL: mentions=%d score=%.1f",
                         symbol, label,
                         record.get("kol_mentions", 0),
                         record.get("kol_score", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | KOL FAILED: %s", symbol, label, e)
            record.update({"kol_mentions": 0, "kol_score": 0.0})

        # --------------------------------------------------
        # Module 8: Community Growth
        # --------------------------------------------------
        try:
            record.update(collect_community(coin))
            logger.debug("[INTEL] %s | %s | Community: tg=%d twitter=%d msg_rate=%.2f",
                         symbol, label,
                         record.get("telegram_members", 0),
                         record.get("twitter_followers", 0),
                         record.get("message_rate", 0))
        except Exception as e:
            logger.warning("[INTEL] %s | %s | Community FAILED: %s", symbol, label, e)
            record.update({
                "telegram_members": 0, "twitter_followers": 0,
                "community_growth_rate": 0.0, "message_rate": 0.0,
                "active_users": 0,
            })

        # --------------------------------------------------
        # Composite Viral Score (from multiple signals)
        # --------------------------------------------------
        try:
            record["viral_score"] = _compute_composite_viral_score(record)
        except Exception:
            pass

        # --------------------------------------------------
        # Save to database
        # --------------------------------------------------
        try:
            db = self._get_db()
            db.save_intelligence(record)
            logger.info(
                "[INTEL] %s | Collection %s ✅ | "
                "Narrative=%s | Viral=%.1f | News=%.1f | MomentumMC=%.2f",
                symbol, label,
                record.get("primary_narrative", "Unknown"),
                record.get("viral_score", 0.0),
                record.get("news_score", 0.0),
                record.get("mc_velocity", 0.0),
            )
        except Exception as e:
            logger.error("[INTEL] %s | %s | SAVE FAILED: %s", symbol, label, e)


# ======================================================
# COMPOSITE VIRAL SCORE
# ======================================================

def _compute_composite_viral_score(record: dict) -> float:
    """
    Computes a composite viral score from multiple passive signals.
    Inputs: social velocity, engagement, news freshness, narrative heat, KOL score.
    NOT used for trading — stored for ML training only.
    """
    social_velocity   = record.get("social_velocity", 0.0)
    engagement        = record.get("engagement_score", 0.0)
    community_growth  = record.get("community_growth_rate", 0.0)
    freshness         = record.get("freshness_score", 0.0)
    narrative_heat    = record.get("narrative_heat_score", 0.0)
    kol_score         = record.get("kol_score", 0.0)

    # Weights (total = 1.0)
    composite = (
        min(social_velocity * 2.0, 100.0) * 0.25 +
        engagement                         * 0.20 +
        min(community_growth * 5.0, 100.0) * 0.15 +
        freshness                           * 0.15 +
        narrative_heat                      * 0.15 +
        kol_score                           * 0.10
    )
    return round(min(composite, 100.0), 2)


# ======================================================
# SINGLETON INSTANCE
# ======================================================

intelligence_runner = IntelligenceRunner()
