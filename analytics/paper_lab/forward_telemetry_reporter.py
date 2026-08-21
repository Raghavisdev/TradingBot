import os
import sys
import sqlite3
import argparse
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import DATABASE

def generate_report(mode="DAILY"):
    print(f"Generating {mode} Forward Telemetry Report...")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # 1. Signals Received
    cursor.execute("SELECT COUNT(*) FROM signals")
    total_signals = cursor.fetchone()[0]

    # 2. S6 Entries & Skips
    cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE strategy_id = 'default'")
    s6_entries = cursor.fetchone()[0]
    s6_skips = total_signals - s6_entries

    # 3. Wins / Losses
    cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'CLOSED' AND realized_pnl > 0")
    s6_wins = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'CLOSED' AND realized_pnl <= 0")
    s6_losses = cursor.fetchone()[0]
    win_rate = (s6_wins / (s6_wins + s6_losses) * 100) if (s6_wins + s6_losses) > 0 else 0

    # 4. P&L & Costs
    cursor.execute("SELECT SUM(invested), SUM(realized_pnl), SUM(fees), SUM(slippage), SUM(network_fee), SUM(commission) FROM paper_trades WHERE status = 'CLOSED'")
    row = cursor.fetchone()
    invested = row[0] or 0.0
    net_pnl = row[1] or 0.0
    fees = row[2] or 0.0
    slippage = row[3] or 0.0
    network_fee = row[4] or 0.0
    commission = row[5] or 0.0
    
    total_costs = fees + slippage + network_fee + commission
    gross_pnl = net_pnl + total_costs
    
    avg_cost = total_costs / s6_entries if s6_entries > 0 else 0.0
    
    cursor.execute("SELECT SUM(realized_pnl) FROM paper_trades WHERE status = 'CLOSED' AND realized_pnl > 0")
    gross_profits = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(realized_pnl) FROM paper_trades WHERE status = 'CLOSED' AND realized_pnl <= 0")
    gross_losses = abs(cursor.fetchone()[0] or 0.0)
    
    pf = (gross_profits / gross_losses) if gross_losses > 0 else 0.0
    
    # 5. ML / S6 Agreement and Missed Opportunities
    cursor.execute("""
        SELECT 
            s6_decision, recommendation, p_rug, expected_return,
            (SELECT max_return FROM outcomes WHERE outcomes.signal_id = s7.signal_id) as max_ret,
            (SELECT returned_2x FROM outcomes WHERE outcomes.signal_id = s7.signal_id) as ret_2x,
            (SELECT returned_5x FROM outcomes WHERE outcomes.signal_id = s7.signal_id) as ret_5x,
            (SELECT returned_10x FROM outcomes WHERE outcomes.signal_id = s7.signal_id) as ret_10x
        FROM s7_shadow_decisions s7
    """)
    shadows = cursor.fetchall()
    
    s6_skip_ml_opp = 0
    ml_high_opp = 0
    cap_2x = 0
    cap_5x = 0
    cap_10x = 0
    extreme_win = 0
    s6_skipped_winners = 0
    
    for row in shadows:
        s6_dec = row[0]
        ml_rec = row[1]
        p_rug = row[2]
        max_ret = row[4] or 0
        ret_2x = row[5] or 0
        ret_5x = row[6] or 0
        ret_10x = row[7] or 0
        
        if ml_rec in ["HIGH_OPPORTUNITY", "CANDIDATE"]:
            ml_high_opp += 1
            if s6_dec not in ["BUY", "STRONG BUY"]:
                s6_skip_ml_opp += 1
                
        if s6_dec in ["BUY", "STRONG BUY"]:
            if ret_2x: cap_2x += 1
            if ret_5x: cap_5x += 1
            if ret_10x: cap_10x += 1
            if max_ret >= 50.0: extreme_win += 1
        else:
            if max_ret >= 2.0:
                s6_skipped_winners += 1
                
    # Generate Markdown
    md = f"# {mode} Forward Telemetry Report\n"
    md += f"Generated: {datetime.utcnow().isoformat()}Z\n\n"
    
    md += "### S6 Execution Metrics\n"
    md += f"- **Signals Received:** {total_signals}\n"
    md += f"- **S6 Entries:** {s6_entries}\n"
    md += f"- **S6 Skips:** {s6_skips}\n"
    md += f"- **S6 Wins / Losses:** {s6_wins} / {s6_losses} ({win_rate:.1f}%)\n"
    md += f"- **Profit Factor:** {pf:.2f}\n"
    md += f"- **Gross P&L:** ${gross_pnl:.2f}\n"
    md += f"- **Total Execution Costs:** ${total_costs:.2f}\n"
    md += f"- **Net P&L:** ${net_pnl:.2f}\n"
    md += f"- **Average Cost/Trade:** ${avg_cost:.2f}\n"
    
    md += "\n### Opportunity Capture\n"
    md += f"- **2x Captures:** {cap_2x}\n"
    md += f"- **5x Captures:** {cap_5x}\n"
    md += f"- **10x Captures:** {cap_10x}\n"
    md += f"- **Extreme Winners (>= 50x):** {extreme_win}\n"
    md += f"- **S6-Skipped Winners (>= 2x):** {s6_skipped_winners}\n"
    
    md += "\n### ML Shadow Analysis\n"
    md += f"- **ML Identified Opportunities:** {ml_high_opp}\n"
    md += f"- **ML Opportunities Skipped by S6:** {s6_skip_ml_opp}\n"
    
    filename = f"S6_FORWARD_AUDIT.md" if mode == "FINAL_72H" else f"DAILY_REPORT_{datetime.utcnow().strftime('%Y%m%d')}.md"
    
    report_path = os.path.join(os.path.dirname(__file__), filename)
    with open(report_path, "w") as f:
        f.write(md)
    print(f"Saved {report_path}")

if __name__ == "__main__":
    mode = "DAILY"
    if len(sys.argv) > 1 and sys.argv[1] == "--final":
        mode = "FINAL_72H"
    generate_report(mode)
