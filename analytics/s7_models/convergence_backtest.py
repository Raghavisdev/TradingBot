import os
import pandas as pd
import numpy as np
import xgboost as xgb

def load_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(base_dir, 's7_dataset')
    
    train_df = pd.read_csv(os.path.join(dataset_dir, 's7_train.csv'))
    val_df = pd.read_csv(os.path.join(dataset_dir, 's7_validation.csv'))
    test_df = pd.read_csv(os.path.join(dataset_dir, 's7_test.csv'))
    
    return train_df, val_df, test_df

def load_models():
    models_dir = os.path.dirname(__file__)
    targets = ['Y_2x', 'Y_5x', 'Y_10x', 'Y_rug']
    models = {}
    
    for target in targets:
        model_path = os.path.join(models_dir, f"model_{target}.ubj")
        if os.path.exists(model_path):
            m = xgb.XGBClassifier()
            m.load_model(model_path)
            models[target] = m
            
    return models

def predict_df(df, models):
    feature_cols = [c for c in df.columns if c.startswith('X_')]
    X = df[feature_cols].copy()
    for c in feature_cols:
        X[c] = pd.to_numeric(X[c], errors='coerce')
        
    for target, model in models.items():
        df[f'P_{target}'] = model.predict_proba(X)[:, 1]
    
    # Fill missing predictions with 0 for safety
    for target in ['Y_2x', 'Y_5x', 'Y_10x', 'Y_rug']:
        if f'P_{target}' not in df.columns:
            df[f'P_{target}'] = 0.0
            
    return df

def find_validation_thresholds(val_df):
    # Using simple heuristic on validation set
    # In practice, this would optimize for F1 or precision
    t_opp = 0.5
    t_rug = 0.5
    
    if len(val_df) > 0:
        if 'P_Y_2x' in val_df.columns:
            t_opp = np.percentile(val_df['P_Y_2x'].dropna(), 80) if len(val_df['P_Y_2x'].dropna()) > 0 else 0.5
        if 'P_Y_rug' in val_df.columns:
            t_rug = np.percentile(val_df['P_Y_rug'].dropna(), 20) if len(val_df['P_Y_rug'].dropna()) > 0 else 0.5
            
    # Hard bounds
    t_opp = max(0.1, min(0.9, t_opp))
    t_rug = max(0.1, min(0.9, t_rug))
    return t_opp, t_rug

def run_backtest():
    train_df, val_df, test_df = load_data()
    models = load_models()
    
    val_df = predict_df(val_df, models)
    test_df = predict_df(test_df, models)
    
    t_opp, t_rug = find_validation_thresholds(val_df)
    
    # ==========================================
    # EVALUATION
    # ==========================================
    
    # S6 Baseline
    s6_signals = len(test_df)
    s6_buy = len(test_df[test_df['X_s6_decision'].isin(['BUY', 'STRONG_BUY'])])
    s6_skip = len(test_df[test_df['X_s6_decision'] == 'SKIP'])
    s6_watch = len(test_df[test_df['X_s6_decision'] == 'WATCH'])
    
    s6_buy_df = test_df[test_df['X_s6_decision'].isin(['BUY', 'STRONG_BUY'])]
    s6_winners = len(s6_buy_df[s6_buy_df['Y_2x'] == 1])
    s6_2x = s6_winners
    s6_5x = len(s6_buy_df[s6_buy_df['Y_5x'] == 1])
    s6_10x = len(s6_buy_df[s6_buy_df['Y_10x'] == 1])
    s6_rugs = len(s6_buy_df[s6_buy_df['Y_rug'] == 1])
    
    # System B - S7 Rescue Only
    skip_watch_df = test_df[~test_df['X_s6_decision'].isin(['BUY', 'STRONG_BUY'])]
    
    # Rescue logic: S7 identifies opportunity and low rug risk
    rescue_mask = (skip_watch_df['P_Y_2x'] >= t_opp) & (skip_watch_df['P_Y_rug'] <= t_rug)
    s7_rescues_df = skip_watch_df[rescue_mask]
    
    s7_candidates = len(skip_watch_df)
    s7_accepted = len(s7_rescues_df)
    s7_2x = len(s7_rescues_df[s7_rescues_df['Y_2x'] == 1])
    s7_5x = len(s7_rescues_df[s7_rescues_df['Y_5x'] == 1])
    s7_10x = len(s7_rescues_df[s7_rescues_df['Y_10x'] == 1])
    s7_rugs = len(s7_rescues_df[s7_rescues_df['Y_rug'] == 1])
    
    rescue_rate = (s7_accepted / s7_candidates * 100) if s7_candidates > 0 else 0
    rescue_precision = (s7_2x / s7_accepted * 100) if s7_accepted > 0 else 0
    
    # System C - S6 + S7
    sys_c_trades = s6_buy + s7_accepted
    sys_c_winners = s6_winners + s7_2x
    sys_c_rugs = s6_rugs + s7_rugs
    
    # P&L Calculation (Opportunity Return proxy since exact paper_lab execution is not linked)
    # We use a theoretical fixed size of $100 per trade for Opportunity-Return Analysis
    TRADE_SIZE = 100.0
    
    def calc_opp_pnl(df):
        pnl = 0.0
        for _, r in df.iterrows():
            if r['Y_rug'] == 1:
                pnl -= TRADE_SIZE  # total loss
            else:
                ret = float(r.get('label_max_return', 0.0))
                if pd.isna(ret): ret = 0.0
                # Using 50% of max_return as a proxy for trailing stop capture
                capture = min(ret * 0.5, ret)
                pnl += TRADE_SIZE * (capture / 100.0)
        return pnl
        
    s6_pnl = calc_opp_pnl(s6_buy_df)
    s7_pnl = calc_opp_pnl(s7_rescues_df)
    sys_c_pnl = s6_pnl + s7_pnl
    
    incremental_pnl = sys_c_pnl - s6_pnl
    incremental_capital = s7_accepted * TRADE_SIZE
    ret_per_capital = (incremental_pnl / incremental_capital) if incremental_capital > 0 else 0
    
    # DECISION GATE
    decision = "FAIL"
    decision_reason = "No demonstrated economic improvement."
    
    if incremental_pnl > 0 and s7_accepted > 0:
        if len(test_df) < 50 or s7_accepted < 5:
            decision = "CONDITIONAL"
            decision_reason = "Promising rescue signal exists but sample size/statistical confidence is insufficient."
        elif s7_rugs > (s7_accepted * 0.2):
            decision = "FAIL"
            decision_reason = "Incremental P&L is positive, but rescue rug rate exceeds acceptable limits (>20%)."
        else:
            decision = "PASS"
            decision_reason = "S7 demonstrates measurable positive economic lift without unacceptable additional risk."
    
    # ==========================================
    # REPORT GENERATION
    # ==========================================
    
    report = []
    report.append("==================================================")
    report.append("S7 V2 CONVERGENCE REPORT")
    report.append("==================================================")
    report.append("")
    report.append("DATASET")
    report.append(f"- train rows: {len(train_df)}")
    report.append(f"- validation rows: {len(val_df)}")
    report.append(f"- final test rows: {len(test_df)}")
    
    # Simple date range if available
    if len(test_df) > 0 and 't0_timestamp' in test_df.columns:
        min_ts = pd.to_datetime(test_df['t0_timestamp'].min(), unit='s')
        max_ts = pd.to_datetime(test_df['t0_timestamp'].max(), unit='s')
        report.append(f"- final test date range: {min_ts} to {max_ts}")
    report.append("")
    report.append("S6 BASELINE")
    report.append(f"- signals: {s6_signals} (BUY:{s6_buy} SKIP:{s6_skip} WATCH:{s6_watch})")
    report.append(f"- winners: {s6_winners}")
    report.append(f"- 2x capture: {s6_2x}")
    report.append(f"- 5x capture: {s6_5x}")
    report.append(f"- 10x capture: {s6_10x}")
    report.append(f"- rugs: {s6_rugs}")
    report.append(f"- P&L (Opportunity-Return proxy): ${s6_pnl:.2f}")
    report.append("  * Exact historical execution/slippage is unavailable in this dataset snapshot. Using opportunity-return proxy.")
    report.append("")
    report.append("S7 RESCUE")
    report.append(f"- thresholds: opp>={t_opp:.2f}, rug<={t_rug:.2f} (from validation)")
    report.append(f"- candidates: {s7_candidates}")
    report.append(f"- accepted: {s7_accepted}")
    report.append(f"- 2x: {s7_2x}")
    report.append(f"- 5x: {s7_5x}")
    report.append(f"- 10x: {s7_10x}")
    report.append(f"- rugs: {s7_rugs}")
    report.append(f"- rescue precision: {rescue_precision:.1f}%")
    report.append(f"- P&L (Opportunity-Return proxy): ${s7_pnl:.2f}")
    report.append(f"- capital required: ${incremental_capital:.2f}")
    report.append("")
    report.append("S6 + S7")
    report.append(f"- total opportunities executed: {sys_c_trades}")
    report.append(f"- incremental winners: {s7_2x}")
    report.append(f"- incremental rugs: {s7_rugs}")
    report.append(f"- incremental P&L: ${incremental_pnl:.2f}")
    report.append(f"- return per unit capital: {ret_per_capital:.2%}")
    report.append("")
    report.append("==================================================")
    report.append("DECISION GATE")
    report.append("==================================================")
    report.append(decision)
    report.append(decision_reason)
    
    report_text = "\n".join(report)
    print(report_text)
    
    out_path = os.path.join(os.path.dirname(__file__), "S7_V2_CONVERGENCE_REPORT.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        
    print(f"\nReport written to: {out_path}")

if __name__ == "__main__":
    run_backtest()
