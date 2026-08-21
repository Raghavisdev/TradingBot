import os
import sys
import sqlite3
import threading
import time
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE
from analytics.paper_lab.lab_portfolio import LabPortfolio
from s7_shadow.execution_intelligence import ExecutionIntelligence

from analytics.paper_lab.strategies import Strategy_S6_Moonshot_Ladder
from analytics.profitability_model.inference import ShadowInference
from analytics.profitability_model.feature_builder import build_all_features, WINDOWS_SECONDS

# Load both S6 (baseline) and S7 ML (shadow observer) globally
try:
    s6_scorer = Strategy_S6_Moonshot_Ladder()
    print(f"[S7 SHADOW] Loaded baseline S6 {s6_scorer.strategy_id} v{s6_scorer.strategy_version}")
except Exception as e:
    print(f"[S7 SHADOW] Error loading S6: {e}")
    s6_scorer = None

try:
    ml_scorer = ShadowInference(horizon='1m')
    print(f"[S7 SHADOW] Loaded canonical ML inference engine. Ready: {ml_scorer.ready}")
except Exception as e:
    print(f"[S7 SHADOW] Error loading ML Inference: {e}")
    ml_scorer = None

def evaluate_and_record_shadow_decision(coin, s6_allocation, s6_decision):
    """
    Non-blocking evaluation of S6 and S7 ML rules.
    coin: The Signal object
    s6_allocation: the allocation S6 chose (e.g. 2.0)
    s6_decision: the decision string (e.g. 'BUY', 'SKIP')
    """
    if s6_scorer is None or ml_scorer is None:
        return
        
    def _run():
        try:
            from database.database import database
            
            t0_timestamp = time.time()
            
            # Extract safe historical data up to t0_timestamp into an in-memory DB to guarantee temporal safety.
            temp_conn = sqlite3.connect(':memory:')
            temp_conn.row_factory = sqlite3.Row
            temp_conn.execute("CREATE TABLE snapshots (signal_id TEXT, timestamp REAL, market_cap REAL, price REAL, liquidity REAL, volume REAL, buys REAL, sells REAL, holders REAL, market_health REAL)")
            temp_conn.execute("CREATE TABLE intelligence (signal_id TEXT, collected_at REAL, buy_sell_ratio REAL, sentiment_strength REAL, mc_velocity REAL, volume_velocity REAL, liquidity_change REAL, mc_acceleration REAL)")
            
            intel_source_timestamp = None
            snapshot_source_timestamp = None
            
            with database.db_lock:
                conn = sqlite3.connect(DATABASE)
                
                # Fetch all safe snapshots
                snaps = conn.execute("SELECT signal_id, timestamp, market_cap, price, liquidity, volume, buys, sells, holders, market_health FROM snapshots WHERE signal_id = ? AND CAST(timestamp AS REAL) <= ?", (coin.signal_id, t0_timestamp)).fetchall()
                if snaps:
                    temp_conn.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)", snaps)
                    # The latest snapshot is the one with the highest timestamp <= t0_timestamp
                    latest_snap = max(snaps, key=lambda x: float(x[1]))
                    snapshot_source_timestamp = latest_snap[1]
                    latest_liq = latest_snap[4]
                    latest_vol = latest_snap[5]
                else:
                    latest_liq = 0.0
                    latest_vol = 0.0
                    
                # Fetch all safe intelligence
                intels = conn.execute("SELECT signal_id, collected_at, buy_sell_ratio, sentiment_strength, mc_velocity, volume_velocity, liquidity_change, mc_acceleration FROM intelligence WHERE signal_id = ? AND CAST(collected_at AS REAL) <= ?", (coin.signal_id, t0_timestamp)).fetchall()
                if intels:
                    temp_conn.executemany("INSERT INTO intelligence VALUES (?,?,?,?,?,?,?,?)", intels)
                    latest_intel = max(intels, key=lambda x: float(x[1]))
                    intel_source_timestamp = latest_intel[1]
                    latest_bs_ratio = latest_intel[2]
                else:
                    latest_bs_ratio = None
                    
                conn.close()
            
            # S6 Moonshot uses Signal dictionary
            coin_dict = vars(coin).copy() if hasattr(coin, '__dict__') else coin
            
            # Inject latest safe DB snapshot data into the S6 evaluation
            if snapshot_source_timestamp:
                coin_dict['liquidity'] = latest_liq
                coin_dict['volume'] = latest_vol
                
            if intel_source_timestamp:
                coin_dict['buy_sell_ratio'] = latest_bs_ratio
            
            # 1. EVALUATE S6 BASELINE
            mock_portfolio = LabPortfolio("mock")
            mock_portfolio.initial_cash = 500.0
            mock_portfolio.cash = 500.0
            
            # Just to prove we evaluated S6 independently
            _s6_test_alloc = s6_scorer.evaluate_entry(coin_dict, mock_portfolio)
            
            # 2. EVALUATE S7 ML SHADOW
            # Guarantee no future observations are passed to the ML engine
            features = build_all_features(temp_conn, coin_dict, WINDOWS_SECONDS)
            temp_conn.close()
            
            ml_result = ml_scorer.evaluate_signal(features)
            
            p_rug = ml_result.get("p_rug", 0.0)
            p_2x = ml_result.get("p_2x", 0.0)
            p_5x = ml_result.get("p_5x", 0.0)
            p_10x = ml_result.get("p_10x", 0.0)
            exp_ret = ml_result.get("expected_return_linear", 0.0)
            opp_score = ml_result.get("opportunity_score", 0.0)
            rec = ml_result.get("recommendation", "AVOID")
            model_ver = ml_result.get("model_version", "UNKNOWN")
            
            # Placeholder for future metrics
            rank_percentile = 0.0 
            confidence = 0.0
            
            # ML Shadow Allocation is 0.0 (Observer only)
            ml_shadow_allocation = 0.0
            
            MODEL_VERSION = model_ver
            f_version = "v1" # feature_builder version
            feature_snapshot_json = json.dumps({k: v for k, v in features.items() if not (isinstance(v, float) and v != v)}, sort_keys=True)
            
            # Generate Execution Intelligence Snapshot (P2A-1) using S6 allocation for hypothetical comparison
            exec_snapshot = ExecutionIntelligence.calculate_snapshot(coin, s6_allocation)
            execution_snapshot_json = json.dumps(exec_snapshot, sort_keys=True)
            
            est_entry = exec_snapshot["ESTIMATED"]["estimated_entry_impact"]
            est_exit = exec_snapshot["ESTIMATED"]["estimated_exit_impact"]
            est_rt = exec_snapshot["ESTIMATED"]["estimated_round_trip_cost"]
            
            # 3. Save to DB
            with database.db_lock:
                conn = sqlite3.connect(DATABASE, timeout=30.0)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO s7_shadow_decisions 
                    (signal_id, symbol, decision_timestamp, model_version, 
                     opportunity_score, execution_risk_score, net_score, shadow_allocation, 
                     estimated_entry_impact, estimated_exit_impact, estimated_round_trip_cost, 
                     s6_decision, s6_allocation, feature_version, feature_snapshot_json, execution_snapshot_json, 
                     t0_timestamp, intel_source_timestamp, snapshot_source_timestamp, created_at,
                     dataset_version, p_rug, p_2x, p_5x, p_10x, expected_return, rank_percentile,
                     confidence, recommendation, ml_shadow_allocation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    coin.signal_id,
                    coin.symbol,
                    t0_timestamp,
                    MODEL_VERSION,
                    opp_score,
                    0.0, # risk score
                    opp_score, # net score
                    0.0, # legacy shadow_allocation
                    est_entry,
                    est_exit,
                    est_rt,
                    s6_decision,
                    s6_allocation,
                    f_version,
                    feature_snapshot_json,
                    execution_snapshot_json,
                    t0_timestamp,
                    intel_source_timestamp,
                    snapshot_source_timestamp,
                    time.time(),
                    "N/A", # dataset_version
                    p_rug,
                    p_2x,
                    p_5x,
                    p_10x,
                    exp_ret,
                    rank_percentile,
                    confidence,
                    rec,
                    ml_shadow_allocation
                ))
                
                if cursor.rowcount == 0:
                    print(f"[S7 SHADOW] Ignored duplicate evaluation for {coin.symbol} (signal_id: {coin.signal_id})")
                else:
                    print(f"[S7 SHADOW] Recorded Decision for {coin.symbol}: ML Rec: {rec} (S6: ${s6_allocation})")
                    
                conn.commit()
                conn.close()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[S7 SHADOW] Exception during async evaluation: {e}")

    # Fire and forget
    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
