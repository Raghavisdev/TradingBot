import os
import sys
import json
import joblib
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s7_experiment.phase_c_liquidity_model import LiquiditySlippageModel, MODEL_VERSION, FEATURE_VERSION

class ShadowScorer:
    def __init__(self, model_path=None):
        self.liq_model = LiquiditySlippageModel()
        
    def evaluate_opportunity(self, row):
        # Opportunity based on buy_sell_ratio, momentum, and volume relative to MC
        bs = row.get('buy_sell_ratio', 1.0)
        vol_to_mc = row.get('vol_to_mc', 0.0)
        sentiment = row.get('sentiment_strength', 0.0)
        
        score = 50.0
        
        if bs > 2.0: score += 15
        elif bs < 0.5: score -= 15
        
        if vol_to_mc > 0.1: score += 15
        
        if sentiment > 0.5: score += 10
        elif sentiment < -0.2: score -= 10
        
        return np.clip(score, 0, 100)

    def evaluate_risk(self, row, allocation):
        liq = row.get('t0_liquidity', 1.0)
        vol = row.get('t0_volume', 1.0)
        
        est_dict = self.liq_model.estimate_cost(allocation, liq, vol)
        return est_dict['execution_risk_score'], est_dict

    def get_allocation_decision(self, row):
        opp = self.evaluate_opportunity(row)
        
        # Build feature snapshot
        # Extract only known numerical or string features, excluding complex objects
        feature_snapshot = {k: v for k, v in row.items() if isinstance(v, (int, float, str, bool)) and not pd.isna(v)}
        feature_snapshot_json = json.dumps(feature_snapshot, sort_keys=True)
        
        candidates = [7.0, 4.0, 2.0, 1.0, 0.0]
        
        for alloc in candidates:
            if alloc == 0:
                continue
                
            risk, est_dict = self.evaluate_risk(row, alloc)
            net_score = opp - risk
            
            if net_score > 60 and alloc == 7.0:
                return opp, risk, net_score, alloc, est_dict, feature_snapshot_json, FEATURE_VERSION
            if net_score > 40 and alloc == 4.0:
                return opp, risk, net_score, alloc, est_dict, feature_snapshot_json, FEATURE_VERSION
            if net_score > 20 and alloc == 2.0:
                return opp, risk, net_score, alloc, est_dict, feature_snapshot_json, FEATURE_VERSION
            if net_score > 0 and alloc == 1.0:
                return opp, risk, net_score, alloc, est_dict, feature_snapshot_json, FEATURE_VERSION
                
        # Fallback
        risk, est_dict = self.evaluate_risk(row, 1.0) 
        return opp, risk, opp - risk, 0.0, est_dict, feature_snapshot_json, FEATURE_VERSION

def run_counterfactual_test():
    dataset_path = os.path.join(os.path.dirname(__file__), "s7_dataset.csv")
    model_path = os.path.join(os.path.dirname(__file__), "liquidity_model.pkl")
    
    if not os.path.exists(dataset_path) or not os.path.exists(model_path):
        print("Missing dataset or model.")
        return

    df = pd.read_csv(dataset_path)
    scorer = ShadowScorer(model_path)
    
    results = []
    
    for _, row in df.iterrows():
        opp, risk, net, alloc, est_dict, feature_snapshot_json, f_version = scorer.get_allocation_decision(row)
        cost = est_dict['estimated_round_trip_cost']
        
        # Simulated S7 P&L
        s6_pnl_pct = row.get('s6_pnl_percent')
        
        if pd.isna(s6_pnl_pct):
            s6_pnl_pct = 0.0
            
        # S7 P&L = (S6 PNL % * allocation) - cost_dollars
        # Cost is a percentage of allocation
        s7_pnl = (s6_pnl_pct / 100.0) * alloc - (cost * alloc)
        s6_alloc = 2.0 # Assume S6 used a static $2
        s6_pnl = (s6_pnl_pct / 100.0) * s6_alloc
        
        results.append({
            'signal_id': row['signal_id'],
            'split': row['split'],
            'opportunity': opp,
            'risk': risk,
            'net_score': net,
            's7_alloc': alloc,
            's7_cost_pct': cost,
            's7_pnl_usd': s7_pnl,
            's6_pnl_usd': s6_pnl
        })
        
    df_res = pd.DataFrame(results)
    
    for split in ['train', 'val', 'test']:
        df_split = df_res[df_res['split'] == split]
        if len(df_split) == 0: continue
        
        s7_tot = df_split['s7_pnl_usd'].sum()
        s6_tot = df_split['s6_pnl_usd'].sum()
        
        print(f"\n[{split.upper()}] S7 P&L: ${s7_tot:.2f} | S6 P&L: ${s6_tot:.2f} | Incremental: ${(s7_tot - s6_tot):.2f}")
        
    df_res.to_csv(os.path.join(os.path.dirname(__file__), "s7_counterfactual.csv"), index=False)

if __name__ == "__main__":
    run_counterfactual_test()
