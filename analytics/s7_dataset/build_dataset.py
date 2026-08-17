import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime, timezone
import dateutil.parser

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import DATABASE

SIGNAL_FEATURES = [
    'signal_id', 'symbol', 'signal_market_cap', 'gt_score', 'decision', 'bought', 't0_timestamp'
]

SNAPSHOT_FEATURES = [
    'price', 'market_cap', 'liquidity', 'volume', 'buys', 'sells'
]

INTELLIGENCE_FEATURES = [
    'social_mentions', 'social_velocity', 'mentions_per_minute', 'growth_rate', 
    'viral_acceleration', 'engagement_velocity', 'engagement_score', 'viral_score',
    'news_score', 'news_sentiment', 'news_minutes_old', 'news_credibility',
    'freshness_score', 'sentiment_positive', 'sentiment_neutral', 'sentiment_negative',
    'sentiment_confidence', 'sentiment_strength', 'sarcasm_probability',
    'narrative_confidence', 'narrative_heat_score', 'kol_mentions', 'kol_score',
    'telegram_members', 'twitter_followers', 'community_growth_rate', 'message_rate',
    'active_users', 'mc_velocity', 'holder_velocity', 'volume_velocity', 'buy_velocity',
    'liquidity_change', 'mc_acceleration', 'holder_acceleration', 'volume_acceleration',
    'buy_sell_ratio'
]

OUTCOME_FEATURES = [
    'max_return', 'peak_market_cap', 'time_to_peak', 'rugged', 'lowest_market_cap',
    'peak_price', 'lowest_price', 'min_return', 'returned_2x', 'returned_5x', 'returned_10x'
]

class S7DatasetBuilder:
    def __init__(self, db_path=DATABASE):
        self.db_path = os.path.abspath(db_path)
        print(f"Using Database: {self.db_path}")

    def parse_timestamp(self, ts_str, fallback_real):
        if fallback_real is not None:
            return fallback_real
        if ts_str is None:
            return 0.0
        try:
            dt = dateutil.parser.parse(ts_str)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except:
            return 0.0

    def build(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch signals
        try:
            cursor.execute("SELECT * FROM signals")
            signals = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            signals = []
            
        # Fetch outcomes
        try:
            cursor.execute("SELECT * FROM outcomes")
            outcomes = {row['signal_id']: dict(row) for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            outcomes = {}

        dataset = []
        quality_metrics = {
            'total_signals': len(signals),
            'with_outcomes': 0,
            'without_outcomes': 0,
            'with_intel_at_t0': 0,
            'with_snapshot_at_t0': 0,
            'complete_t0_features': 0,
            's6_buy': 0,
            's6_skip': 0,
            's6_watch': 0,
            'bought_true': 0,
            'bought_false': 0,
            'profitable': 0,
            'unprofitable': 0,
            'rugged': 0,
            'non_rugged': 0,
            'duplicate_signal_ids': 0,
            'earliest_t0': float('inf'),
            'latest_t0': 0.0
        }

        seen_signals = set()

        for sig in signals:
            sig_id = sig.get('signal_id')
            if not sig_id:
                continue
                
            if sig_id in seen_signals:
                quality_metrics['duplicate_signal_ids'] += 1
                continue
            seen_signals.add(sig_id)

            t0 = self.parse_timestamp(sig.get('timestamp'), sig.get('tracking_started'))
            
            if t0 < quality_metrics['earliest_t0'] and t0 > 0:
                quality_metrics['earliest_t0'] = t0
            if t0 > quality_metrics['latest_t0']:
                quality_metrics['latest_t0'] = t0

            decision = sig.get('decision', 'UNKNOWN')
            if decision == 'BUY': quality_metrics['s6_buy'] += 1
            elif decision == 'SKIP': quality_metrics['s6_skip'] += 1
            elif decision == 'WATCH': quality_metrics['s6_watch'] += 1

            bought = sig.get('bought')
            if bought == 1: quality_metrics['bought_true'] += 1
            else: quality_metrics['bought_false'] += 1

            # Fetch Snapshot at T0
            cursor.execute('''
                SELECT * FROM snapshots 
                WHERE signal_id = ? AND CAST(timestamp AS REAL) <= ? 
                ORDER BY CAST(timestamp AS REAL) DESC LIMIT 1
            ''', (sig_id, t0))
            snap_row = cursor.fetchone()
            snap_dict = dict(snap_row) if snap_row else {}
            if snap_row:
                quality_metrics['with_snapshot_at_t0'] += 1

            # Fetch Intelligence at T0
            cursor.execute('''
                SELECT * FROM intelligence 
                WHERE signal_id = ? AND collected_at <= ? 
                ORDER BY collected_at DESC LIMIT 1
            ''', (sig_id, t0))
            intel_row = cursor.fetchone()
            intel_dict = dict(intel_row) if intel_row else {}
            if intel_row:
                quality_metrics['with_intel_at_t0'] += 1

            # Assemble row (X)
            row = {}
            for col in SIGNAL_FEATURES:
                if col == 't0_timestamp':
                    row[col] = t0
                else:
                    row[col] = sig.get(col, np.nan)
                    
            for col in SNAPSHOT_FEATURES:
                val = snap_dict.get(col)
                row[f"X_{col}"] = val if val is not None else np.nan
                
            for col in INTELLIGENCE_FEATURES:
                val = intel_dict.get(col)
                row[f"X_{col}"] = val if val is not None else np.nan

            # Add source timestamps for temporal validation
            val_snap = snap_dict.get('timestamp')
            row['snapshot_source_timestamp'] = float(val_snap) if val_snap is not None else np.nan
            row['intel_source_timestamp'] = intel_dict.get('collected_at', np.nan)

            if snap_row and intel_row:
                quality_metrics['complete_t0_features'] += 1

            # Outcomes (Y)
            out_dict = outcomes.get(sig_id)
            if out_dict:
                quality_metrics['with_outcomes'] += 1
                max_ret = out_dict.get('max_return', 0.0)
                if max_ret is not None and max_ret > 0: quality_metrics['profitable'] += 1
                else: quality_metrics['unprofitable'] += 1
                
                if out_dict.get('rugged', 0) == 1: quality_metrics['rugged'] += 1
                else: quality_metrics['non_rugged'] += 1
            else:
                quality_metrics['without_outcomes'] += 1
                out_dict = {}

            for col in OUTCOME_FEATURES:
                val = out_dict.get(col)
                row[f"Y_{col}"] = val if val is not None else np.nan

            dataset.append(row)

        conn.close()

        df = pd.DataFrame(dataset)
        
        if quality_metrics['earliest_t0'] == float('inf'):
            quality_metrics['earliest_t0'] = 0.0

        # Feature missingness
        missingness = {}
        if not df.empty:
            for col in df.columns:
                if col.startswith('X_'):
                    pct = (df[col].isna().sum() / len(df)) * 100
                    missingness[col] = float(pct)
        quality_metrics['feature_missingness_pct'] = missingness

        return df, quality_metrics

    def save_artifacts(self, df, metrics, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
        # Save CSV
        csv_path = os.path.join(output_dir, 's7_training_dataset.csv')
        df.to_csv(csv_path, index=False)
        
        # Save JSON quality metrics
        metrics_path = os.path.join(output_dir, 's7_data_quality.json')
        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=4)
            
        # Save Schema
        schema = {
            'SIGNAL_FEATURES': SIGNAL_FEATURES,
            'SNAPSHOT_FEATURES': [f"X_{c}" for c in SNAPSHOT_FEATURES],
            'INTELLIGENCE_FEATURES': [f"X_{c}" for c in INTELLIGENCE_FEATURES],
            'OUTCOME_FEATURES': [f"Y_{c}" for c in OUTCOME_FEATURES],
            'VALIDATION_FEATURES': ['snapshot_source_timestamp', 'intel_source_timestamp']
        }
        schema_path = os.path.join(output_dir, 's7_dataset_schema.json')
        with open(schema_path, 'w') as f:
            json.dump(schema, f, indent=4)
            
        # Save Report
        report_path = os.path.join(output_dir, 's7_dataset_report.txt')
        with open(report_path, 'w') as f:
            f.write("==================================================\n")
            f.write("S7 V2 HISTORICAL DATASET REPORT\n")
            f.write("==================================================\n\n")
            f.write(f"Total signals: {metrics['total_signals']}\n")
            f.write(f"Signals with outcomes: {metrics['with_outcomes']}\n")
            f.write(f"Signals without outcomes: {metrics['without_outcomes']}\n")
            f.write(f"Signals with intelligence at T0: {metrics['with_intel_at_t0']}\n")
            f.write(f"Signals with snapshots at T0: {metrics['with_snapshot_at_t0']}\n")
            f.write(f"Signals with complete T0 feature set: {metrics['complete_t0_features']}\n\n")
            f.write("S6 Baseline:\n")
            f.write(f"BUY: {metrics['s6_buy']}\n")
            f.write(f"SKIP: {metrics['s6_skip']}\n")
            f.write(f"WATCH: {metrics['s6_watch']}\n")
            f.write(f"Bought True: {metrics['bought_true']}\n")
            f.write(f"Bought False: {metrics['bought_false']}\n\n")
            f.write("Outcomes:\n")
            f.write(f"Profitable: {metrics['profitable']}\n")
            f.write(f"Unprofitable: {metrics['unprofitable']}\n")
            f.write(f"Rugged: {metrics['rugged']}\n")
            f.write(f"Non-rugged: {metrics['non_rugged']}\n\n")
            f.write("Validation:\n")
            f.write(f"Duplicate Signal IDs: {metrics['duplicate_signal_ids']}\n")
            
        print(f"Artifacts saved to {output_dir}")

if __name__ == "__main__":
    builder = S7DatasetBuilder()
    df, metrics = builder.build()
    
    # Baseline analysis
    print(f"Total Rows: {len(df)}")
    
    output_dir = os.path.join(os.path.dirname(__file__))
    builder.save_artifacts(df, metrics, output_dir)
