import sys
import os
import sqlite3
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.s7_dataset.build_dataset import S7DatasetBuilder

def setup_test_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE signals(signal_id TEXT, timestamp TEXT, tracking_started REAL, decision TEXT, bought INTEGER, symbol TEXT)''')
    c.execute('''CREATE TABLE snapshots(signal_id TEXT, timestamp REAL, liquidity REAL, volume REAL)''')
    c.execute('''CREATE TABLE intelligence(signal_id TEXT, collected_at REAL, buy_sell_ratio REAL, sentiment_strength REAL)''')
    c.execute('''CREATE TABLE outcomes(signal_id TEXT, max_return REAL, rugged INTEGER)''')
    conn.commit()
    return conn

def test_s7_dataset():
    print("==================================================")
    print("S7 DATASET TESTS")
    print("==================================================")
    
    db_path = "test_s7_dataset.db"
    conn = setup_test_db(db_path)
    c = conn.cursor()
    
    # ---------------------------------------------------------
    # Fixture 1: Perfect past data
    # ---------------------------------------------------------
    t0_1 = 1000.0
    c.execute("INSERT INTO signals VALUES ('sig1', NULL, ?, 'BUY', 1, 'COIN1')", (t0_1,))
    c.execute("INSERT INTO snapshots VALUES ('sig1', ?, 500, 1000)", (t0_1 - 10,))
    c.execute("INSERT INTO intelligence VALUES ('sig1', ?, 1.5, 0.8)", (t0_1 - 5,))
    c.execute("INSERT INTO outcomes VALUES ('sig1', 2.0, 0)")
    
    # ---------------------------------------------------------
    # Fixture 2: Past data + Future data (should pick Past)
    # ---------------------------------------------------------
    t0_2 = 2000.0
    c.execute("INSERT INTO signals VALUES ('sig2', NULL, ?, 'SKIP', 0, 'COIN2')", (t0_2,))
    c.execute("INSERT INTO snapshots VALUES ('sig2', ?, 200, 300)", (t0_2 - 50,))
    c.execute("INSERT INTO snapshots VALUES ('sig2', ?, 99999, 99999)", (t0_2 + 10,)) # FUTURE!
    c.execute("INSERT INTO intelligence VALUES ('sig2', ?, 0.5, -0.5)", (t0_2 - 20,))
    c.execute("INSERT INTO intelligence VALUES ('sig2', ?, 9.9, 1.0)", (t0_2 + 20,)) # FUTURE!
    c.execute("INSERT INTO outcomes VALUES ('sig2', -0.5, 1)")

    # ---------------------------------------------------------
    # Fixture 3: Future data only (should return NaN)
    # ---------------------------------------------------------
    t0_3 = 3000.0
    c.execute("INSERT INTO signals VALUES ('sig3', NULL, ?, 'WATCH', 0, 'COIN3')", (t0_3,))
    c.execute("INSERT INTO snapshots VALUES ('sig3', ?, 99999, 99999)", (t0_3 + 10,)) # FUTURE!
    c.execute("INSERT INTO intelligence VALUES ('sig3', ?, 9.9, 1.0)", (t0_3 + 20,)) # FUTURE!
    # No outcome

    # ---------------------------------------------------------
    # Fixture 4: Duplicate signal ID
    # ---------------------------------------------------------
    t0_4 = 4000.0
    c.execute("INSERT INTO signals VALUES ('sig4', NULL, ?, 'BUY', 1, 'COIN4')", (t0_4,))
    c.execute("INSERT INTO signals VALUES ('sig4', NULL, ?, 'BUY', 1, 'COIN4')", (t0_4 + 1,)) # Duplicate!
    
    conn.commit()
    conn.close()

    # Build dataset
    builder = S7DatasetBuilder(db_path)
    df, metrics = builder.build()
    
    # Run Validations
    errors = []
    
    # 1. One row per unique signal
    if len(df) != 4:
        errors.append(f"Expected 4 rows, got {len(df)}")
        
    # 2. No future intelligence & Latest valid past row
    sig2_row = df[df['signal_id'] == 'sig2'].iloc[0]
    if sig2_row['X_buy_sell_ratio'] != 0.5:
        errors.append(f"Future intelligence leaked or wrong row selected for sig2: {sig2_row['X_buy_sell_ratio']}")
    if sig2_row['intel_source_timestamp'] > t0_2:
        errors.append("intel_source_timestamp is in the future")
        
    # 3. No future snapshots
    if sig2_row['X_liquidity'] != 200.0:
        errors.append(f"Future snapshot leaked or wrong row selected for sig2: {sig2_row['X_liquidity']}")
    if sig2_row['snapshot_source_timestamp'] > t0_2:
        errors.append("snapshot_source_timestamp is in the future")
        
    # 4. Missing telemetry yields NaN
    sig3_row = df[df['signal_id'] == 'sig3'].iloc[0]
    if not pd.isna(sig3_row['X_liquidity']):
        errors.append(f"Future-only snapshot didn't result in NaN: {sig3_row['X_liquidity']}")
    if not pd.isna(sig3_row['X_buy_sell_ratio']):
        errors.append(f"Future-only intelligence didn't result in NaN: {sig3_row['X_buy_sell_ratio']}")
        
    # 5. Outcome separation
    if 'Y_max_return' not in df.columns or 'X_max_return' in df.columns:
        errors.append("Outcome fields not properly prefixed with Y_ or leaked into X_")
        
    # 6. Duplicates rejected
    sig4_rows = df[df['signal_id'] == 'sig4']
    if len(sig4_rows) != 1:
        errors.append("Duplicate signal IDs not rejected")

    if os.path.exists(db_path):
        os.remove(db_path)

    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        return False
    else:
        print("[PASS] All temporal and dataset validation tests passed.")
        return True

if __name__ == "__main__":
    success = test_s7_dataset()
    sys.exit(0 if success else 1)
