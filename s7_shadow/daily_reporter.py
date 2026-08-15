import os
import sys
import sqlite3
import pandas as pd
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE

MIN_FORWARD_DECISIONS = 50
MIN_RESOLVED_OUTCOMES = 20

def generate_report():
    conn = sqlite3.connect(DATABASE)
    
    query = """
    SELECT 
        d.*,
        o.max_return as actual_max_return,
        t.pnl_percent as s6_actual_pnl
    FROM s7_shadow_decisions d
    LEFT JOIN outcomes o ON d.signal_id = o.signal_id
    LEFT JOIN trades t ON d.signal_id = t.signal_id
    ORDER BY d.decision_timestamp ASC
    """
    
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading decisions: {e}")
        df = pd.DataFrame()
        
    conn.close()
    
    if len(df) == 0:
        print("No S7 shadow decisions yet.")
        num_decisions = 0
        num_resolved = 0
        resolved_df = pd.DataFrame()
    else:
        resolved_df = df[df['s6_actual_pnl'].notnull()].copy()
        num_decisions = len(df)
        num_resolved = len(resolved_df)
    
    # Initialize defaults
    s7_total_net_pnl = 0.0
    s6_total_pnl = 0.0
    incremental_total = 0.0
    profit_factor = 0.0
    incremental_ex_top1 = 0.0
    incremental_ex_top3 = 0.0
    friction_results = {"0.0%": 0.0, "0.25%": 0.0, "0.5%": 0.0, "1.0%": 0.0, "2.0%": 0.0}
    has_positive_incremental = False
    has_pf = False
    has_unconcentrated_edge = False
    
    if num_resolved == 0:
        print("No resolved outcomes yet.")
    else:
        resolved_df['gross_counterfactual_pnl'] = (resolved_df['s6_actual_pnl'] / 100.0) * resolved_df['shadow_allocation']
        resolved_df['estimated_execution_cost'] = resolved_df['estimated_round_trip_cost'] * resolved_df['shadow_allocation']
        resolved_df['net_counterfactual_pnl'] = resolved_df['gross_counterfactual_pnl'] - resolved_df['estimated_execution_cost']
        
        resolved_df['s6_pnl_usd'] = (resolved_df['s6_actual_pnl'] / 100.0) * resolved_df['s6_allocation']
        resolved_df['incremental_pnl'] = resolved_df['net_counterfactual_pnl'] - resolved_df['s6_pnl_usd']
        
        s7_total_net_pnl = resolved_df['net_counterfactual_pnl'].sum()
        s6_total_pnl = resolved_df['s6_pnl_usd'].sum()
        incremental_total = s7_total_net_pnl - s6_total_pnl
        
        s7_winners = resolved_df[resolved_df['net_counterfactual_pnl'] > 0]
        s7_losers = resolved_df[resolved_df['net_counterfactual_pnl'] <= 0]
        
        gross_profit = s7_winners['net_counterfactual_pnl'].sum()
        gross_loss = abs(s7_losers['net_counterfactual_pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
        
        top_winners = resolved_df.nlargest(3, 'net_counterfactual_pnl')
        
        resolved_df_ex_top1 = resolved_df.drop(top_winners.index[:1]) if len(top_winners) >= 1 else resolved_df
        incremental_ex_top1 = resolved_df_ex_top1['net_counterfactual_pnl'].sum() - resolved_df_ex_top1['s6_pnl_usd'].sum()
        
        resolved_df_ex_top3 = resolved_df.drop(top_winners.index) if len(top_winners) >= 3 else resolved_df
        incremental_ex_top3 = resolved_df_ex_top3['net_counterfactual_pnl'].sum() - resolved_df_ex_top3['s6_pnl_usd'].sum()
        
        friction_results = {}
        for friction_pct in [0.0, 0.25, 0.5, 1.0, 2.0]:
            stress_cost = (friction_pct / 100.0) * 2 * resolved_df['shadow_allocation']
            stressed_net = resolved_df['net_counterfactual_pnl'] - stress_cost
            friction_results[f"{friction_pct}%"] = stressed_net.sum() - s6_total_pnl
            
        has_positive_incremental = incremental_total > 0
        has_pf = profit_factor > 1.0
        has_unconcentrated_edge = incremental_ex_top1 > 0 and incremental_ex_top3 > 0
    
    if num_decisions < MIN_FORWARD_DECISIONS or num_resolved < MIN_RESOLVED_OUTCOMES:
        verdict = "PROMISING — NEED MORE FORWARD DATA" if (has_positive_incremental or num_resolved == 0) else "NO DEPLOYMENT"
    elif has_positive_incremental and has_pf and has_unconcentrated_edge:
        verdict = "ROBUST INCREMENTAL EDGE"
    else:
        verdict = "NO DEPLOYMENT"
        
    model_version = resolved_df['model_version'].iloc[-1] if num_resolved > 0 else "UNKNOWN"
    feature_version = resolved_df['feature_version'].iloc[-1] if num_resolved > 0 else "UNKNOWN"

    report = f"""# S7 Shadow Engine Daily Report
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Model Version: {model_version}
Feature Version: {feature_version}

## Forward Sample
- **Forward Decisions Logged**: {num_decisions} (Min required: {MIN_FORWARD_DECISIONS})
- **Resolved Outcomes**: {num_resolved} (Min required: {MIN_RESOLVED_OUTCOMES})

## Performance Summary
- **S7 Net Counterfactual P&L**: ${s7_total_net_pnl:.2f}
- **S6 Actual P&L**: ${s6_total_pnl:.2f}
- **Incremental P&L**: ${incremental_total:.2f}
- **S7 Profit Factor**: {profit_factor:.2f}

## Concentration Test
- Incremental P&L (excl. top 1 S7 winner): ${incremental_ex_top1:.2f}
- Incremental P&L (excl. top 3 S7 winners): ${incremental_ex_top3:.2f}

## Friction Sensitivity (Incremental P&L after extra stress)
"""
    for k, v in friction_results.items():
        report += f"- {k} per-leg stress: ${v:.2f}\n"
        
    if num_decisions > 0:
        report += f"\n## Allocation Distribution\n{df['shadow_allocation'].value_counts().to_string()}\n"
        
    report += f"\n**FINAL VERDICT**: {verdict}\n"

    report_path = os.path.join(os.path.dirname(__file__), "s7_shadow_daily.md")
    with open(report_path, "w") as f:
        f.write(report)
        
    csv_path = os.path.join(os.path.dirname(__file__), "s7_shadow_trades.csv")
    df.to_csv(csv_path, index=False)
    
    print(f"Generated daily report at {report_path}")
    print(f"Verdict: {verdict}")

if __name__ == "__main__":
    generate_report()
