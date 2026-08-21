import sqlite3
import json
import os
import sys
import numpy as np

sys.path.insert(0, '/home/tradingbot/TradingBot')
from analytics.paper_lab.strategies import Strategy_S6_Moonshot_Ladder
from analytics.paper_lab.cost_simulator import ExecutionCostSimulator

class MockPortfolio:
    def __init__(self):
        self.total_equity = 500.0
        self.initial_cash = 500.0
        self._peak_equity = 500.0
        self.cash = 500.0
        self.open_positions = []
    def has_traded_signal(self, sig_id): return False
    def can_open(self, amount): return True
    def can_open_capital_aware(self, amount, max_deployed_pct=0.15): return True
    
def get_s6_return_gross(row):
    # Simulated S6 Ladder gross return based on max_return
    max_ret = row['max_return'] if row['max_return'] is not None else 0.0
    rugged = row.get('rugged', 0) == 1
    
    if rugged or max_ret < 0.2:
        return -0.20 # Hard stop
        
    # Ladder: +20% (20%), +50% (10%), +100% (10%), +200% (10%), +500% (10%), +1000% (10%), mb(30%)
    # This is a very rough gross return assuming peak hit perfectly
    # In reality trailing stops capture some fraction. 
    # For audit, we'll approximate realized gross
    if max_ret >= 10.0:
        return 3.0
    elif max_ret >= 5.0:
        return 1.5
    elif max_ret >= 2.0:
        return 0.5
    elif max_ret >= 1.0:
        return 0.2
    elif max_ret >= 0.5:
        return 0.1
    elif max_ret >= 0.2:
        return 0.05
    else:
        return -0.20

def estimate_cost(amount, liq, max_ret, rugged, mode="BASE"):
    if mode == "LOW":
        sim = ExecutionCostSimulator(mode="MODELED_COST", base_network_fee=0.01, tx_fail_prob=0.01)
        sim.jupiter_commission_rate = 0.001
    elif mode == "HIGH":
        sim = ExecutionCostSimulator(mode="MODELED_COST", base_network_fee=0.05, tx_fail_prob=0.10)
        sim.jupiter_commission_rate = 0.005
    else:
        sim = ExecutionCostSimulator(mode="MODELED_COST", base_network_fee=0.02, tx_fail_prob=0.05)
        sim.jupiter_commission_rate = 0.002
        
    entry = sim.estimate_entry_cost(amount, liq)
    
    # Exit cost - assume single exit for simplicity in this proxy, though ladder has multiple
    gross_ret = get_s6_return_gross({'max_return': max_ret, 'rugged': rugged})
    exit = sim.estimate_exit_cost(amount * (1 + gross_ret), liq)
    
    return entry['total_cost'] + exit['total_cost'], gross_ret

def run():
    conn = sqlite3.connect('/home/tradingbot/TradingBot/database/trading.db')
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT 
            s.signal_id, s.symbol, s.final_score, s.gt_score, s.signal_market_cap, s.timestamp,
            sd.feature_snapshot_json, sd.opportunity_score, sd.p_rug, sd.recommendation,
            o.max_return, o.rugged, o.returned_2x, o.returned_5x, o.returned_10x
        FROM outcomes o
        JOIN signals s ON o.signal_id = s.signal_id
        JOIN s7_shadow_decisions sd ON o.signal_id = sd.signal_id
        ORDER BY CAST(s.timestamp AS REAL) ASC
    """
    rows = conn.execute(query).fetchall()
    
    s6 = Strategy_S6_Moonshot_Ladder()
    
    # Trackers
    s6_gross = {'trades': 0, 'pnl': 0.0, 'allocs': []}
    s6_low = {'trades': 0, 'pnl': 0.0, 'costs': 0.0}
    s6_base = {'trades': 0, 'pnl': 0.0, 'costs': 0.0}
    s6_high = {'trades': 0, 'pnl': 0.0, 'costs': 0.0}
    
    # Phase 6
    sA = {'trades': 0, 'pnl': 0.0, 'costs': 0.0, '2x': 0, '10x': 0, 'rug': 0}
    sB = {'trades': 0, 'pnl': 0.0, 'costs': 0.0, '2x': 0, '10x': 0, 'rug': 0}
    sC = {'trades': 0, 'pnl': 0.0, 'costs': 0.0, '2x': 0, '10x': 0, 'rug': 0}
    sD = {'trades': 0, 'pnl': 0.0, 'costs': 0.0, '2x': 0, '10x': 0, 'rug': 0}
    sE = {'trades': 0, 'pnl': 0.0, 'costs': 0.0, '2x': 0, '10x': 0, 'rug': 0}
    
    # ML Rescue specific
    ml_rescue_trades = 0
    ml_rescue_pnl = 0.0
    ml_rescue_costs = 0.0
    ml_rescue_rug = 0
    ml_rescue_10x = 0
    
    for row in rows:
        max_ret = row['max_return'] if row['max_return'] is not None else 0.0
        rugged = row['rugged'] == 1
        p_rug = row['p_rug'] if row['p_rug'] is not None else 1.0
        opp = row['opportunity_score'] if row['opportunity_score'] is not None else -1.0
        
        # Build Sig
        sig = {
            "signal_id": row["signal_id"],
            "symbol": row["symbol"],
            "final_score": row["final_score"],
            "gt_score": row["gt_score"],
            "signal_market_cap": row["signal_market_cap"],
            "valid": True
        }
        liq = 1000.0
        if row["feature_snapshot_json"]:
            try:
                snap = json.loads(row["feature_snapshot_json"])
                sig["buys"] = snap.get("buys")
                sig["sells"] = snap.get("sells")
                sig["liquidity"] = snap.get("liquidity")
                liq = float(snap.get("liquidity") or 1000.0)
            except: pass
            
        alloc = s6.evaluate_entry(sig, MockPortfolio())
        s6_entered = (alloc > 0)
        
        cost_low, gross_ret = estimate_cost(alloc, liq, max_ret, rugged, "LOW")
        cost_base, _ = estimate_cost(alloc, liq, max_ret, rugged, "BASE")
        cost_high, _ = estimate_cost(alloc, liq, max_ret, rugged, "HIGH")
        
        # ML Rescue
        rescue_entry = False
        if not s6_entered and p_rug < 0.7 and opp >= 0.7: # ML highly confident
            rescue_entry = True
            
        ml_only_entry = (p_rug < 0.7 and opp >= 0.7)
        
        if s6_entered:
            s6_gross['trades'] += 1
            s6_gross['pnl'] += alloc * gross_ret
            s6_gross['allocs'].append(alloc)
            
            s6_low['trades'] += 1
            s6_low['pnl'] += (alloc * gross_ret) - cost_low
            s6_low['costs'] += cost_low
            
            s6_base['trades'] += 1
            s6_base['pnl'] += (alloc * gross_ret) - cost_base
            s6_base['costs'] += cost_base
            
            s6_high['trades'] += 1
            s6_high['pnl'] += (alloc * gross_ret) - cost_high
            s6_high['costs'] += cost_high
            
            # Strat A
            sA['trades'] += 1; sA['pnl'] += (alloc * gross_ret) - cost_base; sA['costs'] += cost_base
            if max_ret >= 2.0: sA['2x'] += 1
            if max_ret >= 10.0: sA['10x'] += 1
            if rugged: sA['rug'] += 1
            
            # Strat B (S6 + Rug Filter)
            if p_rug < 0.7:
                sB['trades'] += 1; sB['pnl'] += (alloc * gross_ret) - cost_base; sB['costs'] += cost_base
                if max_ret >= 2.0: sB['2x'] += 1
                if max_ret >= 10.0: sB['10x'] += 1
                if rugged: sB['rug'] += 1
                
            # Strat C (S6 + Opp)
            if opp >= 0.5:
                sC['trades'] += 1; sC['pnl'] += (alloc * gross_ret) - cost_base; sC['costs'] += cost_base
                if max_ret >= 2.0: sC['2x'] += 1
                if max_ret >= 10.0: sC['10x'] += 1
                if rugged: sC['rug'] += 1
                
            # Strat D (S6 + Rescue) -> Same as S6 entry + Rescue
            sD['trades'] += 1; sD['pnl'] += (alloc * gross_ret) - cost_base; sD['costs'] += cost_base
            if max_ret >= 2.0: sD['2x'] += 1
            if max_ret >= 10.0: sD['10x'] += 1
            if rugged: sD['rug'] += 1
            
        if rescue_entry:
            # Hypothetical $5 rescue size
            resc_cost, resc_ret = estimate_cost(5.0, liq, max_ret, rugged, "BASE")
            ml_rescue_trades += 1
            ml_rescue_pnl += (5.0 * resc_ret) - resc_cost
            ml_rescue_costs += resc_cost
            if rugged: ml_rescue_rug += 1
            if max_ret >= 10.0: ml_rescue_10x += 1
            
            # Add to Strat D
            sD['trades'] += 1; sD['pnl'] += (5.0 * resc_ret) - resc_cost; sD['costs'] += resc_cost
            if max_ret >= 2.0: sD['2x'] += 1
            if max_ret >= 10.0: sD['10x'] += 1
            if rugged: sD['rug'] += 1
            
        if ml_only_entry:
            cst, ret = estimate_cost(5.0, liq, max_ret, rugged, "BASE")
            sE['trades'] += 1; sE['pnl'] += (5.0 * ret) - cst; sE['costs'] += cst
            if max_ret >= 2.0: sE['2x'] += 1
            if max_ret >= 10.0: sE['10x'] += 1
            if rugged: sE['rug'] += 1
            
    # Phase 4 Output
    r4 = "# S6 Cost-Aware Audit\n\n"
    r4 += "| Scenario | Trades | Gross PnL | Costs | Net PnL |\n"
    r4 += "|---|---|---|---|---|\n"
    r4 += f"| S6_GROSS | {s6_gross['trades']} | ${s6_gross['pnl']:.2f} | $0.00 | ${s6_gross['pnl']:.2f} |\n"
    r4 += f"| S6_NET_LOW_COST | {s6_low['trades']} | ${s6_gross['pnl']:.2f} | ${s6_low['costs']:.2f} | ${s6_low['pnl']:.2f} |\n"
    r4 += f"| S6_NET_BASE_COST | {s6_base['trades']} | ${s6_gross['pnl']:.2f} | ${s6_base['costs']:.2f} | ${s6_base['pnl']:.2f} |\n"
    r4 += f"| S6_NET_HIGH_COST | {s6_high['trades']} | ${s6_gross['pnl']:.2f} | ${s6_high['costs']:.2f} | ${s6_high['pnl']:.2f} |\n"
    with open('/home/tradingbot/TradingBot/analytics/paper_lab/S6_COST_AWARE_AUDIT.md', 'w') as f:
        f.write(r4)
        
    # Phase 5 & 6 Output
    r6 = "# Strategy Final Audit\n\n"
    r6 += "## ML Missed-Winner Rescue\n"
    r6 += f"Rescue Trades: {ml_rescue_trades}\n"
    r6 += f"Rescue Net PnL: ${ml_rescue_pnl:.2f}\n"
    r6 += f"Rescue 10x captured: {ml_rescue_10x}\n"
    r6 += f"Rescue Rugs: {ml_rescue_rug}\n\n"
    
    r6 += "## Combined Strategy Matrix\n"
    r6 += "| Strategy | Trades | Rugs | 2x | 10x | Costs | Net PnL |\n"
    r6 += "|---|---|---|---|---|---|---|\n"
    r6 += f"| A. S6 v1.2 | {sA['trades']} | {sA['rug']} | {sA['2x']} | {sA['10x']} | ${sA['costs']:.2f} | ${sA['pnl']:.2f} |\n"
    r6 += f"| B. S6 + ML Rug Filter | {sB['trades']} | {sB['rug']} | {sB['2x']} | {sB['10x']} | ${sB['costs']:.2f} | ${sB['pnl']:.2f} |\n"
    r6 += f"| C. S6 + ML Opp Rank | {sC['trades']} | {sC['rug']} | {sC['2x']} | {sC['10x']} | ${sC['costs']:.2f} | ${sC['pnl']:.2f} |\n"
    r6 += f"| D. S6 + ML Rescue | {sD['trades']} | {sD['rug']} | {sD['2x']} | {sD['10x']} | ${sD['costs']:.2f} | ${sD['pnl']:.2f} |\n"
    r6 += f"| E. ML Only | {sE['trades']} | {sE['rug']} | {sE['2x']} | {sE['10x']} | ${sE['costs']:.2f} | ${sE['pnl']:.2f} |\n"
    
    with open('/home/tradingbot/TradingBot/analytics/paper_lab/STRATEGY_FINAL_AUDIT.md', 'w') as f:
        f.write(r6)
        
    # Also write ML_S6_COMPARISON_AUDIT.md as a copy of rescue section
    r5 = "# ML vs S6 Comparison (Missed Winner Rescue)\n\n"
    r5 += f"For signals REJECTED by S6, ML identified {ml_rescue_trades} high-opportunity trades.\n"
    r5 += f"Incremental Net PnL (Base Costs): ${ml_rescue_pnl:.2f}\n"
    r5 += f"Incremental 10x Runners Captured: {ml_rescue_10x}\n"
    r5 += f"Incremental Rugs Incurred: {ml_rescue_rug}\n"
    with open('/home/tradingbot/TradingBot/analytics/paper_lab/ML_S6_COMPARISON_AUDIT.md', 'w') as f:
        f.write(r5)

    print("Phase 4, 5, 6 audits generated.")

if __name__ == '__main__':
    run()
