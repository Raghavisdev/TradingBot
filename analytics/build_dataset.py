import os
import sqlite3
import csv

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

from database.models import DATABASE
from analytics.feature_builder import feature_builder
from analytics.label_builder import label_builder


class DatasetBuilder:

    def __init__(self, db_path=DATABASE):
        self.db_path = os.path.abspath(db_path)

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # ======================================================
    # LOAD DATA
    # ======================================================

    def fetch_all_as_dicts(self, table_name):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = [dict(r) for r in cursor.fetchall()]
        except Exception:
            rows = []
        finally:
            conn.close()
        return rows

    # ======================================================
    # BUILD DATASET
    # ======================================================

    def build(self):
        print("\n==================================================")
        print("BUILDING ML TRAINING DATASET")
        print("==================================================")

        # Step 1: Read database tables
        signals_list = self.fetch_all_as_dicts("signals")
        outcomes_list = self.fetch_all_as_dicts("outcomes")
        snapshots_list = self.fetch_all_as_dicts("snapshots")

        signals_loaded = len(signals_list)
        outcomes_loaded = len(outcomes_list)
        snapshots_loaded = len(snapshots_list)

        print(f"Loaded Signals    : {signals_loaded}")
        print(f"Loaded Outcomes   : {outcomes_loaded}")
        print(f"Loaded Snapshots  : {snapshots_loaded}")

        all_cols = [
            "signal_id", "timestamp", "symbol", "contract", "source", "bot_version",
            "gt_score", "signal_market_cap", "liquidity", "volume", "holders",
            "top10", "bundled", "jeeters", "fresh", "snipers", "insiders", "dev",
            "safe", "poor", "community", "whales", "win_rate", "market_health",
            "final_score", "decision", "returned_2x", "returned_5x", "returned_10x",
            "rugged", "max_return", "min_return", "time_to_peak", "tracking_duration",
            "tracking_end_reason"
        ]

        if not signals_list or not outcomes_list:
            print("[INFO] No complete signals + outcomes found. Returning empty dataset structure.")
            if HAS_PANDAS:
                return pd.DataFrame(columns=all_cols)
            return []

        # Index initial snapshots by signal_id
        initial_snapshots = {}
        for snap in snapshots_list:
            sid = snap.get("signal_id")
            if sid and sid not in initial_snapshots:
                initial_snapshots[sid] = snap

        # Index outcomes by signal_id
        outcomes_by_id = {}
        for out in outcomes_list:
            sid = out.get("signal_id")
            if sid:
                outcomes_by_id[sid] = out

        # Merge signals + initial snapshot + outcome (one row per signal_id)
        formatted_rows = []
        seen_signal_ids = set()

        for sig in signals_list:
            sid = sig.get("signal_id")
            if not sid or sid in seen_signal_ids:
                continue

            # Require an outcome record for training labels
            if sid not in outcomes_by_id:
                continue

            seen_signal_ids.add(sid)
            snap = initial_snapshots.get(sid, {})
            out = outcomes_by_id.get(sid, {})

            # Combine signal data with initial snapshot data
            combined_context = {**snap, **sig}

            # Generate features & labels
            features = feature_builder.build_features(combined_context)
            labels = label_builder.build_labels(out)

            meta = {
                "signal_id": sid,
                "timestamp": sig.get("timestamp", ""),
                "symbol": sig.get("symbol", ""),
                "contract": sig.get("contract", ""),
                "source": sig.get("source", "GemTools"),
                "bot_version": sig.get("bot_version", "1.0")
            }

            combined_row = {**meta, **features, **labels}
            formatted_rows.append(combined_row)

        # Verification metrics
        duplicate_ids = len(formatted_rows) - len(seen_signal_ids)
        label_cols = ["returned_2x", "returned_5x", "returned_10x", "rugged", "max_return", "min_return", "time_to_peak", "tracking_duration", "tracking_end_reason"]
        missing_labels = sum(1 for r in formatted_rows if any(r.get(c) is None for c in label_cols))

        print("--------------------------------------------------")
        print(f"Exported Rows        : {len(formatted_rows)}")
        print(f"Duplicate Signal IDs : {duplicate_ids}")
        print(f"Missing Labels       : {missing_labels}")
        print(f"Total Columns        : {len(formatted_rows[0].keys()) if formatted_rows else len(all_cols)}")
        print("==================================================\n")

        if HAS_PANDAS:
            return pd.DataFrame(formatted_rows, columns=all_cols) if formatted_rows else pd.DataFrame(columns=all_cols)
        return formatted_rows

    # ======================================================
    # SAVE CSV
    # ======================================================

    def save(self, filename="training_dataset.csv"):
        dataset = self.build()

        all_cols = [
            "signal_id", "timestamp", "symbol", "contract", "source", "bot_version",
            "gt_score", "signal_market_cap", "liquidity", "volume", "holders",
            "top10", "bundled", "jeeters", "fresh", "snipers", "insiders", "dev",
            "safe", "poor", "community", "whales", "win_rate", "market_health",
            "final_score", "decision", "returned_2x", "returned_5x", "returned_10x",
            "rugged", "max_return", "min_return", "time_to_peak", "tracking_duration",
            "tracking_end_reason"
        ]

        if HAS_PANDAS and isinstance(dataset, pd.DataFrame):
            dataset.to_csv(filename, index=False)
        else:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=all_cols if not dataset else list(dataset[0].keys()))
                writer.writeheader()
                if dataset:
                    writer.writerows(dataset)

        print(f"[SUCCESS] Saved ML Dataset to: {os.path.abspath(filename)}")
        return dataset


if __name__ == "__main__":
    builder = DatasetBuilder()
    builder.save()