import sys
import os
import sqlite3
import time
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import create_tables
from database.database import database
from config import DATABASE
from s7_shadow.live_evaluator import evaluate_and_record_shadow_decision
from knowledge.coin import Coin

def run_tests():
    print("==================================================")
    print("S7 TEMPORAL ALIGNMENT TESTS")
    print("==================================================")

    results = {}
    def report(name, condition):
        results[name] = "PASS" if condition else "FAIL"
        print(f"[{results[name]}] {name}")

    # Re-init db for test
    create_tables()
    conn = database.execution_logger.connection
    c = conn.cursor()
    c.execute("DELETE FROM s7_shadow_decisions")
    c.execute("DELETE FROM intelligence")
    c.execute("DELETE FROM snapshots")
    conn.commit()

    # Create a coin
    coin = Coin()
    coin.signal_id = "temp_align_sig_1"
    coin.symbol = "TEMPALIGN"
    
    # --------------------------------------------------
    # 1. Insert ONLY FUTURE data
    # --------------------------------------------------
    now = time.time()
    future_time = now + 10000
    
    c.execute("""
        INSERT INTO intelligence (signal_id, buy_sell_ratio, sentiment_strength, collected_at) 
        VALUES (?, ?, ?, ?)
    """, (coin.signal_id, 9.9, 1.0, future_time))
    
    c.execute("""
        INSERT INTO snapshots (signal_id, liquidity, volume, timestamp) 
        VALUES (?, ?, ?, ?)
    """, (coin.signal_id, 999999, 999999, future_time))
    
    conn.commit()
    
    # Run evaluator
    evaluate_and_record_shadow_decision(coin, 2.0, "BUY")
    
    # Wait for async thread
    time.sleep(2)
    
    c.execute("SELECT intel_source_timestamp, snapshot_source_timestamp FROM s7_shadow_decisions WHERE signal_id = ?", (coin.signal_id,))
    row = c.fetchone()
    
    report("1. Strictly future data is rejected (empty state)", 
           row is not None and row[0] is None and row[1] is None)
           
    # --------------------------------------------------
    # 2. Insert PAST data AND FUTURE data, ensure it picks PAST
    # --------------------------------------------------
    coin2 = Coin()
    coin2.signal_id = "temp_align_sig_2"
    coin2.symbol = "TEMPALIGN2"
    
    now = time.time()
    past_time = now - 1000
    future_time = now + 1000
    
    # Past Data
    c.execute("""
        INSERT INTO intelligence (signal_id, buy_sell_ratio, sentiment_strength, collected_at) 
        VALUES (?, ?, ?, ?)
    """, (coin2.signal_id, 1.1, 0.5, past_time))
    c.execute("""
        INSERT INTO snapshots (signal_id, liquidity, volume, timestamp) 
        VALUES (?, ?, ?, ?)
    """, (coin2.signal_id, 100, 100, past_time))
    
    # Future Data
    c.execute("""
        INSERT INTO intelligence (signal_id, buy_sell_ratio, sentiment_strength, collected_at) 
        VALUES (?, ?, ?, ?)
    """, (coin2.signal_id, 9.9, 1.0, future_time))
    c.execute("""
        INSERT INTO snapshots (signal_id, liquidity, volume, timestamp) 
        VALUES (?, ?, ?, ?)
    """, (coin2.signal_id, 999999, 999999, future_time))
    
    conn.commit()
    
    # Run evaluator
    evaluate_and_record_shadow_decision(coin2, 2.0, "BUY")
    time.sleep(2)
    
    c.execute("SELECT intel_source_timestamp, snapshot_source_timestamp FROM s7_shadow_decisions WHERE signal_id = ?", (coin2.signal_id,))
    row2 = c.fetchone()
    print(f"DEBUG: row2={row2}, expected past_time={past_time}")
    
    report("2. Correctly selects latest valid PAST data and ignores FUTURE", 
           row2 is not None and abs(row2[0] - past_time) < 0.01 and abs(row2[1] - past_time) < 0.01)
           
    print("\nTests completed.")

if __name__ == "__main__":
    run_tests()
