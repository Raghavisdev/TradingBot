import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import json
import dateutil.parser
from datetime import timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import DATABASE
from analytics.s7_dataset.feature_engineering import engineer_features
from analytics.s7_dataset.labels import engineer_labels

class S7DatasetBuilderV2:
    def __init__(self, db_path=DATABASE):
        self.db_path = os.path.abspath(db_path)
        print(f"Using Database: {self.db_path}")

    def parse_timestamp(self, ts_str):
        if ts_str is None:
            return 0.0
        try:
            return float(ts_str)
        except (TypeError, ValueError):
            pass
        try:
            dt = dateutil.parser.parse(str(ts_str))
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def build(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM signals")
            signals = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            signals = []

        try:
            cursor.execute("SELECT * FROM outcomes")
            outcomes = {row['signal_id']: dict(row) for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            outcomes = {}

        dataset = []
        seen_signals = set()

        report = {
            'total_signals': len(signals),
            'resolved_signals': 0,
            'unresolved_signals': 0,
            's6_buy': 0,
            's6_skip': 0,
            's6_watch': 0,
            'y_2x': 0,
            'y_5x': 0,
            'y_10x': 0,
            'y_rug': 0,
            'missed_2x': 0,
            'missed_5x': 0,
            'missed_10x': 0,
            'duplicate_signals': 0
        }

        for sig in signals:
            sig_id = sig.get('signal_id')
            if not sig_id:
                continue

            if sig_id in seen_signals:
                report['duplicate_signals'] += 1
                continue
            seen_signals.add(sig_id)

            t0 = self.parse_timestamp(sig.get('timestamp'))

            decision = sig.get('decision', 'UNKNOWN')
            if decision == 'BUY': report['s6_buy'] += 1
            elif decision == 'SKIP': report['s6_skip'] += 1
            elif decision == 'WATCH': report['s6_watch'] += 1

            cursor.execute('''
                SELECT * FROM snapshots
                WHERE signal_id = ? AND CAST(timestamp AS REAL) <= ?
                ORDER BY CAST(timestamp AS REAL) DESC LIMIT 1
            ''', (sig_id, t0))
            snap_row = cursor.fetchone()
            snap_dict = dict(snap_row) if snap_row else {}

            cursor.execute('''
                SELECT * FROM intelligence
                WHERE signal_id = ? AND CAST(collected_at AS REAL) <= ?
                ORDER BY CAST(collected_at AS REAL) DESC LIMIT 1
            ''', (sig_id, t0))
            intel_row = cursor.fetchone()
            intel_dict = dict(intel_row) if intel_row else {}

            features = engineer_features(sig, snap_dict, intel_dict)
            outcome = outcomes.get(sig_id)
            labels = engineer_labels(outcome)

            if labels['label_resolved'] == 1:
                report['resolved_signals'] += 1
                report['y_2x'] += labels['Y_2x']
                report['y_5x'] += labels['Y_5x']
                report['y_10x'] += labels['Y_10x']
                report['y_rug'] += labels['Y_rug']

                if decision in ['SKIP', 'WATCH']:
                    if labels['Y_2x'] == 1: report['missed_2x'] += 1
                    if labels['Y_5x'] == 1: report['missed_5x'] += 1
                    if labels['Y_10x'] == 1: report['missed_10x'] += 1
            else:
                report['unresolved_signals'] += 1

            row = {'signal_id': sig_id, 't0_timestamp': t0}
            row.update(features)
            row.update(labels)
            dataset.append(row)

        conn.close()

        df = pd.DataFrame(dataset)
        out_dir = os.path.dirname(__file__)
        csv_path = os.path.join(out_dir, 's7_training_dataset_v2.csv')
        df.to_csv(csv_path, index=False)

        # Missingness
        missingness = (df.isna().sum() / len(df) * 100).to_dict()

        report_txt = f"""=== S7 V2 DATASET ===
Total signals: {report['total_signals']}
Resolved signals: {report['resolved_signals']}
Unresolved signals: {report['unresolved_signals']}
Duplicates: {report['duplicate_signals']}

=== S6 DISTRIBUTIONS ===
BUY: {report['s6_buy']}
SKIP: {report['s6_skip']}
WATCH: {report['s6_watch']}

=== LABELS ===
Y_2x: {report['y_2x']}
Y_5x: {report['y_5x']}
Y_10x: {report['y_10x']}
Y_rug: {report['y_rug']}

=== MISSED WINNERS (SKIP/WATCH) ===
Missed 2x: {report['missed_2x']}
Missed 5x: {report['missed_5x']}
Missed 10x: {report['missed_10x']}

=== MISSINGNESS ===
{json.dumps(missingness, indent=2)}
"""
        with open(os.path.join(out_dir, 's7_dataset_v2_report.txt'), 'w', encoding='utf-8') as f:
            f.write(report_txt)

        return df, report

if __name__ == "__main__":
    builder = S7DatasetBuilderV2()
    builder.build()
