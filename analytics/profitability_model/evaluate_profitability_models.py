import pandas as pd
import numpy as np
from analytics.profitability_model.model_registry import ModelRegistry
from analytics.profitability_model.profitability_score import calculate_expected_value
from analytics.profitability_model.train_profitability_models import load_data

def compute_precision_at_k(df_ranked, k_percent, total_population):
    k_idx = int(len(total_population) * k_percent)
    if k_idx == 0:
        k_idx = 1
    
    top_k = df_ranked.head(k_idx)
    
    metrics = {
        'count': k_idx,
        'rug_rate': top_k['T_rugged'].mean(),
        '2x_rate': top_k['T_reached_2x'].mean(),
        '5x_rate': top_k['T_reached_5x'].mean(),
        '10x_rate': top_k['T_reached_10x'].mean(),
        'capture_2x': top_k['T_reached_2x'].sum() / max(1, total_population['T_reached_2x'].sum()),
        'capture_5x': top_k['T_reached_5x'].sum() / max(1, total_population['T_reached_5x'].sum()),
        'capture_10x': top_k['T_reached_10x'].sum() / max(1, total_population['T_reached_10x'].sum()),
    }
    
    # Expected Value empirical calculation for the bucket
    rugs = top_k['T_rugged'].sum()
    c2x = top_k['T_reached_2x'].sum()
    c5x = top_k['T_reached_5x'].sum()
    c10x = top_k['T_reached_10x'].sum()
    ev_total = (c2x * 0.5) + (c5x * 1.5) + (c10x * 3.0) - (rugs * 1.0)
    metrics['ev_per_trade'] = ev_total / k_idx
    
    return metrics

def print_bucket_metrics(name, m):
    print(f"[{name}] Trades: {m['count']} | EV/Trade: {m['ev_per_trade']:+.2f} | Rugs: {m['rug_rate']:.1%} | 2x: {m['2x_rate']:.1%} (Captures {m['capture_2x']:.1%} of all 2x) | 10x: {m['10x_rate']:.1%} (Captures {m['capture_10x']:.1%} of all 10x)")

def main():
    print("Evaluating Opportunity Ranking...")
    df = load_data()
    registry = ModelRegistry()
    
    horizon = '1m'
    
    try:
        model_rug, meta_rug = registry.get_best_model(horizon, 'T_rugged')
        model_2x, meta_2x = registry.get_best_model(horizon, 'T_reached_2x')
        model_5x, meta_5x = registry.get_best_model(horizon, 'T_reached_5x')
        model_10x, meta_10x = registry.get_best_model(horizon, 'T_reached_10x')
        model_ret, meta_ret = registry.get_best_model(horizon, 'T_log_return', metric='mae')
    except Exception as e:
        print("Models not found:", e)
        return

    features = meta_rug['features']
    
    for split in ['VALIDATION', 'TEST']:
        print(f"\\n================ {split} SET RANKING ================")
        df_split = df[df['split'] == split].copy()
        
        if len(df_split) == 0:
            continue
            
        X = df_split[features].values
        
        df_split['P_rug'] = model_rug.predict_proba(X)[:, 1]
        df_split['P_2x'] = model_2x.predict_proba(X)[:, 1]
        df_split['P_5x'] = model_5x.predict_proba(X)[:, 1]
        df_split['P_10x'] = model_10x.predict_proba(X)[:, 1]
        df_split['E_log_ret'] = model_ret.predict(X)
        
        df_split['opportunity_score'] = calculate_expected_value(
            df_split['P_rug'], df_split['P_2x'], df_split['P_5x'], df_split['P_10x'], df_split['E_log_ret']
        )
        
        # Rank signals
        df_ranked = df_split.sort_values('opportunity_score', ascending=False)
        
        print_bucket_metrics("Baseline 100%", compute_precision_at_k(df_ranked, 1.0, df_split))
        print_bucket_metrics("Top 50%", compute_precision_at_k(df_ranked, 0.50, df_split))
        print_bucket_metrics("Top 20%", compute_precision_at_k(df_ranked, 0.20, df_split))
        print_bucket_metrics("Top 10%", compute_precision_at_k(df_ranked, 0.10, df_split))
        print_bucket_metrics("Top  5%", compute_precision_at_k(df_ranked, 0.05, df_split))
        
        # Determine if ML provides verified alpha
        # If the Top 10% has a positive EV and EV_Top10 > EV_Baseline, it provides alpha.
        if split == 'TEST':
            top10 = compute_precision_at_k(df_ranked, 0.10, df_split)
            base = compute_precision_at_k(df_ranked, 1.0, df_split)
            
            print("\\nFINAL VERDICT:")
            if top10['ev_per_trade'] > 0 and top10['ev_per_trade'] > base['ev_per_trade']:
                print("ML DOES PROVIDE VERIFIED ALPHA. Winners are concentrated at the top.")
            else:
                print("ML DOES NOT YET PROVIDE VERIFIED ALPHA. Top ranked signals are not highly profitable.")

if __name__ == "__main__":
    main()
