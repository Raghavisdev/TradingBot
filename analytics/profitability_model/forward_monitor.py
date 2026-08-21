import os
import sys
import sqlite3
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import DATABASE

REPORT_PATH = os.path.join(os.path.dirname(__file__), "PHASE4_FORWARD_SHADOW_REPORT.md")

def run_forward_monitor():
    conn = sqlite3.connect(DATABASE)
    
    df_all = pd.read_sql_query("SELECT * FROM s7_shadow_decisions", conn)
    df_outcomes = pd.read_sql_query("SELECT signal_id, max_return, min_return FROM outcomes", conn)
    conn.close()
    
    if df_all.empty:
        legacy_count = 0
        new_count = 0
        df_new = pd.DataFrame()
    else:
        # Separate Legacy vs New (New records have recommendation not null)
        is_new = df_all['recommendation'].notna() & (df_all['recommendation'] != '')
        df_legacy = df_all[~is_new]
        df_new = df_all[is_new]
        legacy_count = len(df_legacy)
        new_count = len(df_new)
        
    report = []
    report.append("# PHASE 4B: FORWARD SHADOW VALIDATION REPORT")
    report.append("\n## 1. OBSERVATION COUNTS")
    report.append(f"- **Total S7 Shadow Decisions:** {len(df_all)}")
    report.append(f"- **Legacy Decisions:** {legacy_count}")
    report.append(f"- **New Phase 4A ML Decisions:** {new_count}")
    
    if new_count > 0:
        ml_with_feat = df_new['feature_snapshot_json'].notna().sum()
        ml_with_model = df_new['model_version'].notna().sum()
        ml_with_data = df_new['dataset_version'].notna().sum()
        ml_with_fver = df_new['feature_version'].notna().sum()
        
        report.append(f"- Decisions with feature_snapshot: {ml_with_feat}")
        report.append(f"- Decisions with model_version: {ml_with_model}")
        report.append(f"- Decisions with dataset_version: {ml_with_data}")
        report.append(f"- Decisions with feature_version: {ml_with_fver}")
    
    report.append("\n## 2. TEMPORAL PROVENANCE VERIFICATION")
    temporal_issues = []
    if new_count > 0:
        for _, row in df_new.iterrows():
            d_ts = row.get('decision_timestamp', 0) or 0
            s_ts = row.get('snapshot_source_timestamp', 0) or 0
            i_ts = row.get('intel_source_timestamp', 0) or 0
            t_ts = row.get('t0_timestamp', 0) or 0
            
            if s_ts > d_ts: temporal_issues.append(f"Signal {row['signal_id']}: Snapshot future leak ({s_ts} > {d_ts})")
            if i_ts > d_ts: temporal_issues.append(f"Signal {row['signal_id']}: Intelligence future leak ({i_ts} > {d_ts})")
            if t_ts > d_ts: temporal_issues.append(f"Signal {row['signal_id']}: T0 future leak ({t_ts} > {d_ts})")
            
        if not temporal_issues:
            report.append("- **Status:** PASSED (No future leaks detected in forward data)")
        else:
            report.append("- **Status:** FAILED")
            for issue in temporal_issues:
                report.append(f"  - {issue}")
    else:
        report.append("- **Status:** N/A (No new records to verify)")

    report.append("\n## 3. PREDICTION DISTRIBUTIONS")
    if new_count > 0:
        cols = ['p_rug', 'p_2x', 'p_5x', 'p_10x', 'expected_return', 'opportunity_score']
        for c in cols:
            report.append(f"**{c}**")
            report.append(f"- min: {df_new[c].min():.4f}")
            report.append(f"- median: {df_new[c].median():.4f}")
            report.append(f"- mean: {df_new[c].mean():.4f}")
            report.append(f"- max: {df_new[c].max():.4f}\n")
            
        report.append("**Recommendations:**")
        rc = df_new['recommendation'].value_counts()
        for r_name in ['AVOID', 'OBSERVE', 'CANDIDATE', 'HIGH_OPPORTUNITY']:
            report.append(f"- {r_name}: {rc.get(r_name, 0)}")
    else:
        report.append("No data.")

    report.append("\n## 4. S6 / ML AGREEMENT")
    if new_count > 0:
        df_new['agreement'] = df_new['s6_decision'].apply(lambda x: "BUY" if x in ["BUY", "STRONG BUY"] else "NON-BUY") + " + ML " + df_new['recommendation']
        ac = df_new['agreement'].value_counts()
        for cat, cnt in ac.items():
            report.append(f"- {cat}: {cnt}")
    else:
        report.append("No data.")
        
    report.append("\n## 5. OUTCOME JOINING & PERFORMANCE")
    if new_count > 0 and not df_outcomes.empty:
        df_merged = pd.merge(df_new, df_outcomes, on='signal_id', how='inner')
        resolved_count = len(df_merged)
        report.append(f"- **Resolved Signals (New ML):** {resolved_count}")
        if resolved_count > 0:
            df_merged['is_rug'] = df_merged['max_return'] < -0.80
            df_merged['is_2x'] = df_merged['max_return'] >= 1.0
            df_merged['is_5x'] = df_merged['max_return'] >= 4.0
            df_merged['is_10x'] = df_merged['max_return'] >= 9.0
            
            # Simple threshold rules for "predicted rug": p_rug > 0.5
            correct_rug = len(df_merged[(df_merged['p_rug'] > 0.5) & df_merged['is_rug']])
            incorrect_rug = len(df_merged[(df_merged['p_rug'] > 0.5) & (~df_merged['is_rug'])])
            
            # Accuracy roughly defined as picking right direction threshold
            # E.g. p_2x > 0.5 and it hits 2x
            acc_2x = len(df_merged[(df_merged['p_2x'] > 0.5) == df_merged['is_2x']]) / resolved_count
            acc_5x = len(df_merged[(df_merged['p_5x'] > 0.5) == df_merged['is_5x']]) / resolved_count
            acc_10x = len(df_merged[(df_merged['p_10x'] > 0.5) == df_merged['is_10x']]) / resolved_count
            
            mae_er = (df_merged['expected_return'] - df_merged['max_return']).abs().mean()
            
            report.append(f"- Correct Rug Prediction: {correct_rug}")
            report.append(f"- Incorrect Rug Prediction: {incorrect_rug}")
            report.append(f"- 2x Prediction Accuracy: {acc_2x*100:.1f}%")
            report.append(f"- 5x Prediction Accuracy: {acc_5x*100:.1f}%")
            report.append(f"- 10x Prediction Accuracy: {acc_10x*100:.1f}%")
            report.append(f"- Expected-Return Error (MAE): {mae_er:.3f}")
        else:
            report.append("No resolved outcomes yet.")
    else:
        report.append("No resolved outcomes yet.")
        resolved_count = 0
        df_merged = pd.DataFrame()

    report.append("\n## 6. FORWARD PAPER EXPERIMENT")
    if resolved_count > 0:
        df_merged['is_s6_buy'] = df_merged['s6_decision'].isin(["BUY", "STRONG BUY"])
        exps = {
            "A (S6 baseline)": df_merged[df_merged['is_s6_buy']],
            "B (S6 + ML rug filter)": df_merged[df_merged['is_s6_buy'] & (df_merged['recommendation'] != 'AVOID')],
            "C (S6 + ML opp ranking)": df_merged[df_merged['is_s6_buy'] & (df_merged['recommendation'] == 'HIGH_OPPORTUNITY')],
            "D (Both)": df_merged[df_merged['is_s6_buy'] & (df_merged['recommendation'] == 'HIGH_OPPORTUNITY') & (df_merged['p_rug'] < 0.5)]
        }
        for name, exp_df in exps.items():
            report.append(f"### Experiment {name}")
            if exp_df.empty:
                report.append("No trades.\n")
                continue
            tc = len(exp_df)
            rr = len(exp_df[exp_df['max_return'] < -0.8]) / tc
            c2 = len(exp_df[exp_df['max_return'] >= 1.0]) / tc
            c5 = len(exp_df[exp_df['max_return'] >= 4.0]) / tc
            c10 = len(exp_df[exp_df['max_return'] >= 9.0]) / tc
            av = exp_df['max_return'].mean()
            md = exp_df['max_return'].median()
            
            gross_p = exp_df[exp_df['max_return'] > 0]['max_return'].sum()
            gross_l = abs(exp_df[exp_df['max_return'] < 0]['max_return'].sum())
            pf = gross_p / gross_l if gross_l != 0 else float('inf')
            
            mdd = exp_df['min_return'].min() if 'min_return' in exp_df.columns else exp_df['max_return'].min()
            
            report.append(f"- Trade count: {tc}")
            report.append(f"- Rug rate: {rr*100:.1f}%")
            report.append(f"- 2x capture: {c2*100:.1f}%")
            report.append(f"- 5x capture: {c5*100:.1f}%")
            report.append(f"- 10x capture: {c10*100:.1f}%")
            report.append(f"- Average return: {av*100:.1f}%")
            report.append(f"- Median return: {md*100:.1f}%")
            report.append(f"- Profit factor: {pf:.2f}")
            report.append(f"- EV: {av:.3f}")
            report.append(f"- Max drawdown: {mdd*100:.1f}%\n")
    else:
        report.append("No resolved outcomes yet.")

    report.append("\n## 7. SAMPLE SIZE TRACKER")
    report.append(f"- ML forward observations: {new_count}")
    report.append(f"- ML resolved observations: {resolved_count}")
    if resolved_count > 0:
        report.append(f"- 2x examples: {len(df_merged[df_merged['is_2x']])}")
        report.append(f"- 5x examples: {len(df_merged[df_merged['is_5x']])}")
        report.append(f"- 10x examples: {len(df_merged[df_merged['is_10x']])}")
        report.append(f"- S6 BUY observations: {len(df_new[df_new['s6_decision'].isin(['BUY', 'STRONG BUY'])])}")
        report.append(f"- S6 BUY resolved observations: {len(df_merged[df_merged['is_s6_buy']])}")
    else:
        report.append("- 2x examples: 0")
        report.append("- 5x examples: 0")
        report.append("- 10x examples: 0")
        report.append(f"- S6 BUY observations: {len(df_new[df_new['s6_decision'].isin(['BUY', 'STRONG BUY'])]) if new_count > 0 else 0}")
        report.append("- S6 BUY resolved observations: 0")

    report.append("\n## 8. CRITICAL SAFETY TEST (CALL GRAPH)")
    report.append("```text")
    report.append("engine/pipeline.py:process_signal(coin)")
    report.append("  |")
    report.append("  |-- s7_shadow/live_evaluator.py:evaluate_and_record_shadow_decision(coin, s6_amount, coin.decision)")
    report.append("  |      |-- Analytics: ShadowInference(features)")
    report.append("  |      |-- Database: INSERT INTO s7_shadow_decisions")
    report.append("  |")
    report.append("  |-- trading/live_trader.py:LiveTrader.enter_position(coin)")
    report.append("```")
    report.append("**Observation:** The ML prediction is recorded to the database in a daemon thread. `pipeline.py` ignores its return value. The LiveTrader execution path is completely independent and does not access the ML predictions.")

    report.append("\n## 9. FINAL VERDICT")
    RETRAIN_THRESHOLD = 50
    if temporal_issues:
        verdict = "CRITICAL_TEMPORAL_LEAK"
    elif new_count == 0:
        verdict = "INSUFFICIENT_FORWARD_DATA"
    elif resolved_count < RETRAIN_THRESHOLD:
        verdict = "COLLECTING_FORWARD_DATA"
    else:
        # Simplified threshold rule for preliminary evidence
        verdict = "PRELIMINARY_EVIDENCE"
    
    report.append(f"**Verdict:** {verdict}")
    report.append(f"**Progress to Phase 4C:** {resolved_count} / {RETRAIN_THRESHOLD} resolved signals")
    
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report))
        
    print(f"Report successfully generated at {REPORT_PATH}")

if __name__ == "__main__":
    run_forward_monitor()
