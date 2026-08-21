import os
import sys
import sqlite3
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE

def load_data():
    conn = sqlite3.connect(DATABASE)
    
    # Load all shadow decisions
    df_s7 = pd.read_sql_query('''
        SELECT signal_id, symbol, decision_timestamp,
               s6_decision, s6_allocation,
               recommendation, p_rug, opportunity_score,
               ml_shadow_allocation
        FROM s7_shadow_decisions
    ''', conn)
    
    # Load outcomes
    df_outcomes = pd.read_sql_query('''
        SELECT signal_id, max_return, min_return
        FROM outcomes
    ''', conn)
    
    conn.close()
    
    if df_s7.empty:
        return pd.DataFrame()
        
    df = pd.merge(df_s7, df_outcomes, on='signal_id', how='inner')
    return df

def agreement_analysis(df):
    print("============================================================")
    print("                   AGREEMENT ANALYSIS                       ")
    print("============================================================")
    
    if df.empty:
        print("No shadow decisions with outcomes found.")
        return
        
    # Categorize
    df['agreement_category'] = df['s6_decision'] + " + ML " + df['recommendation']
    counts = df['agreement_category'].value_counts()
    
    for cat, count in counts.items():
        print(f"{cat:<40}: {count} signals")
        
    print(f"\nTotal signals analyzed: {len(df)}")

def calculate_metrics(df_trades):
    if df_trades.empty:
        return {
            "entries": 0, "win_rate": 0.0, "rug_rate": 0.0, "avg_ret": 0.0,
            "med_ret": 0.0, "profit_factor": 0.0, "max_dd": 0.0, "ev": 0.0,
            "capture_2x": 0.0, "capture_5x": 0.0, "capture_10x": 0.0
        }
    
    entries = len(df_trades)
    
    # Assuming max_return < -0.80 is a rug, or status == 'RUG' (if status exists)
    rug_mask = df_trades['max_return'] < -0.80
    if 'status' in df_trades.columns:
        rug_mask = rug_mask | (df_trades['status'] == 'RUG')
        
    rugs = df_trades[rug_mask]
    wins = df_trades[df_trades['max_return'] > 0.0] # simple win definition
    
    win_rate = len(wins) / entries
    rug_rate = len(rugs) / entries
    avg_ret = df_trades['max_return'].mean()
    med_ret = df_trades['max_return'].median()
    
    capture_2x = len(df_trades[df_trades['max_return'] >= 1.0]) / entries
    capture_5x = len(df_trades[df_trades['max_return'] >= 4.0]) / entries
    capture_10x = len(df_trades[df_trades['max_return'] >= 9.0]) / entries
    
    # Rough profit factor
    gross_profit = df_trades[df_trades['max_return'] > 0]['max_return'].sum()
    gross_loss = abs(df_trades[df_trades['max_return'] < 0]['max_return'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    # Expected value (simplified based on max return - not perfectly realistic but consistent)
    ev = avg_ret
    
    # Max DD (naive estimation across portfolio)
    # A true max DD requires a time series, but we'll approximate worst trade as max DD for isolated trades
    max_dd = df_trades['min_return'].min() if 'min_return' in df_trades.columns else df_trades['max_return'].min()
    
    return {
        "entries": entries, "win_rate": win_rate, "rug_rate": rug_rate, "avg_ret": avg_ret,
        "med_ret": med_ret, "profit_factor": profit_factor, "max_dd": max_dd, "ev": ev,
        "capture_2x": capture_2x, "capture_5x": capture_5x, "capture_10x": capture_10x
    }

def paper_experiment(df):
    print("\n============================================================")
    print("                   OFFLINE PAPER EXPERIMENT                 ")
    print("============================================================")
    
    if df.empty:
        print("No shadow decisions with outcomes found.")
        return

    # Experiment A = S6 alone (S6 BUY)
    df_A = df[df['s6_decision'] == 'BUY']
    
    # Experiment B = S6 + ML rug filter (S6 BUY and ML recommendation != AVOID)
    df_B = df[(df['s6_decision'] == 'BUY') & (df['recommendation'] != 'AVOID')]
    
    # Experiment C = S6 + ML opportunity ranking (sizing by rank)
    # Since this is purely statistical offline, we just evaluate the subset of HIGH_OPPORTUNITY
    # to see if it outperforms the baseline (proxy for sizing impact).
    df_C = df[(df['s6_decision'] == 'BUY') & (df['recommendation'] == 'HIGH_OPPORTUNITY')]
    
    # Experiment D = S6 + both (Rug filter AND opportunity ranking)
    # Effectively same as C if HIGH_OPPORTUNITY naturally excludes AVOID
    df_D = df[(df['s6_decision'] == 'BUY') & (df['recommendation'] == 'HIGH_OPPORTUNITY') & (df['p_rug'] < 0.5)]

    experiments = {
        "A (S6 Alone)": df_A,
        "B (S6 + Rug Filter)": df_B,
        "C (S6 + Opp Ranking)": df_C,
        "D (S6 + Both)": df_D
    }
    
    for name, exp_df in experiments.items():
        metrics = calculate_metrics(exp_df)
        print(f"--- Experiment {name} ---")
        print(f"Entries       : {metrics['entries']}")
        print(f"Win Rate      : {metrics['win_rate']*100:.1f}%")
        print(f"Rug Rate      : {metrics['rug_rate']*100:.1f}%")
        print(f"Avg Return    : {metrics['avg_ret']*100:.1f}%")
        print(f"Median Return : {metrics['med_ret']*100:.1f}%")
        print(f"Profit Factor : {metrics['profit_factor']:.2f}")
        print(f"Expected Val  : {metrics['ev']:.3f}")
        print(f"2x Capture    : {metrics['capture_2x']*100:.1f}%")
        print(f"5x Capture    : {metrics['capture_5x']*100:.1f}%")
        print(f"10x Capture   : {metrics['capture_10x']*100:.1f}%")
        print(f"Max DD (est)  : {metrics['max_dd']*100:.1f}%")
        print("")

if __name__ == "__main__":
    df = load_data()
    agreement_analysis(df)
    paper_experiment(df)
