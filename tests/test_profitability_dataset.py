import os
import sys
import pytest
import sqlite3
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analytics.profitability_model.build_dataset import ProfitabilityDatasetBuilder
from analytics.profitability_model.temporal_split import split_chronological

@pytest.fixture
def dummy_db(tmp_path):
    db_path = str(tmp_path / "test_trading.db")
    con = sqlite3.connect(db_path)
    
    # Minimal schema
    con.execute('''CREATE TABLE signals (
        signal_id TEXT PRIMARY KEY,
        timestamp TEXT,
        gt_score REAL,
        final_score REAL,
        bought INTEGER,
        signal_market_cap REAL,
        telegram_message TEXT
    )''')
    
    con.execute('''CREATE TABLE snapshots (
        signal_id TEXT,
        timestamp TEXT,
        market_cap REAL,
        price REAL,
        liquidity REAL,
        volume REAL,
        buys INTEGER,
        sells INTEGER,
        holders INTEGER,
        market_health REAL
    )''')
    
    con.execute('''CREATE TABLE intelligence (
        signal_id TEXT,
        collected_at REAL,
        buy_sell_ratio REAL,
        sentiment_strength REAL,
        mc_velocity REAL,
        volume_velocity REAL,
        liquidity_change REAL,
        mc_acceleration REAL
    )''')
    
    con.execute('''CREATE TABLE outcomes (
        signal_id TEXT PRIMARY KEY,
        max_return REAL,
        min_return REAL,
        returned_2x INTEGER,
        returned_5x INTEGER,
        returned_10x INTEGER,
        rugged INTEGER
    )''')
    
    # Insert a test signal
    con.execute("INSERT INTO signals VALUES ('sig1', '1700000000.0', 2, 70, 0, 50000, 'MC: 50K Age: 5m Holders: 200')")
    con.execute("INSERT INTO outcomes VALUES ('sig1', 150.0, -10.0, 1, 0, 0, 0)")
    
    # Snapshots at T+10s, T+40s, T+90s
    con.execute("INSERT INTO snapshots VALUES ('sig1', '1700000010.0', 50000, 0.01, 10000, 5000, 10, 2, 200, 0.9)")
    con.execute("INSERT INTO snapshots VALUES ('sig1', '1700000040.0', 55000, 0.011, 11000, 6000, 15, 3, 210, 0.95)")
    con.execute("INSERT INTO snapshots VALUES ('sig1', '1700000090.0', 60000, 0.012, 12000, 7000, 20, 4, 220, 0.99)")
    
    con.commit()
    con.close()
    return db_path

def test_dataset_builder_runs(dummy_db):
    builder = ProfitabilityDatasetBuilder(dummy_db)
    builder.windows_sec = [0, 30, 60, 120]  # Smaller windows for testing
    builder.build()
    
    out_dir = os.path.dirname(os.path.abspath(sys.modules[builder.__module__].__file__))
    csv_path = os.path.join(out_dir, 'canonical_dataset.csv')
    
    assert os.path.exists(csv_path)
    
    df = pd.read_csv(csv_path)
    assert len(df) == 1
    assert df.iloc[0]['signal_id'] == 'sig1'
    assert df.iloc[0]['T_positive_return'] == 1
    assert df.iloc[0]['F_t0_snap_price'] == 0.01
    
    # Window 30s should pick up T+10 snapshot
    assert df.iloc[0]['F_snap_30s_price'] == 0.01
    # Window 60s should pick up T+40 snapshot
    assert df.iloc[0]['F_snap_60s_price'] == 0.011

def test_chronological_split():
    df = pd.DataFrame({
        'signal_id': ['A', 'B', 'C', 'D', 'E'],
        'signal_timestamp': [100, 500, 200, 400, 300]
    })
    
    res, ranges = split_chronological(df, train_frac=0.6, val_frac=0.2, test_frac=0.2)
    
    # Should sort A(100), C(200), E(300), D(400), B(500)
    assert res.iloc[0]['signal_id'] == 'A'
    assert res.iloc[-1]['signal_id'] == 'B'
    
    assert list(res['split']) == ['TRAIN', 'TRAIN', 'TRAIN', 'VALIDATION', 'TEST']
    assert len(set(res['signal_id'])) == 5  # No duplicates
