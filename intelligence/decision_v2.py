"""
Module 12 — Decision Engine V2 (INTERFACE ONLY — NOT ACTIVE)
--------------------------------------------------------------
This module defines the interface for a future AI-powered decision engine.

It is NOT called anywhere in the current trading pipeline.
It does NOT affect any BUY/WATCH/SKIP decisions.

Purpose:
    - Define the input contract all intelligence modules must satisfy
    - Design the future scoring architecture
    - Provide a stub that can be activated via DECISION_V2_ACTIVE=True in .env

Activation Plan:
    Phase 1: Data collection (current)
    Phase 2: Model training on exported dataset
    Phase 3: Shadow mode (logs recommendations without trading)
    Phase 4: Full activation replaces decision.py output

MODE: INTERFACE DEFINITION ONLY. NOT CALLED IN PIPELINE.
"""

import os
import logging

logger = logging.getLogger("DecisionV2")

# ==========================================================
# ACTIVATION FLAG — must be explicitly set to True in .env
# ==========================================================
DECISION_V2_ACTIVE = os.getenv("DECISION_V2_ACTIVE", "False").lower() in ("true", "1", "yes")


# ==========================================================
# FUTURE SCORING WEIGHTS (not yet active)
# ==========================================================

V2_WEIGHTS = {
    "gemtools":          0.25,  # From existing gemtools_score
    "fundamental":       0.20,  # From existing fundamental_score
    "momentum":          0.15,  # New: market cap velocity, holder velocity
    "social":            0.12,  # New: viral_score, engagement_score
    "narrative_heat":    0.10,  # New: how hot is this narrative right now
    "news":              0.08,  # New: time-decayed news_score
    "sentiment":         0.05,  # New: positive/negative sentiment ratio
    "kol":               0.05,  # New: KOL mentions + score
}

# Weights must sum to 1.0
assert abs(sum(V2_WEIGHTS.values()) - 1.0) < 0.001, "V2 weights must sum to 1.0"


# ==========================================================
# DECISION V2 INTERFACE (NOT CALLED YET)
# ==========================================================

def make_decision_v2(coin, intelligence_record: dict) -> dict:
    """
    Future AI decision function.
    Takes a Coin object and its full intelligence_record from the database.

    NOT called anywhere in the current pipeline.
    Will be activated in a future release after sufficient data collection.

    Returns:
        {
            "v2_score":    float,   # 0-100 combined score
            "v2_decision": str,     # "STRONG BUY" / "BUY" / "WATCH" / "SKIP"
            "v2_reasons":  list,    # human-readable explanation
        }
    """
    if not DECISION_V2_ACTIVE:
        logger.debug("[V2] Decision Engine V2 is INACTIVE. Skipping.")
        return {
            "v2_score": 0.0,
            "v2_decision": "INACTIVE",
            "v2_reasons": ["Decision Engine V2 is not yet activated."],
        }

    try:
        # Pull scores from coin object
        gemtools_score    = getattr(coin, "gemtools_score",    0) or 0
        fundamental_score = getattr(coin, "fundamental_score", 0) or 0

        # Pull intelligence-derived scores
        viral_score       = intelligence_record.get("viral_score",          0.0)
        news_score        = intelligence_record.get("news_score",            0.0)
        narrative_heat    = intelligence_record.get("narrative_heat_score",  0.0)
        kol_score         = intelligence_record.get("kol_score",             0.0)
        mc_velocity       = intelligence_record.get("mc_velocity",           0.0)
        sentiment_pos     = intelligence_record.get("sentiment_positive",    0.0)
        sentiment_neg     = intelligence_record.get("sentiment_negative",    0.0)

        # Momentum composite: normalize velocity to 0-100
        momentum_score = min(max(mc_velocity / 1000.0 * 100.0, 0.0), 100.0)

        # Sentiment net score (0-100)
        sentiment_score = max((sentiment_pos - sentiment_neg) * 100.0, 0.0)

        # Weighted final V2 score
        v2_score = (
            gemtools_score    * V2_WEIGHTS["gemtools"]       +
            fundamental_score * V2_WEIGHTS["fundamental"]    +
            momentum_score    * V2_WEIGHTS["momentum"]       +
            viral_score       * V2_WEIGHTS["social"]         +
            narrative_heat    * V2_WEIGHTS["narrative_heat"] +
            news_score        * V2_WEIGHTS["news"]           +
            sentiment_score   * V2_WEIGHTS["sentiment"]      +
            kol_score         * V2_WEIGHTS["kol"]
        )
        v2_score = round(min(v2_score, 100.0), 2)

        # Decision thresholds (intentionally higher than V1 for extra confidence)
        if v2_score >= 85:
            v2_decision = "STRONG BUY"
        elif v2_score >= 72:
            v2_decision = "BUY"
        elif v2_score >= 58:
            v2_decision = "WATCH"
        else:
            v2_decision = "SKIP"

        reasons = [
            f"V2 Score: {v2_score}/100 → {v2_decision}",
            f"GemTools: {gemtools_score}  Fundamental: {fundamental_score}",
            f"Momentum: {momentum_score:.1f}  Social: {viral_score:.1f}",
            f"News: {news_score:.1f}  Narrative Heat: {narrative_heat:.1f}",
            f"KOL: {kol_score:.1f}  Sentiment: {sentiment_score:.1f}",
        ]

        return {
            "v2_score": v2_score,
            "v2_decision": v2_decision,
            "v2_reasons": reasons,
        }

    except Exception as e:
        logger.error("[V2] Decision Engine V2 error: %s", e)
        return {
            "v2_score": 0.0,
            "v2_decision": "ERROR",
            "v2_reasons": [f"V2 error: {e}"],
        }
