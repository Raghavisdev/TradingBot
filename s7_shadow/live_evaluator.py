import os
import sys
import sqlite3
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE
from s7_experiment.phase_d_e_shadow_score import ShadowScorer
from s7_experiment.phase_c_liquidity_model import MODEL_VERSION
from s7_shadow.execution_intelligence import ExecutionIntelligence
import json

# Load the model globally so it's ready in memory
try:
    scorer = ShadowScorer()
    print(f"[S7 SHADOW] Loaded model S7_SHADOW_V1")
except Exception as e:
    print(f"[S7 SHADOW] Error loading model: {e}")
    scorer = None

def evaluate_and_record_shadow_decision(coin, s6_allocation, s6_decision):
    """
    Non-blocking evaluation of S7 rules.
    coin: The Signal object
    s6_allocation: the allocation S6 chose (e.g. 2.0)
    s6_decision: the decision string (e.g. 'BUY', 'SKIP')
    """
    if scorer is None:
        return
        
    def _run():
        try:
            # We need to construct the 'row' for the scorer based on the current db state
            # This replicates T0 data collection
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            
            t0_timestamp = time.time()
            
            # Get latest intelligence
            cursor.execute('''
                SELECT buy_sell_ratio, mc_velocity, volume_velocity, sentiment_strength, collected_at 
                FROM intelligence 
                WHERE signal_id = ? AND collected_at <= ?
                ORDER BY collected_at DESC LIMIT 1
            ''', (coin.signal_id, t0_timestamp))
            intel_row = cursor.fetchone()
            
            # Get latest snapshot
            cursor.execute('''
                SELECT liquidity, volume, timestamp 
                FROM snapshots 
                WHERE signal_id = ? AND CAST(timestamp AS REAL) <= ?
                ORDER BY CAST(timestamp AS REAL) DESC LIMIT 1
            ''', (coin.signal_id, t0_timestamp))
            snap_row = cursor.fetchone()
            
            conn.close()
            
            row = {}
            intel_source_timestamp = None
            if intel_row:
                row['buy_sell_ratio'] = intel_row[0]
                row['mc_velocity'] = intel_row[1]
                row['volume_velocity'] = intel_row[2]
                row['sentiment_strength'] = intel_row[3]
                intel_source_timestamp = intel_row[4]
                
            snapshot_source_timestamp = None
            if snap_row:
                row['t0_liquidity'] = snap_row[0]
                row['t0_volume'] = snap_row[1]
                snapshot_source_timestamp = snap_row[2]
                
            # Derived fields
            signal_mc = coin.signal_market_cap if coin.signal_market_cap else 1.0
            row['vol_to_mc'] = row.get('t0_volume', 1.0) / signal_mc
            
            # Get decision
            opp, risk, net, alloc, est_dict_old, feature_snapshot_json, f_version = scorer.get_allocation_decision(row)
            
            # Generate Execution Intelligence Snapshot (P2A-1)
            exec_snapshot = ExecutionIntelligence.calculate_snapshot(coin, s6_allocation)
            execution_snapshot_json = json.dumps(exec_snapshot, sort_keys=True)
            
            est_entry = exec_snapshot["ESTIMATED"]["estimated_entry_impact"]
            est_exit = exec_snapshot["ESTIMATED"]["estimated_exit_impact"]
            est_rt = exec_snapshot["ESTIMATED"]["estimated_round_trip_cost"]
            
            # Save to DB
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO s7_shadow_decisions 
                (signal_id, symbol, decision_timestamp, model_version, 
                 opportunity_score, execution_risk_score, net_score, shadow_allocation, 
                 estimated_entry_impact, estimated_exit_impact, estimated_round_trip_cost, 
                 s6_decision, s6_allocation, feature_version, feature_snapshot_json, execution_snapshot_json, 
                 t0_timestamp, intel_source_timestamp, snapshot_source_timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                coin.signal_id,
                coin.symbol,
                t0_timestamp,
                MODEL_VERSION,
                opp,
                risk,
                net,
                alloc,
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
                time.time()
            ))
            
            if cursor.rowcount == 0:
                print(f"[S7 SHADOW] Ignored duplicate evaluation for {coin.symbol} (signal_id: {coin.signal_id})")
            else:
                print(f"[S7 SHADOW] Recorded Decision for {coin.symbol}: Alloc ${alloc} (S6: ${s6_allocation})")
                
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"[S7 SHADOW] Exception during async evaluation: {e}")

    # Fire and forget
    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
