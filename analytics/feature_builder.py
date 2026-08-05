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

    def build(self, row):
        return self.build_features(row)


feature_builder = FeatureBuilder()