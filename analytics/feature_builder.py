class FeatureBuilder:

    def __init__(self):
        pass

    # ==================================================
    # BUILD FEATURES
    # ==================================================

    def build_features(self, row):
        """
        Extract ML input features representing information available at signal time.
        Works with a dict, pandas Series, or object with attributes/keys.
        """
        def get_val(key, default=0):
            if isinstance(row, dict):
                val = row.get(key, default)
            elif hasattr(row, "get"):
                val = row.get(key, default)
            elif hasattr(row, key):
                val = getattr(row, key, default)
            else:
                val = default
            return default if val is None else val

        features = {}

        # Core score & signal metrics
        features["gt_score"] = int(get_val("gt_score", 0))
        features["signal_market_cap"] = float(get_val("signal_market_cap", 0.0))
        features["liquidity"] = float(get_val("liquidity", 0.0))
        features["volume"] = float(get_val("volume", get_val("volume_5m", 0.0)))

        # Holder breakdown
        features["holders"] = int(get_val("holders", 0))
        features["top10"] = float(get_val("top10", 0.0))
        features["bundled"] = float(get_val("bundled", 0.0))
        features["jeeters"] = float(get_val("jeeters", 0.0))
        features["fresh"] = float(get_val("fresh", 0.0))
        features["snipers"] = float(get_val("snipers", 0.0))
        features["insiders"] = float(get_val("insiders", 0.0))
        features["dev"] = float(get_val("dev", 0.0))

        # Risk & safety metrics
        features["safe"] = float(get_val("safe", 0.0))
        features["poor"] = float(get_val("poor", 0.0))
        features["community"] = float(get_val("community", 0.0))
        features["whales"] = float(get_val("whales", 0.0))
        features["win_rate"] = float(get_val("win_rate", 0.0))

        # AI decisions & health
        features["market_health"] = float(get_val("market_health", 0.0))
        features["final_score"] = float(get_val("final_score", 0.0))
        features["decision"] = str(get_val("decision", ""))

        return features

    # ==================================================
    # BUILD INTELLIGENCE FEATURES (AI V2)
    # ==================================================

    def build_intelligence_features(self, intel_row):
        """
        Extract intelligence features from an intelligence table record.
        Works with a dict. Returns all zeros safely when data is missing.
        Includes all v2 fields: velocity, acceleration, freshness, community.
        """
        if not intel_row:
            return self._empty_intelligence_features()

        def get_val(key, default=0):
            if isinstance(intel_row, dict):
                val = intel_row.get(key, default)
            elif hasattr(intel_row, "get"):
                val = intel_row.get(key, default)
            elif hasattr(intel_row, key):
                val = getattr(intel_row, key, default)
            else:
                val = default
            return default if val is None else val

        intel = {}

        # Time-series context
        intel["collection_index"]   = int(get_val("collection_index", 0))
        intel["collection_minutes"] = float(get_val("collection_minutes", 0.0))

        # Social v2
        intel["social_mentions"]     = int(get_val("social_mentions", 0))
        intel["social_velocity"]     = float(get_val("social_velocity", 0.0))
        intel["mentions_per_minute"] = float(get_val("mentions_per_minute", 0.0))
        intel["growth_rate"]         = float(get_val("growth_rate", 0.0))
        intel["viral_acceleration"]  = float(get_val("viral_acceleration", 0.0))
        intel["engagement_velocity"] = float(get_val("engagement_velocity", 0.0))
        intel["engagement_score"]    = float(get_val("engagement_score", 0.0))
        intel["viral_score"]         = float(get_val("viral_score", 0.0))

        # News v2
        intel["news_score"]       = float(get_val("news_score", 0.0))
        intel["news_sentiment"]   = str(get_val("news_sentiment", "neutral"))
        intel["news_minutes_old"] = float(get_val("news_minutes_old", 0.0))
        intel["news_credibility"] = float(get_val("news_credibility", 0.0))
        intel["news_source"]      = str(get_val("news_source", ""))
        intel["freshness_score"]  = float(get_val("freshness_score", 0.0))

        # Sentiment v2
        intel["sentiment_positive"]   = float(get_val("sentiment_positive", 0.0))
        intel["sentiment_neutral"]    = float(get_val("sentiment_neutral", 1.0))
        intel["sentiment_negative"]   = float(get_val("sentiment_negative", 0.0))
        intel["sentiment_confidence"] = float(get_val("sentiment_confidence", 0.0))
        intel["sentiment_strength"]   = float(get_val("sentiment_strength", 0.0))

        # Sarcasm
        intel["sarcasm_probability"] = float(get_val("sarcasm_probability", 0.0))

        # Narrative
        intel["primary_narrative"]    = str(get_val("primary_narrative", "Unknown"))
        intel["secondary_narrative"]  = str(get_val("secondary_narrative", ""))
        intel["narrative_confidence"] = float(get_val("narrative_confidence", 0.0))
        intel["narrative_heat_score"] = float(get_val("narrative_heat_score", 0.0))

        # KOL
        intel["kol_mentions"] = int(get_val("kol_mentions", 0))
        intel["kol_score"]    = float(get_val("kol_score", 0.0))

        # Community v2
        intel["telegram_members"]      = int(get_val("telegram_members", 0))
        intel["twitter_followers"]     = int(get_val("twitter_followers", 0))
        intel["community_growth_rate"] = float(get_val("community_growth_rate", 0.0))
        intel["message_rate"]          = float(get_val("message_rate", 0.0))
        intel["active_users"]          = int(get_val("active_users", 0))

        # Momentum velocity
        intel["mc_velocity"]      = float(get_val("mc_velocity", 0.0))
        intel["holder_velocity"]  = float(get_val("holder_velocity", 0.0))
        intel["volume_velocity"]  = float(get_val("volume_velocity", 0.0))
        intel["buy_velocity"]     = float(get_val("buy_velocity", 0.0))
        intel["liquidity_change"] = float(get_val("liquidity_change", 0.0))

        # Momentum acceleration v2
        intel["mc_acceleration"]     = float(get_val("mc_acceleration", 0.0))
        intel["holder_acceleration"] = float(get_val("holder_acceleration", 0.0))
        intel["volume_acceleration"] = float(get_val("volume_acceleration", 0.0))
        intel["buy_sell_ratio"]      = float(get_val("buy_sell_ratio", 0.0))

        return intel

    # ==================================================
    # AGGREGATE TIME-SERIES INTELLIGENCE
    # ==================================================

    def aggregate_intelligence_timeseries(self, intel_records: list) -> dict:
        """
        Aggregates a list of time-series intelligence records into ML features.
        Preserves temporal information by computing:
            - max values (peak performance)
            - mean values (average behavior)
            - first and last snapshot values
            - time-to-peak for key metrics

        Returns empty if no records provided.
        """
        if not intel_records:
            return self._empty_intelligence_features()

        # Sort by collection_index ascending
        records = sorted(intel_records, key=lambda r: r.get("collection_index", 0))

        first = records[0]
        last  = records[-1]

        def _max(key):
            vals = [float(r.get(key) or 0) for r in records]
            return max(vals) if vals else 0.0

        def _mean(key):
            vals = [float(r.get(key) or 0) for r in records]
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        def _first(key, default=0):
            v = first.get(key, default)
            return default if v is None else v

        def _last(key, default=0):
            v = last.get(key, default)
            return default if v is None else v

        def _time_to_peak(key):
            """Returns collection_minutes at which key was at its maximum."""
            best_val, best_mins = None, 0.0
            for r in records:
                val = float(r.get(key) or 0)
                if best_val is None or val > best_val:
                    best_val = val
                    best_mins = float(r.get("collection_minutes", 0))
            return best_mins

        agg = {}

        # Context
        agg["collection_count"] = len(records)

        # Social aggregations
        agg["max_viral_score"]        = _max("viral_score")
        agg["mean_viral_score"]       = _mean("viral_score")
        agg["max_social_velocity"]    = _max("social_velocity")
        agg["max_engagement_score"]   = _max("engagement_score")
        agg["max_mentions_per_min"]   = _max("mentions_per_minute")
        agg["max_viral_acceleration"] = _max("viral_acceleration")
        agg["time_to_peak_viral"]     = _time_to_peak("viral_score")

        # News aggregations
        agg["max_news_score"]        = _max("news_score")
        agg["mean_freshness_score"]  = _mean("freshness_score")
        agg["best_news_credibility"] = _max("news_credibility")
        agg["first_news_source"]     = str(_first("news_source", ""))
        agg["final_news_sentiment"]  = str(_last("news_sentiment", "neutral"))

        # Sentiment aggregations
        agg["mean_sentiment_positive"] = _mean("sentiment_positive")
        agg["mean_sentiment_negative"] = _mean("sentiment_negative")
        agg["max_sentiment_strength"]  = _max("sentiment_strength")
        agg["max_sarcasm_probability"] = _max("sarcasm_probability")

        # Narrative
        agg["primary_narrative"]    = str(_first("primary_narrative", "Unknown"))
        agg["max_narrative_heat"]   = _max("narrative_heat_score")
        agg["mean_narrative_heat"]  = _mean("narrative_heat_score")

        # KOL
        agg["max_kol_score"]    = _max("kol_score")
        agg["max_kol_mentions"] = _max("kol_mentions")

        # Community
        agg["max_active_users"]          = _max("active_users")
        agg["max_message_rate"]          = _max("message_rate")
        agg["community_growth_overall"]  = _max("community_growth_rate")

        # Momentum — latest is most relevant for trading features
        agg["latest_mc_velocity"]      = float(_last("mc_velocity", 0.0))
        agg["latest_holder_velocity"]  = float(_last("holder_velocity", 0.0))
        agg["latest_volume_velocity"]  = float(_last("volume_velocity", 0.0))
        agg["latest_buy_velocity"]     = float(_last("buy_velocity", 0.0))
        agg["latest_liquidity_change"] = float(_last("liquidity_change", 0.0))

        # Peak momentum
        agg["max_mc_velocity"]      = _max("mc_velocity")
        agg["max_holder_velocity"]  = _max("holder_velocity")
        agg["max_volume_velocity"]  = _max("volume_velocity")
        agg["time_to_peak_mc"]      = _time_to_peak("mc_velocity")

        # Acceleration
        agg["max_mc_acceleration"]     = _max("mc_acceleration")
        agg["max_holder_acceleration"] = _max("holder_acceleration")
        agg["latest_buy_sell_ratio"]   = float(_last("buy_sell_ratio", 0.5))

        return agg

    def _empty_intelligence_features(self):
        """Returns a zero-filled intelligence feature dict for missing records."""
        return {
            "collection_index": 0, "collection_minutes": 0.0,
            "social_mentions": 0, "social_velocity": 0.0,
            "mentions_per_minute": 0.0, "growth_rate": 0.0,
            "viral_acceleration": 0.0, "engagement_velocity": 0.0,
            "engagement_score": 0.0, "viral_score": 0.0,
            "news_score": 0.0, "news_sentiment": "neutral",
            "news_minutes_old": 0.0, "news_credibility": 0.0,
            "news_source": "", "freshness_score": 0.0,
            "sentiment_positive": 0.0, "sentiment_neutral": 1.0,
            "sentiment_negative": 0.0, "sentiment_confidence": 0.0,
            "sentiment_strength": 0.0,
            "sarcasm_probability": 0.0,
            "primary_narrative": "Unknown", "secondary_narrative": "",
            "narrative_confidence": 0.0, "narrative_heat_score": 0.0,
            "kol_mentions": 0, "kol_score": 0.0,
            "telegram_members": 0, "twitter_followers": 0,
            "community_growth_rate": 0.0, "message_rate": 0.0,
            "active_users": 0,
            "mc_velocity": 0.0, "holder_velocity": 0.0,
            "volume_velocity": 0.0, "buy_velocity": 0.0,
            "liquidity_change": 0.0,
            "mc_acceleration": 0.0, "holder_acceleration": 0.0,
            "volume_acceleration": 0.0, "buy_sell_ratio": 0.0,
        }

    def build(self, row):
        return self.build_features(row)


feature_builder = FeatureBuilder()