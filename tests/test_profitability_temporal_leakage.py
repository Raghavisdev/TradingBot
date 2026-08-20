import os
import sys
import pytest
import sqlite3
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analytics.profitability_model.feature_builder import build_all_features

@pytest.fixture
def leakage_db(tmp_path):
    db_path = str(tmp_path / "leakage_test.db")
    con = sqlite3.connect(db_path)
    
    con.execute("CREATE TABLE snapshots (signal_id TEXT, timestamp TEXT, market_cap REAL, price REAL, liquidity REAL, volume REAL, buys INTEGER, sells INTEGER, holders INTEGER, market_health REAL)")
    con.execute("CREATE TABLE intelligence (signal_id TEXT, collected_at REAL, buy_sell_ratio REAL, sentiment_strength REAL, mc_velocity REAL, volume_velocity REAL, liquidity_change REAL, mc_acceleration REAL)")
    
    # Signal at T=100
    # Snapshot at T=100, T=130, T=160 (future)
    con.execute("INSERT INTO snapshots (signal_id, timestamp, price) VALUES ('s1', '100.0', 1.0)")
    con.execute("INSERT INTO snapshots (signal_id, timestamp, price) VALUES ('s1', '130.0', 1.5)")
    con.execute("INSERT INTO snapshots (signal_id, timestamp, price) VALUES ('s1', '160.0', 9.99)") # Future for 30s window
    
    # Intelligence at T=100, T=160
    con.execute("INSERT INTO intelligence (signal_id, collected_at, sentiment_strength) VALUES ('s1', 100.0, 0.5)")
    con.execute("INSERT INTO intelligence (signal_id, collected_at, sentiment_strength) VALUES ('s1', 160.0, 0.99)") # Future for 30s window
    
    con.commit()
    return db_path

def test_no_future_snapshots_leak(leakage_db):
    con = sqlite3.connect(leakage_db)
    con.row_factory = sqlite3.Row
    
    signal_row = {'signal_id': 's1', 'timestamp': '100.0'}
    
    # Extract features up to 30s
    feat = build_all_features(con, signal_row, windows_sec=[0, 30])
    
    # T0 snapshot should be T=100 (price 1.0)
    assert feat['F_t0_snap_price'] == 1.0
    
    # 30s snapshot should be T=130 (price 1.5)
    assert feat['F_snap_30s_price'] == 1.5
    
    # Future snapshot (9.99) should NOT leak into 30s window
    assert 'F_snap_60s_price' not in feat
    
    # Intelligence T0 should be T=100 (sentiment 0.5)
    assert feat['F_t0_intel_sent'] == 0.5
    
    # Intelligence 30s should be T=100 since there is no intelligence at 130
    assert feat['F_intel_30s_sent'] == 0.5
    
    con.close()

def test_targets_completely_isolated():
    # If build_dataset is run, verify columns prefixed with F_ have no overlap with T_
    from analytics.profitability_model.build_dataset import ProfitabilityDatasetBuilder
    import inspect
    
    # Statically check targets.py does not contain 'F_' strings
    import analytics.profitability_model.targets as tgt
    source = inspect.getsource(tgt.get_targets)
    assert "F_" not in source, "Targets generator must never output F_ feature keys"
    
    # Check feature_builder does not output T_
    import analytics.profitability_model.feature_builder as fb
    source = inspect.getsource(fb.build_all_features)
    assert "T_" not in source, "Feature builder must never output T_ target keys"
