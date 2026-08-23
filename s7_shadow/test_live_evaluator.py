import os
import sys
import sqlite3
import time
import json
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s7_shadow.live_evaluator import evaluate_and_record_shadow_decision, STAGE_FEATURE_BUILD, DATABASE
from database.database import database

class MockCoin:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def setup_test_db():
    print("Setting up test database...")
    with database.db_lock:
        conn = sqlite3.connect(DATABASE)
        # Create necessary tables if they don't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                signal_id TEXT, timestamp TEXT,
                market_cap REAL, price REAL, liquidity REAL,
                volume REAL, buys REAL, sells REAL,
                holders REAL, market_health REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intelligence (
                signal_id TEXT, collected_at REAL,
                buy_sell_ratio REAL, sentiment_strength REAL,
                mc_velocity REAL, volume_velocity REAL,
                liquidity_change REAL, mc_acceleration REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS s7_shadow_decisions (
                signal_id TEXT PRIMARY KEY, symbol TEXT, decision_timestamp REAL, model_version TEXT,
                opportunity_score REAL, execution_risk_score REAL, net_score REAL,
                shadow_allocation REAL,
                estimated_entry_impact REAL, estimated_exit_impact REAL,
                estimated_round_trip_cost REAL,
                s6_decision TEXT, s6_allocation REAL,
                feature_version TEXT, dataset_version TEXT,
                feature_snapshot_json TEXT, execution_snapshot_json TEXT,
                t0_timestamp REAL, intel_source_timestamp REAL,
                snapshot_source_timestamp REAL, created_at TEXT,
                p_rug REAL, p_2x REAL, p_5x REAL, p_10x REAL,
                expected_return REAL, rank_percentile REAL, confidence REAL,
                recommendation TEXT, ml_shadow_allocation REAL
            )
        """)
        conn.commit()
        conn.close()

def seed_data(signal_id, ts, snap_delay=10, with_intel=True):
    with database.db_lock:
        conn = sqlite3.connect(DATABASE)
        # Snapshots: delayed
        snap_ts = ts + snap_delay
        conn.execute("""
            INSERT INTO snapshots (signal_id, timestamp, market_cap, price, liquidity, volume, buys, sells, holders, market_health)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (signal_id, str(snap_ts), 1000000, 0.01, 50000, 10000, 150, 50, 500, 0.9))
        
        # Intelligence
        if with_intel:
            intel_ts = ts + snap_delay + 5
            conn.execute("""
                INSERT INTO intelligence (signal_id, collected_at, buy_sell_ratio, sentiment_strength, mc_velocity, volume_velocity, liquidity_change, mc_acceleration)
                VALUES (?,?,?,?,?,?,?,?)
            """, (signal_id, float(intel_ts), 1.2, 0.8, 0.1, 0.05, 0.01, 0.02))
        
        conn.commit()
        conn.close()

def run_test():
    setup_test_db()
    
    print("\n--- TEST 1: ISO Timestamp, T0 Snapshot, With Intelligence ---")
    iso_ts = "2026-08-22T17:39:58.239861"
    # parse roughly
    from analytics.profitability_model.feature_builder import parse_ts
    numeric_ts = parse_ts(iso_ts)
    
    coin1 = MockCoin(
        signal_id="TEST_KABO_1",
        symbol="KABO",
        signal_time=iso_ts,
        # 'timestamp' is intentionally missing to test KeyError
        telegram_message="MC: $1.2M\nAge: 5m\nHolders: 500\nTop10: 15%\nBundled: 0%\nJeeters: 5%\nSnipers: 1%\nDev: 2%\nSafe: 100%"
    )
    
    seed_data("TEST_KABO_1", numeric_ts, snap_delay=5, with_intel=True)
    
    evaluate_and_record_shadow_decision(coin1, 50.0, "BUY")
    
    # Wait for daemon thread to finish
    time.sleep(2)
    
    print("\n--- TEST 2: ISO Timestamp, Missing Intelligence ---")
    coin2 = MockCoin(
        signal_id="TEST_KABO_2",
        symbol="KABO",
        signal_time=iso_ts,
        telegram_message="MC: $1.2M"
    )
    seed_data("TEST_KABO_2", numeric_ts, snap_delay=5, with_intel=False)
    
    evaluate_and_record_shadow_decision(coin2, 0.0, "SKIP")
    
    time.sleep(2)
    
    # Verify records
    with database.db_lock:
        conn = sqlite3.connect(DATABASE)
        rows = conn.execute("SELECT signal_id, recommendation, s6_decision, feature_snapshot_json, intel_source_timestamp FROM s7_shadow_decisions WHERE signal_id IN ('TEST_KABO_1', 'TEST_KABO_2')").fetchall()
        print("\n--- RESULTS IN DB ---")
        for r in rows:
            print(f"Signal ID: {r[0]}")
            print(f"  Recommendation: {r[1]}")
            print(f"  S6 Decision: {r[2]}")
            print(f"  Intel Source TS: {r[4]}")
            feats = json.loads(r[3])
            print(f"  Features size: {len(feats)}")
            print(f"  Has F_t0_snap_mc: {'F_t0_snap_mc' in feats}")
            print(f"  Has F_t0_intel_sent: {'F_t0_intel_sent' in feats}")
            print("-" * 20)
        conn.close()
    
    print("\nTests complete!")

if __name__ == "__main__":
    run_test()
