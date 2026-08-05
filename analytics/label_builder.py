class LabelBuilder:

    def __init__(self):
        pass

    # =====================================================
    # BUILD LABELS
    # =====================================================

    def build_labels(self, outcome_row):
        """
        Generate supervised learning labels from an outcome record.
        Reads exclusively from outcomes table data.
        """
        def get_val(key, default=0):
            if isinstance(outcome_row, dict):
                val = outcome_row.get(key, default)
            elif hasattr(outcome_row, "get"):
                val = outcome_row.get(key, default)
            elif hasattr(outcome_row, key):
                val = getattr(outcome_row, key, default)
            else:
                val = default
            return default if val is None else val

        labels = {}

        labels["returned_2x"] = int(bool(get_val("returned_2x", 0)))
        labels["returned_5x"] = int(bool(get_val("returned_5x", 0)))
        labels["returned_10x"] = int(bool(get_val("returned_10x", 0)))
        labels["rugged"] = int(bool(get_val("rugged", 0)))
        labels["max_return"] = float(get_val("max_return", 0.0))
        labels["min_return"] = float(get_val("min_return", 0.0))
        labels["time_to_peak"] = float(get_val("time_to_peak", 0.0))
        labels["tracking_duration"] = float(get_val("tracking_duration", 0.0))
        labels["tracking_end_reason"] = str(get_val("tracking_end_reason", "NORMAL_24H"))

        return labels

    def build(self, outcome_row):
        return self.build_labels(outcome_row)


label_builder = LabelBuilder()