import sqlite3
import json
import os
import sys

# Ensure we can import from TradingBot
sys.path.insert(0, '/home/tradingbot/TradingBot')
from analytics.paper_lab.strategies import Strategy_S6_Moonshot_Ladder

def run_opportunity_audit():
    conn = sqlite3.connect('/home/tradingbot/TradingBot/database/trading.db')
    conn.row_factory = sqlite3.Row
    
    # We want ALL resolved signals, meaning they are in the outcomes table.
    query = """
        SELECT 
            s.signal_id, s.symbol, s.final_score, s.gt_score, s.signal_market_cap,
            sd.feature_snapshot_json, sd.opportunity_score, sd.p_rug, sd.recommendation,
            o.max_return, o.rugged, o.returned_2x, o.returned_5x, o.returned_10x
        FROM outcomes o
        JOIN signals s ON o.signal_id = s.signal_id
        LEFT JOIN s7_shadow_decisions sd ON o.signal_id = sd.signal_id
    """
    
    rows = conn.execute(query).fetchall()
    
    # S6 mock portfolio to check can_open (we just mock it returning True)
    class MockPortfolio:
        total_equity = 500.0
        initial_cash = 500.0
        _peak_equity = 500.0
        cash = 500.0
        open_positions = []
        def has_traded_signal(self, sig_id): return False
        def can_open(self, amount): return True
        def can_open_capital_aware(self, amount, max_deployed_pct=0.15): return True
        
    s6 = Strategy_S6_Moonshot_Ladder()
    port = MockPortfolio()
    
    total_signals = len(rows)
    s6_accepted = 0
    s6_rejected = 0
    
    # Captured winners
    cap_2x = 0
    cap_5x = 0
    cap_10x = 0
    cap_20x = 0
    cap_50x = 0
    cap_100x = 0
    
    # Missed winners
    miss_2x = 0
    miss_5x = 0
    miss_10x = 0
    miss_20x = 0
    miss_50x = 0
    miss_100x = 0
    
    missed_winner_details = []
    
    for row in rows:
        max_ret = row['max_return'] if row['max_return'] is not None else 0.0
        
        # Reconstruct signal dictionary for S6
        sig = {
            "signal_id": row["signal_id"],
            "symbol": row["symbol"],
            "final_score": row["final_score"],
            "gt_score": row["gt_score"],
            "signal_market_cap": row["signal_market_cap"],
            "valid": True # Historically if in DB it was generally valid
        }
        
        # Merge T0 snapshot
        if row["feature_snapshot_json"]:
            try:
                snap = json.loads(row["feature_snapshot_json"])
                sig["buys"] = snap.get("buys")
                sig["sells"] = snap.get("sells")
                sig["liquidity"] = snap.get("liquidity")
            except Exception:
                pass
                
        # Run S6
        allocation = s6.evaluate_entry(sig, port)
        accepted = (allocation > 0)
        
        if accepted:
            s6_accepted += 1
            if max_ret >= 100.0: cap_100x += 1
            if max_ret >= 50.0:  cap_50x += 1
            if max_ret >= 20.0:  cap_20x += 1
            if max_ret >= 10.0:  cap_10x += 1
            if max_ret >= 5.0:   cap_5x += 1
            if max_ret >= 2.0:   cap_2x += 1
        else:
            s6_rejected += 1
            is_winner = False
            if max_ret >= 100.0: miss_100x += 1; is_winner = True
            if max_ret >= 50.0:  miss_50x += 1; is_winner = True
            if max_ret >= 20.0:  miss_20x += 1; is_winner = True
            if max_ret >= 10.0:  miss_10x += 1; is_winner = True
            if max_ret >= 5.0:   miss_5x += 1; is_winner = True
            if max_ret >= 2.0:   miss_2x += 1; is_winner = True
            
            if max_ret >= 2.0:
                missed_winner_details.append({
                    "symbol": row["symbol"],
                    "max_ret": max_ret,
                    "s6_score": row["final_score"],
                    "opp_score": row["opportunity_score"],
                    "p_rug": row["p_rug"],
                    "ml_rec": row["recommendation"],
                    "liquidity": sig.get("liquidity")
                })
                
    # Generate Report
    missed_winner_details.sort(key=lambda x: x["max_ret"], reverse=True)
    
    report = f"# S6 Opportunity Coverage Audit\\n\\n"
    report += f"Total Resolved Signals: {total_signals}\\n"
    report += f"S6 Accepted (Hypothetical Base): {s6_accepted}\\n"
    report += f"S6 Rejected: {s6_rejected}\\n\\n"
    
    report += f"## Winner Capture Matrix\\n\\n"
    report += f"| Tier | Available | S6 Captured | S6 Missed | Capture Rate |\\n"
    report += f"|---|---|---|---|---|\\n"
    report += f"| >= 2x | {cap_2x + miss_2x} | {cap_2x} | {miss_2x} | {cap_2x/(cap_2x+miss_2x) if cap_2x+miss_2x > 0 else 0:.1%} |\\n"
    report += f"| >= 5x | {cap_5x + miss_5x} | {cap_5x} | {miss_5x} | {cap_5x/(cap_5x+miss_5x) if cap_5x+miss_5x > 0 else 0:.1%} |\\n"
    report += f"| >= 10x | {cap_10x + miss_10x} | {cap_10x} | {miss_10x} | {cap_10x/(cap_10x+miss_10x) if cap_10x+miss_10x > 0 else 0:.1%} |\\n"
    report += f"| >= 20x | {cap_20x + miss_20x} | {cap_20x} | {miss_20x} | {cap_20x/(cap_20x+miss_20x) if cap_20x+miss_20x > 0 else 0:.1%} |\\n"
    report += f"| >= 50x | {cap_50x + miss_50x} | {cap_50x} | {miss_50x} | {cap_50x/(cap_50x+miss_50x) if cap_50x+miss_50x > 0 else 0:.1%} |\\n"
    report += f"| >= 100x | {cap_100x + miss_100x} | {cap_100x} | {miss_100x} | {cap_100x/(cap_100x+miss_100x) if cap_100x+miss_100x > 0 else 0:.1%} |\\n\\n"
    
    report += f"## Top Missed Winners (>= 5x)\\n\\n"
    report += f"| Symbol | Max Return | S6 Score | T0 Liquidity | ML Opp Score | ML p_rug | ML Recommendation |\\n"
    report += f"|---|---|---|---|---|---|---|\\n"
    for w in missed_winner_details:
        if w["max_ret"] >= 5.0:
            opp = f'{w["opp_score"]:.3f}' if w["opp_score"] is not None else 'N/A'
            prug = f'{w["p_rug"]:.3f}' if w["p_rug"] is not None else 'N/A'
            liq = f'${w["liquidity"]:.0f}' if w["liquidity"] else 'N/A'
            report += f"| {w['symbol']} | {w['max_ret']:.1f}x | {w['s6_score']} | {liq} | {opp} | {prug} | {w['ml_rec']} |\\n"
            
    with open('/home/tradingbot/TradingBot/analytics/paper_lab/S6_OPPORTUNITY_COVERAGE_AUDIT.md', 'w') as f:
        f.write(report)
        
    print("Opportunity audit generated: analytics/paper_lab/S6_OPPORTUNITY_COVERAGE_AUDIT.md")

if __name__ == '__main__':
    run_opportunity_audit()
