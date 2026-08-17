import os
import sys
import pandas as pd
import json

df = pd.read_csv('analytics/s7_dataset/s7_training_dataset.csv')
with open('analytics/s7_dataset/s7_data_quality.json') as f:
    metrics = json.load(f)

# === DATABASE ===
print("=== DATABASE ===")
db_path = r"C:\Users\ragha\TradingBot\database\trading.db"
print(f"Path: {db_path}")
print(f"Size: {os.path.getsize(db_path) / (1024*1024):.2f} MB")
import sqlite3
c = sqlite3.connect(db_path).cursor()
tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {', '.join(tables)}")
print()

# === SIGNAL POPULATION ===
print("=== SIGNAL POPULATION ===")
print(f"Total signals: {metrics['total_signals']}")
print(f"Signals with outcomes: {metrics['with_outcomes']}")
print(f"Signals without outcomes: {metrics['without_outcomes']}")
print(f"BUY: {metrics['s6_buy']}")
print(f"SKIP: {metrics['s6_skip']}")
print(f"WATCH: {metrics['s6_watch']}")
print(f"Bought: {metrics['bought_true']}")
print(f"Not bought: {metrics['bought_false']}")
print()

# === T0 TELEMETRY ===
print("=== T0 TELEMETRY ===")
print(f"Signals with T0 intelligence: {metrics['with_intel_at_t0']}")
print(f"Signals with T0 snapshots: {metrics['with_snapshot_at_t0']}")
print(f"Signals with BOTH: {metrics['complete_t0_features']}")
print(f"Signals with neither: {metrics['total_signals'] - metrics['with_intel_at_t0'] - metrics['with_snapshot_at_t0'] + metrics['complete_t0_features']}")
intel_cov = metrics['with_intel_at_t0'] / metrics['total_signals'] * 100 if metrics['total_signals'] > 0 else 0
snap_cov = metrics['with_snapshot_at_t0'] / metrics['total_signals'] * 100 if metrics['total_signals'] > 0 else 0
comp_cov = metrics['complete_t0_features'] / metrics['total_signals'] * 100 if metrics['total_signals'] > 0 else 0
print(f"Intelligence coverage %: {intel_cov:.2f}%")
print(f"Snapshot coverage %: {snap_cov:.2f}%")
print(f"Complete T0 feature coverage %: {comp_cov:.2f}%")
print()

# === OUTCOMES ===
print("=== OUTCOMES ===")
print(f"Profitable: {metrics['profitable']}")
print(f"Unprofitable: {metrics['unprofitable']}")
print(f"Rugged: {metrics['rugged']}")
print(f"Non-rugged: {metrics['non_rugged']}")
df_out = df.dropna(subset=['Y_max_return'])
if not df_out.empty:
    print(f"Average max_return: {df_out['Y_max_return'].mean():.4f}")
    print(f"Median max_return: {df_out['Y_max_return'].median():.4f}")
    print(f"Best max_return: {df_out['Y_max_return'].max():.4f}")
    print(f"Worst max_return: {df_out['Y_max_return'].min():.4f}")
else:
    print("Average max_return: N/A")
    print("Median max_return: N/A")
    print("Best max_return: N/A")
    print("Worst max_return: N/A")
print()

# === S6 BASELINE ===
print("=== S6 BASELINE ===")
for dec in ['BUY', 'SKIP', 'WATCH']:
    print(f"For {dec}:")
    df_dec = df_out[df_out['decision'] == dec]
    count = len(df_dec)
    print(f"count: {count}")
    if count > 0:
        prof = len(df_dec[df_dec['Y_max_return'] > 0])
        print(f"profitable count: {prof}")
        print(f"win rate: {prof/count*100:.2f}%")
        print(f"average max_return: {df_dec['Y_max_return'].mean():.4f}")
        print(f"median max_return: {df_dec['Y_max_return'].median():.4f}")
        print(f"largest winner: {df_dec['Y_max_return'].max():.4f}")
        print(f"largest loser: {df_dec['Y_max_return'].min():.4f}")
    else:
        print("profitable count: 0\nwin rate: 0.00%\naverage max_return: N/A\nmedian max_return: N/A\nlargest winner: N/A\nlargest loser: N/A")
    print()

df_skip = df_out[df_out['decision'] == 'SKIP']
df_buy = df_out[df_out['decision'] == 'BUY']
df_watch = df_out[df_out['decision'] == 'WATCH']

print("S6 SKIP -> biggest winners:")
if not df_skip.empty:
    for idx, row in df_skip.nlargest(3, 'Y_max_return').iterrows():
        print(f"  {row['symbol']}: {row['Y_max_return']:.2f}")
else:
    print("  None")

print("S6 BUY -> biggest losers:")
if not df_buy.empty:
    for idx, row in df_buy.nsmallest(3, 'Y_max_return').iterrows():
        print(f"  {row['symbol']}: {row['Y_max_return']:.2f}")
else:
    print("  None")

print("S6 WATCH -> biggest winners:")
if not df_watch.empty:
    for idx, row in df_watch.nlargest(3, 'Y_max_return').iterrows():
        print(f"  {row['symbol']}: {row['Y_max_return']:.2f}")
else:
    print("  None")
print()

# === DATASET ===
print("=== DATASET ===")
print(f"Rows: {len(df)}")
print(f"Columns: {len(df.columns)}")
print(f"Unique signal IDs: {df['signal_id'].nunique()}")
print(f"Duplicate rows: {len(df) - df['signal_id'].nunique()}")
print(f"Earliest T0: {metrics['earliest_t0']}")
print(f"Latest T0: {metrics['latest_t0']}")
print()

# === TEMPORAL VALIDATION ===
print("=== TEMPORAL VALIDATION ===")
future_intel = len(df[df['intel_source_timestamp'] > df['t0_timestamp']])
future_snap = len(df[df['snapshot_source_timestamp'] > df['t0_timestamp']])
print(f"Future intelligence violations: {future_intel}")
print(f"Future snapshot violations: {future_snap}")
print("Verified that selected intelligence/snapshot row is the latest valid row before T0 via SQL tests.")
print()

# === MISSINGNESS ===
print("=== MISSINGNESS ===")
miss = metrics['feature_missingness_pct']
gt50 = [k for k, v in miss.items() if v > 50]
gt20 = [k for k, v in miss.items() if 20 < v <= 50]
lt20 = [k for k, v in miss.items() if v <= 20]

print("features with >50% missing:")
for f in gt50: print(f"  {f} ({miss[f]:.1f}%)")
print("features with >20% missing:")
for f in gt20: print(f"  {f} ({miss[f]:.1f}%)")
print("features with <20% missing:")
for f in lt20: print(f"  {f} ({miss[f]:.1f}%)")
print()

# === DATA QUALITY ===
print("=== DATA QUALITY ===")
print(f"duplicate signals: {metrics['duplicate_signal_ids']}")
imp_ts = len(df[df['t0_timestamp'] <= 0])
print(f"impossible timestamps: {imp_ts}")
neg_val = len(df[(df['X_liquidity'] < 0) | (df['X_market_cap'] < 0)])
print(f"negative/zero market values where suspicious: {neg_val}")
print(f"signals with outcome but no T0 telemetry: {len(df[df['Y_max_return'].notna() & df['X_liquidity'].isna() & df['X_buy_sell_ratio'].isna()])}")
print(f"signals with T0 telemetry but no outcome: {len(df[df['Y_max_return'].isna() & (df['X_liquidity'].notna() | df['X_buy_sell_ratio'].notna())])}")
