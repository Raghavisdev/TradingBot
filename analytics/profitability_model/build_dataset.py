import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

from analytics.profitability_model.feature_builder import build_all_features, parse_ts, WINDOWS_SECONDS
from analytics.profitability_model.targets import get_targets
from analytics.profitability_model.temporal_split import split_chronological

class ProfitabilityDatasetBuilder:
    def __init__(self, db_path):
        self.db_path = db_path
        self.windows_sec = WINDOWS_SECONDS
        
    def build(self):
        print(f"Connecting to database: {self.db_path}")
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        
        # 1. Fetch signals
        signals = con.execute("SELECT * FROM signals ORDER BY timestamp ASC").fetchall()
        print(f"Loaded {len(signals)} signals.")
        
        dataset = []
        seen = set()
        duplicates = 0
        
        # Stats for report
        stats = {
            'total_signals': len(signals),
            'usable': 0,
            'duplicates': 0,
            'missing_outcomes': 0,
            'valid_t0_snap': 0,
            'valid_t0_intel': 0,
        }
        
        for sig in signals:
            sig_id = sig['signal_id']
            if sig_id in seen:
                stats['duplicates'] += 1
                continue
            seen.add(sig_id)
            
            # Target construction (must have outcomes)
            targets = get_targets(con, sig_id)
            if not targets:
                stats['missing_outcomes'] += 1
                continue
                
            stats['usable'] += 1
            
            # Feature construction
            features = build_all_features(con, dict(sig), self.windows_sec)
            
            if not np.isnan(features.get('t0_snapshot_lag_s', np.nan)):
                stats['valid_t0_snap'] += 1
                
            if not np.isnan(features.get('t0_intel_lag_s', np.nan)):
                stats['valid_t0_intel'] += 1
            
            row = {'signal_id': sig_id, 'signal_timestamp': parse_ts(sig['timestamp'])}
            row.update(features)
            row.update(targets)
            
            dataset.append(row)
            
        df = pd.DataFrame(dataset)
        
        # Splits
        df, ranges = split_chronological(df)
        
        # Missingness
        feat_cols = [c for c in df.columns if c.startswith('F_')]
        missingness = (df[feat_cols].isna().sum() / len(df) * 100).to_dict()
        
        # Save CSV
        out_dir = os.path.dirname(__file__)
        csv_path = os.path.join(out_dir, 'canonical_dataset.csv')
        df.to_csv(csv_path, index=False)
        
        self.generate_report(df, stats, ranges, missingness, out_dir, csv_path)
        con.close()
        print(f"Done. Dataset saved to {csv_path}")
        
    def generate_report(self, df, stats, ranges, missingness, out_dir, csv_path):
        db_size_mb = os.path.getsize(self.db_path) / (1024*1024)
        
        # Target dists
        target_cols = [c for c in df.columns if c.startswith('T_') and 'raw' not in c and 'log' not in c]
        t_dists = {}
        for c in target_cols:
            t_dists[c] = df[c].sum()
            
        md = f"""# Canonical Dataset Quality Report
**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Database:** `{self.db_path}` ({db_size_mb:.1f} MB)

## 1. Pipeline Statistics
- Total signals evaluated: {stats['total_signals']}
- Duplicate signals rejected: {stats['duplicates']}
- Signals missing outcomes rejected: {stats['missing_outcomes']}
- **Usable training examples: {stats['usable']}**

## 2. Temporal Alignment
- Signals with valid T0 snapshot (<=120s lag): {stats['valid_t0_snap']} ({(stats['valid_t0_snap']/stats['usable']*100):.1f}%)
- Signals with valid T0 intelligence (<=120s lag): {stats['valid_t0_intel']} ({(stats['valid_t0_intel']/stats['usable']*100):.1f}%)
- Average T0 snapshot lag: {df['t0_snapshot_lag_s'].mean():.1f}s

## 3. Chronological Splits
No random splitting. Strictly ordered by `signal_timestamp`.

- **TRAIN** (60%): {ranges['TRAIN']['count']} signals | {ranges['TRAIN']['start']} to {ranges['TRAIN']['end']}
- **VALIDATION** (20%): {ranges['VALIDATION']['count']} signals | {ranges['VALIDATION']['start']} to {ranges['VALIDATION']['end']}
- **TEST** (20%): {ranges['TEST']['count']} signals | {ranges['TEST']['start']} to {ranges['TEST']['end']}

## 4. Target Distributions (from {stats['usable']} usable signals)
"""
        for k, v in t_dists.items():
            pct = (v / stats['usable']) * 100
            md += f"- **{k}**: {v} ({pct:.1f}%)\n"
            
        md += f"""
## 5. Feature Coverage Analysis
Percentage of missing values per feature window:
"""
        
        # Group missingness by window
        windows = ['t0', '30s', '1m', '3m', '5m', '10m', '15m', '30m', '60m']
        for w in windows:
            w_cols = [k for k in missingness.keys() if f'_{w}_' in k or f'_{w}' in k]
            if not w_cols: continue
            avg_miss = np.mean([missingness[k] for k in w_cols])
            md += f"- Window `{w}`: {avg_miss:.1f}% missing on average\n"
            
        # Top 5 most missing
        sorted_miss = sorted(missingness.items(), key=lambda x: x[1], reverse=True)
        md += "\n**Top 10 highest missingness features:**\n"
        for k, v in sorted_miss[:10]:
            md += f"- `{k}`: {v:.1f}%\n"

        md += """
## 6. Leakage Audit
- **T0 Snapshot Leakage:** T0 constrained to [0, +120s] from signal time.
- **Window Leakage:** Window snapshot queries explicitly filter `timestamp <= signal_time + window`.
- **Label Leakage:** Target building is entirely isolated in `targets.py`. Output CSV columns prefixed with `T_` never enter the `F_` feature block.
"""
        
        report_path = os.path.join(out_dir, 'dataset_report.md')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(md)
            
if __name__ == '__main__':
    # Can run locally against dev DB
    builder = ProfitabilityDatasetBuilder("database/trading.db")
    builder.build()
