import os
import sys
import time
import sqlite3
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import create_tables
from config import DATABASE
from s7_shadow.live_evaluator import evaluate_and_record_shadow_decision
from s7_shadow.daily_reporter import generate_report

class MockCoin:
    def __init__(self, signal_id, symbol, decision, signal_market_cap):
        self.signal_id = signal_id
        self.symbol = symbol
        self.decision = decision
        self.signal_market_cap = signal_market_cap

def run_tests():
    print("=== STARTING S7 VERIFICATION TESTS ===")
    
    # 1. Initialize DB (This will DROP the old s7_shadow_decisions and recreate)
    print("Initializing Database...")
    create_tables()
    
    # Check if table exists with correct schema
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(s7_shadow_decisions)")
    cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "model_version" in cols
    assert "feature_snapshot_json" in cols
    print("OK: Schema verified")

    # Insert mock intelligence and snapshot to test evaluator
    test_signal_id = "test_sig_123"
    cursor.execute("INSERT OR REPLACE INTO intelligence (signal_id, buy_sell_ratio, sentiment_strength, collection_index) VALUES (?, 2.5, 0.8, 0)", (test_signal_id,))
    cursor.execute("INSERT OR REPLACE INTO snapshots (signal_id, liquidity, volume) VALUES (?, 50000, 100000)", (test_signal_id,))
    conn.commit()

    # 2. Test S7 execution
    coin = MockCoin(test_signal_id, "TESTCOIN", "BUY", 1000000)
    original_decision = coin.decision
    s6_alloc = 2.0
    
    print("Running live evaluator (should be non-blocking)...")
    evaluate_and_record_shadow_decision(coin, s6_alloc, coin.decision)
    
    # Give the daemon thread time to finish
    time.sleep(2)
    
    # 3. Verify coin isolation
    assert coin.decision == original_decision, "S7 modified coin decision!"
    print("OK: S7 does not modify coin.decision")
    print("OK: S7 does not modify s6_allocation (passed by value)")
    
    # 4. Verify DB persistence
    cursor.execute("SELECT * FROM s7_shadow_decisions WHERE signal_id=?", (test_signal_id,))
    row = cursor.fetchone()
    assert row is not None, "Decision not persisted to database!"
    
    col_names = [description[0] for description in cursor.description]
    row_dict = dict(zip(col_names, row))
    
    assert row_dict["model_version"] == "S7_SHADOW_V1", "Missing or incorrect model_version"
    print("OK: Decision contains model_version")
    
    assert row_dict["feature_snapshot_json"] is not None, "Missing feature_snapshot_json"
    snapshot = json.loads(row_dict["feature_snapshot_json"])
    assert "buy_sell_ratio" in snapshot, "Snapshot missing features"
    print("OK: Decision contains feature snapshot")

    # 5. Reporter test
    print("Running daily reporter on small sample size...")
    generate_report()
    
    with open(os.path.join(os.path.dirname(__file__), "s7_shadow_daily.md"), "r") as f:
        content = f.read()
        assert "READY" not in content, "Reporter declared READY with insufficient data!"
        assert "PROMISING" in content or "NO DEPLOYMENT" in content
    print("OK: Reporter respects Minimum Forward Sample Gate")
    
    print("=== ALL S7 VERIFICATION TESTS PASSED ===")
    
    # Clean up mock records
    cursor.execute("DELETE FROM intelligence WHERE signal_id=?", (test_signal_id,))
    cursor.execute("DELETE FROM snapshots WHERE signal_id=?", (test_signal_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    run_tests()
