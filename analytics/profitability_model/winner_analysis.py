import pandas as pd
import numpy as np
import shap
from xgboost import XGBClassifier
import json

def generate_profile():
    print("Generating Winner Profile...")
    df = pd.read_csv('analytics/profitability_model/canonical_dataset.csv')
    
    # We only care about TRAIN and VALIDATION for profiling
    df = df[df['split'].isin(['TRAIN', 'VALIDATION'])].copy()
    
    rugged = df[df['T_rugged'] == 1]
    w2x = df[df['T_reached_2x'] == 1]
    w5x = df[df['T_reached_5x'] == 1]
    w10x = df[df['T_reached_10x'] == 1]
    
    features = [c for c in df.columns if c.startswith('F_') and not ('_snap_' in c or '_intel_' in c or '_t0_' in c) or '_t0_' in c]
    # Filter only float/int columns
    features = [f for f in features if df[f].dtype in [np.float64, np.int64]]
    
    report = []
    report.append("# Winner Profile Report\\n")
    report.append(f"Sample size: {len(df)} (Rugs: {len(rugged)}, 2x: {len(w2x)}, 5x: {len(w5x)}, 10x: {len(w10x)})\\n")
    
    report.append("## Distribution Medians (T0 Horizon)\\n")
    report.append("| Feature | Rugs | 2x | 5x | 10x |")
    report.append("|---|---|---|---|---|")
    
    key_features = ['F_t0_snap_liq', 'F_t0_snap_vol', 'F_tel_snipers', 'F_signal_mc', 'F_tel_jeeters', 'F_final_score', 'F_t0_intel_bs_ratio']
    
    for f in key_features:
        if f not in df.columns: continue
        r_med = rugged[f].median()
        m2 = w2x[f].median()
        m5 = w5x[f].median()
        m10 = w10x[f].median()
        report.append(f"| {f} | {r_med:.2f} | {m2:.2f} | {m5:.2f} | {m10:.2f} |")
        
    report.append("\\n## SHAP Interaction Analysis (T_reached_2x)\\n")
    
    # Train XGBoost on 2x
    X = df[features].fillna(0)
    y = df['T_reached_2x']
    
    if y.sum() > 0:
        xgb = XGBClassifier(random_state=42, use_label_encoder=False, eval_metric='logloss')
        xgb.fit(X, y)
        
        explainer = shap.TreeExplainer(xgb)
        shap_values = explainer.shap_values(X)
        
        # Mean absolute SHAP values for global importance
        mean_abs_shap = np.abs(shap_values).mean(axis=0)
        top_indices = np.argsort(mean_abs_shap)[::-1][:10]
        
        report.append("Top 10 Main Effects (SHAP):\\n")
        for idx in top_indices:
            report.append(f"- {features[idx]}: {mean_abs_shap[idx]:.4f}")
            
        # Due to compute limits on VPS, full interaction values might OOM, we will rely on main effects.
        # But we can calculate simple correlations for interactions manually:
        report.append("\\n## Empirical Interactions (Rank Correlation with 2x Target)\\n")
        
        if 'F_t0_snap_liq' in X.columns and 'F_tel_snipers' in X.columns:
            df['int_liq_snipers'] = df['F_t0_snap_liq'] * df['F_tel_snipers']
            corr = df['int_liq_snipers'].corr(df['T_reached_2x'], method='spearman')
            report.append(f"- Liquidity x Snipers: {corr:.3f}")
            
        if 'F_final_score' in X.columns and 'F_tel_snipers' in X.columns:
            df['int_score_snipers'] = df['F_final_score'] * df['F_tel_snipers']
            corr = df['int_score_snipers'].corr(df['T_reached_2x'], method='spearman')
            report.append(f"- Score x Snipers: {corr:.3f}")
            
    with open("WINNER_PROFILE_REPORT.md", "w") as f:
        f.write("\\n".join(report))
        
    print("Saved WINNER_PROFILE_REPORT.md")

if __name__ == "__main__":
    generate_profile()
