import os
import sys
import sqlite3
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE
from s7_experiment.phase_d_e_shadow_score import ShadowScorer
from s7_experiment.phase_c_liquidity_model import MODEL_VERSION

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
            
            # Get latest intelligence
            cursor.execute('''
                SELECT buy_sell_ratio, mc_velocity, volume_velocity, sentiment_strength 
                FROM intelligence 
                WHERE signal_id = ? 
                ORDER BY id DESC LIMIT 1
            ''', (coin.signal_id,))
            intel_row = cursor.fetchone()
            
            # Get latest snapshot
            cursor.execute('''
                SELECT liquidity, volume 
                FROM snapshots 
                WHERE signal_id = ? 
                ORDER BY id ASC LIMIT 1
            ''', (coin.signal_id,))
            snap_row = cursor.fetchone()
            
            conn.close()
            
            row = {}
            if intel_row:
                row['buy_sell_ratio'] = intel_row[0]
                row['mc_velocity'] = intel_row[1]
                row['volume_velocity'] = intel_row[2]
                row['sentiment_strength'] = intel_row[3]
                
            if snap_row:
                row['t0_liquidity'] = snap_row[0]
                row['t0_volume'] = snap_row[1]
                
            # Derived fields
            signal_mc = coin.signal_market_cap if coin.signal_market_cap else 1.0
            row['vol_to_mc'] = row.get('t0_volume', 1.0) / signal_mc
            
            # Get decision
            opp, risk, net, alloc, est_dict, feature_snapshot_json, f_version = scorer.get_allocation_decision(row)
            
            # Save to DB
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO s7_shadow_decisions 
                (signal_id, symbol, decision_timestamp, model_version, 
                 opportunity_score, execution_risk_score, net_score, shadow_allocation, 
                 estimated_entry_impact, estimated_exit_impact, estimated_round_trip_cost, 
                 s6_decision, s6_allocation, feature_version, feature_snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                coin.signal_id,
                coin.symbol,
                time.time(),
                MODEL_VERSION,
                opp,
                risk,
                net,
                alloc,
                est_dict.get('estimated_entry_impact'),
                est_dict.get('estimated_exit_impact'),
                est_dict.get('estimated_round_trip_cost'),
                s6_decision,
                s6_allocation,
                f_version,
                feature_snapshot_json,
                time.time()
            ))
            conn.commit()
            conn.close()
            
            print(f"[S7 SHADOW] Recorded Decision for {coin.symbol}: Alloc ${alloc} (S6: ${s6_allocation})")
            
        except Exception as e:
            print(f"[S7 SHADOW] Exception during async evaluation: {e}")

    # Fire and forget
    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
