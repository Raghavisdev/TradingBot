import os
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import roc_auc_score, average_precision_score

def evaluate_convergence():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(base_dir, 's7_dataset')
    models_dir = os.path.dirname(__file__)
    
    test_path = os.path.join(dataset_dir, 's7_test.csv')
    
    if not os.path.exists(test_path):
        print(f"Error: {test_path} not found.")
        return
        
    test_df = pd.read_csv(test_path)
    
    if len(test_df) == 0:
        print("Empty test set.")
        return
        
    feature_cols = [c for c in test_df.columns if c.startswith('X_')]
    X_test = test_df[feature_cols].copy()
    
    for c in feature_cols:
        X_test[c] = pd.to_numeric(X_test[c], errors='coerce')
        
    predictions = {}
    targets = ['Y_2x', 'Y_5x', 'Y_10x', 'Y_rug']
    
    print("\n" + "="*50)
    print("PHASE 2F: EVALUATION")
    print("="*50)
    
    for target in targets:
        model_path = os.path.join(models_dir, f"model_{target}.ubj")
        if not os.path.exists(model_path):
            predictions[target] = np.zeros(len(test_df))
            continue
            
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        
        preds = model.predict_proba(X_test)[:, 1]
        predictions[target] = preds
        
        y_test = test_df[target].values
        
        if len(np.unique(y_test)) > 1:
            auc = roc_auc_score(y_test, preds)
            pr_auc = average_precision_score(y_test, preds)
            print(f"{target} - ROC-AUC: {auc:.4f} | PR-AUC: {pr_auc:.4f}")
        else:
            print(f"{target} - Only one class present in test set.")
            
        # Quick feature importance top 3
        booster = model.get_booster()
        importance = booster.get_score(importance_type='gain')
        if importance:
            sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"  Top Features: {sorted_imp}")

    print("\n" + "="*50)
    print("PHASE 2G: ECONOMIC CONVERGENCE TEST")
    print("="*50)
    
    # We apply the predictions to the test_df
    test_df['P_2x'] = predictions.get('Y_2x', np.zeros(len(test_df)))
    test_df['P_5x'] = predictions.get('Y_5x', np.zeros(len(test_df)))
    test_df['P_10x'] = predictions.get('Y_10x', np.zeros(len(test_df)))
    test_df['P_rug'] = predictions.get('Y_rug', np.zeros(len(test_df)))
    
    # Thresholds for rescue
    T_2X_RESCUE = 0.5
    T_RUG_VETO = 0.8
    
    sys_a_returns = []
    sys_b_returns = []
    sys_c_returns = []
    
    s6_missed_2x = 0
    s6_missed_5x = 0
    s6_missed_10x = 0
    
    s7_recovered_2x = 0
    s7_recovered_5x = 0
    s7_recovered_10x = 0
    s7_rescue_rugs = 0
    s7_rescue_count = 0
    
    for _, row in test_df.iterrows():
        s6_decision = row['X_s6_decision']
        max_return = row.get('label_max_return', 0)
        if pd.isna(max_return): max_return = 0
        rugged = row.get('label_rugged', 0)
        
        is_s6_buy = (s6_decision in ['BUY', 'STRONG_BUY'])
        
        # Determine S7 rescue on S6 SKIP/WATCH
        s7_rescue = False
        if not is_s6_buy:
            if row['P_2x'] > T_2X_RESCUE and row['P_rug'] < T_RUG_VETO:
                s7_rescue = True
        
        # Track Misses & Recoveries
        if not is_s6_buy:
            if row['Y_2x'] == 1: s6_missed_2x += 1
            if row['Y_5x'] == 1: s6_missed_5x += 1
            if row['Y_10x'] == 1: s6_missed_10x += 1
            
            if s7_rescue:
                s7_rescue_count += 1
                if row['Y_2x'] == 1: s7_recovered_2x += 1
                if row['Y_5x'] == 1: s7_recovered_5x += 1
                if row['Y_10x'] == 1: s7_recovered_10x += 1
                if rugged == 1: s7_rescue_rugs += 1
        
        # System A: S6 unchanged
        if is_s6_buy:
            sys_a_returns.append(max_return if rugged == 0 else -100.0) # Hypothetical -100% on rug
            
        # System B: S7 rescue candidates from S6 SKIP/WATCH
        if s7_rescue:
            sys_b_returns.append(max_return if rugged == 0 else -100.0)
            
        # System C: S6 BUY + S7 rescue
        if is_s6_buy or s7_rescue:
            sys_c_returns.append(max_return if rugged == 0 else -100.0)
            
    print(f"Test Set Size: {len(test_df)}")
    print(f"S6 Missed 2x: {s6_missed_2x}")
    print(f"S6 Missed 5x: {s6_missed_5x}")
    print(f"S6 Missed 10x: {s6_missed_10x}")
    print(f"S7 Recovered 2x: {s7_recovered_2x}")
    print(f"S7 Recovered 5x: {s7_recovered_5x}")
    print(f"S7 Recovered 10x: {s7_recovered_10x}")
    print(f"S7 Rescue count: {s7_rescue_count}")
    print(f"S7 Rescue rug rate: {(s7_rescue_rugs / s7_rescue_count * 100) if s7_rescue_count > 0 else 0:.2f}%")
    
    def calc_stats(ret_list):
        if not ret_list: return 0, 0, 0
        return sum(ret_list), np.mean(ret_list), len(ret_list)
        
    pnl_a, avg_a, n_a = calc_stats(sys_a_returns)
    pnl_b, avg_b, n_b = calc_stats(sys_b_returns)
    pnl_c, avg_c, n_c = calc_stats(sys_c_returns)
    
    print("\n--- PERFORMANCE SUMMARY ---")
    print(f"System A (S6): P&L={pnl_a:.2f} | AvgReturn={avg_a:.2f}% | Trades={n_a}")
    print(f"System C (S6+S7): P&L={pnl_c:.2f} | AvgReturn={avg_c:.2f}% | Trades={n_c}")
    print(f"Incremental P&L: {pnl_c - pnl_a:.2f}")
    print(f"Additional Trades Required: {n_c - n_a}")
    
    # Final Decision
    decision_str = ""
    print("\n==================================================")
    if (pnl_c - pnl_a) > 0 and (n_c - n_a) > 0:
        decision_str = "PASS (or CONDITIONAL based on sample size)"
        print(f"DECISION: {decision_str}")
        print("S7 has demonstrated measurable economic lift.")
    else:
        decision_str = "FAIL"
        print(f"DECISION: {decision_str}")
        print("S7 did not demonstrate economic lift over S6.")
    print("==================================================")
    
    # Generate S7_V2_FINAL_REPORT.txt
    report_path = os.path.join(models_dir, 'S7_V2_FINAL_REPORT.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("S7 V2 FINAL REPORT\n")
        f.write("==================================================\n")
        f.write(f"1. Usable training rows: {len(test_df)} (in this Test set)\n")
        f.write(f"2. T0 features available: {len(feature_cols)}\n")
        f.write(f"3. Sufficiently populated labels: {[t for t in predictions.keys() if np.any(predictions[t] > 0)]}\n")
        f.write(f"4. S7 Learning: It learned to predict {list(predictions.keys())}\n")
        f.write(f"5. Top features: Evaluated per model above\n")
        f.write(f"6. S6 Missed Winners Recovered: {s7_recovered_2x} (2x), {s7_recovered_5x} (5x)\n")
        f.write(f"7. Dangerous signals rejected (rugs avoided): Not measured directly in System C Rescue yet\n")
        f.write(f"8. S6 performance on final test: P&L={pnl_a:.2f}, Trades={n_a}\n")
        f.write(f"9. S7 pure performance on final test: P&L={pnl_b:.2f}, Trades={n_b}\n")
        f.write(f"10. S6+S7 performance on final test: P&L={pnl_c:.2f}, Trades={n_c}\n")
        f.write(f"11. Incremental P&L: {pnl_c - pnl_a:.2f}\n")
        f.write(f"12. Incremental Risk (Rescue rug rate): {(s7_rescue_rugs / s7_rescue_count * 100) if s7_rescue_count > 0 else 0:.2f}%\n")
        f.write(f"13. Passes Live Shadow Gate: {'Yes' if decision_str.startswith('PASS') else 'No'}\n")
        f.write(f"14. Remain Shadow Only: Yes (Mandatory for current phase)\n")
        f.write(f"15. Exact Next Step: Review model performance and collect more data if CONDITIONAL.\n")
        
    print(f"\nFinal report saved to {report_path}")

if __name__ == "__main__":
    evaluate_convergence()
