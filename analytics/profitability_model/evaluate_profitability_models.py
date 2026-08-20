import pandas as pd
import numpy as np
from analytics.profitability_model.model_registry import ModelRegistry
from analytics.profitability_model.calibration import calibrate_probabilities
from sklearn.metrics import precision_recall_curve

def load_data():
    return pd.read_csv('analytics/profitability_model/canonical_dataset.csv')

def simulate_trades(df, accepted_mask):
    trades = df[accepted_mask]
    n_trades = len(trades)
    
    if n_trades == 0:
        return {
            'n_trades': 0, 'entry_rate': 0.0, 'win_rate': 0.0,
            'avg_return': 0.0, 'median_return': 0.0, 'total_pnl': 0.0,
            'profit_factor': 0.0, 'rug_exposure': 0.0,
            'capture_2x': 0, 'capture_5x': 0, 'capture_10x': 0,
            'expected_value_per_trade': 0.0
        }
        
    # Baseline simulation assuming equal sizing for simplicity in this offline metric
    # S6 actually uses dynamic sizing, but average return is position-agnostic.
    # The prompt allows using simplified execution assumptions or S6 logic.
    # Let's use max_return as the proxy for peak_pnl, and apply a trailing stop logic proxy:
    # A simplified offline proxy: 
    # If rugged, return = -100%
    # If 10x, return = +500% (due to ladder scaling out)
    # Actually, we have the true `T_positive_return` and we can just use mean target fields.
    
    # We will use empirical averages of the dataset's outcome metrics
    # Max return is T_max_return (we might need to reconstruct it if we only have robust log returns, 
    # but let's assume the raw max_return is available or just use T_rugged and T_reached limits).
    
    win_rate = trades['T_positive_return'].mean()
    rug_exp = trades['T_rugged'].mean()
    c2x = trades['T_reached_2x'].sum()
    c5x = trades['T_reached_5x'].sum()
    c10x = trades['T_reached_10x'].sum()
    
    # For a robust proxy of expected value, assume rugged loses 1 unit, 
    # 2x makes 0.5 units, 5x makes 2 units, 10x makes 5 units (laddering out).
    # EV = (c2x*0.5 + c5x*1.5 + c10x*3.0) - (rugs * 1.0)
    rugs = trades['T_rugged'].sum()
    ev_total = (c2x * 0.5) + (c5x * 1.5) + (c10x * 3.0) - (rugs * 1.0)
    ev_per_trade = ev_total / n_trades
    
    return {
        'n_trades': n_trades,
        'entry_rate': n_trades / len(df),
        'win_rate': win_rate,
        'rug_exposure': rug_exp,
        'capture_2x': c2x,
        'capture_5x': c5x,
        'capture_10x': c10x,
        'expected_value_per_trade': ev_per_trade
    }

def main():
    print("Evaluating Profitability Models...")
    df = load_data()
    registry = ModelRegistry()
    
    # S6 Baseline: final_score >= 65
    s6_mask_val = (df['split'] == 'VALIDATION') & (df['F_final_score'] >= 65)
    s6_mask_test = (df['split'] == 'TEST') & (df['F_final_score'] >= 65)
    
    print("\\n--- BASELINE S6 PERFORMANCE ---")
    val_baseline = simulate_trades(df[df['split'] == 'VALIDATION'], s6_mask_val[df['split'] == 'VALIDATION'])
    test_baseline = simulate_trades(df[df['split'] == 'TEST'], s6_mask_test[df['split'] == 'TEST'])
    
    print(f"VAL  | Trades: {val_baseline['n_trades']} | Win Rate: {val_baseline['win_rate']:.1%} | EV/Trade: {val_baseline['expected_value_per_trade']:.2f} | Rugs: {val_baseline['rug_exposure']:.1%}")
    print(f"TEST | Trades: {test_baseline['n_trades']} | Win Rate: {test_baseline['win_rate']:.1%} | EV/Trade: {test_baseline['expected_value_per_trade']:.2f} | Rugs: {test_baseline['rug_exposure']:.1%}")

    print("\\n--- ML FILTER PERFORMANCE (S6 + ML) ---")
    # Evaluate best model for 1m horizon targeting Rug
    model, meta = registry.get_best_model(horizon='1m', target='T_rugged', metric='pr_auc')
    
    if model is None:
        print("No models found in registry.")
        return
        
    features = meta['features']
    X_val = df[df['split'] == 'VALIDATION'][features].values
    X_test = df[df['split'] == 'TEST'][features].values
    y_val = df[df['split'] == 'VALIDATION']['T_rugged'].values
    y_test = df[df['split'] == 'TEST']['T_rugged'].values
    
    probs_val = model.predict_proba(X_val)[:, 1]
    probs_test = model.predict_proba(X_test)[:, 1]
    
    # Select threshold using validation set (e.g. max acceptable rug probability)
    # We want to REJECT trades if P_rug > threshold
    precision, recall, thresholds = precision_recall_curve(y_val, probs_val)
    # Find a threshold that keeps precision for detecting rugs high
    threshold = 0.5
    for p, r, t in zip(precision, recall, thresholds):
        if p >= 0.85: # Require 85% confidence to classify as a rug to block it
            threshold = t
            break
            
    print(f"Selected block threshold for P_rug: {threshold:.3f}")
    
    ml_accept_val = probs_val <= threshold
    ml_accept_test = probs_test <= threshold
    
    # Combined masks
    combined_val_mask = s6_mask_val[df['split'] == 'VALIDATION'] & ml_accept_val
    combined_test_mask = s6_mask_test[df['split'] == 'TEST'] & ml_accept_test
    
    val_ml = simulate_trades(df[df['split'] == 'VALIDATION'], combined_val_mask)
    test_ml = simulate_trades(df[df['split'] == 'TEST'], combined_test_mask)
    
    print(f"VAL  | Trades: {val_ml['n_trades']} | Win Rate: {val_ml['win_rate']:.1%} | EV/Trade: {val_ml['expected_value_per_trade']:.2f} | Rugs: {val_ml['rug_exposure']:.1%}")
    print(f"TEST | Trades: {test_ml['n_trades']} | Win Rate: {test_ml['win_rate']:.1%} | EV/Trade: {test_ml['expected_value_per_trade']:.2f} | Rugs: {test_ml['rug_exposure']:.1%}")
    
    # Delta
    ev_delta = test_ml['expected_value_per_trade'] - test_baseline['expected_value_per_trade']
    print(f"\\nTest Set EV Delta: {ev_delta:+.2f}")
    if ev_delta > 0:
        print("ML layer mathematically improves S6 baseline on unseen chronological test data.")
    else:
        print("ML layer FAILS to improve S6 baseline on test data. REJECT.")

if __name__ == "__main__":
    main()
