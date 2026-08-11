"""
analytics/paper_lab/report.py
-------------------------------
Report Generator for Paper Lab (Phase 3).

Output folder: analytics/paper_lab/results/

Files generated:
  - daily_report.csv
  - strategy_performance.csv
  - trade_attribution.csv
  - equity_curves.csv
  - PAPER_LAB_REPORT.txt

CRITICAL: Strictly separates FORWARD_PAPER metrics from HISTORICAL_REPLAY metrics.
Never combines historical replay numbers with forward paper trading numbers.
"""

import os
import csv
import time
from datetime import datetime

from analytics.paper_lab import metrics as M

_RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results"
)


def _ensure_dir():
    os.makedirs(_RESULTS_DIR, exist_ok=True)


def _path(filename):
    _ensure_dir()
    return os.path.join(_RESULTS_DIR, filename)


def _write_csv(filename, rows, fieldnames=None):
    if not rows:
        # Create empty file with headers if fieldnames provided
        if fieldnames:
            with open(_path(filename), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
        return
    fnames = fieldnames or list(rows[0].keys())
    with open(_path(filename), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def generate_paper_lab_reports(portfolios_map, all_trades_list=None, signals_considered_count=0):
    """
    Generates all forward-paper trading CSV reports and PAPER_LAB_REPORT.txt text report.

    Args:
        portfolios_map: dict mapping strategy_id -> LabPortfolio instance
        all_trades_list: optional list of all closed trade dicts (loaded from DB or portfolios)
        signals_considered_count: total new signals evaluated in forward paper lab
    """
    print("\n[PAPER LAB REPORT] Generating forward-paper performance reports...")
    _ensure_dir()

    # Collect strategy performance summaries
    perf_rows = []
    equity_rows = []
    trade_rows = []

    for strat_id, port in sorted(portfolios_map.items()):
        trades = port.closed_trades
        m = M.compute_lab_strategy_metrics(
            strat_id, trades, port, signals_considered_count=signals_considered_count
        )
        perf_rows.append(m)

        # Equity curve rows
        for ts, eq in port.equity_curve:
            equity_rows.append({
                "strategy_id": strat_id,
                "timestamp":   ts,
                "equity":      round(eq, 4),
                "cash":        round(port.cash, 4) if ts == port.equity_curve[-1][0] else "",
            })

        # Trade attribution rows
        for t in trades:
            trade_rows.append({
                "strategy_id":       strat_id,
                "strategy_version":  t.get("strategy_version", "1.0"),
                "trade_id":          t.get("trade_id", ""),
                "signal_id":        t.get("signal_id", ""),
                "symbol":           t.get("symbol", ""),
                "entry_time":       t.get("entry_time", ""),
                "exit_time":        t.get("exit_time", ""),
                "exit_reason":      t.get("exit_reason", ""),
                "invested":         t.get("invested", 0.0),
                "realized_pnl":     t.get("realized_pnl", 0.0),
                "realized_pct":     t.get("realized_pct", 0.0),
                "mfe":              t.get("mfe", 0.0),
                "mae":              t.get("mae", 0.0),
                "holding_seconds":  t.get("holding_seconds", 0.0),
            })

    # Write CSVs
    _write_csv("strategy_performance.csv", perf_rows)
    _write_csv("equity_curves.csv", equity_rows)
    _write_csv("trade_attribution.csv", trade_rows)

    # Daily report CSV (summary by day)
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_rows = []
    for p in perf_rows:
        daily_rows.append({
            "date":              today_str,
            "strategy_id":        p["strategy_id"],
            "signals_considered": p["signals_considered"],
            "signals_traded":     p["signals_traded"],
            "completed_trades":   p["n_completed_trades"],
            "realized_pnl":       p["total_realized_pnl"],
            "return_pct":         p["total_return_pct"],
            "win_rate_pct":       p["win_rate_pct"],
            "max_drawdown_pct":   p["max_drawdown_pct"],
        })
    _write_csv("daily_report.csv", daily_rows)

    # Generate PAPER_LAB_REPORT.txt
    _write_text_report(perf_rows, signals_considered_count)

    print(f"  [REPORT] Forward-paper reports generated in: {_RESULTS_DIR}")
    return perf_rows


def _write_text_report(perf_rows, signals_considered_count):
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("============================================================")
    lines.append("PAPER LAB FORWARD-TESTING REPORT")
    lines.append("============================================================")
    lines.append(f"Generated : {now}")
    lines.append(f"Sample Type: FORWARD_PAPER (Real-Time Observer Engine)")
    lines.append(f"Signals Evaluated : {signals_considered_count}")
    lines.append(f"Starting Capital  : $100.00 PER STRATEGY (Isolated)")
    lines.append("")
    lines.append("------------------------------------------------------------")
    lines.append("IMPORTANT: HISTORICAL REPLAY vs FORWARD PAPER SEPARATION")
    lines.append("------------------------------------------------------------")
    lines.append("  Historical Replay Sample : 14 completed historical signals")
    lines.append(f"  Forward Paper Sample     : {signals_considered_count} new forward signals")
    lines.append("  Note: Forward paper trading results are tracked in real time")
    lines.append("  and are NEVER combined with historical replay figures.")
    lines.append("")
    lines.append("------------------------------------------------------------")
    lines.append("STRATEGY FORWARD PERFORMANCE SUMMARY")
    lines.append("------------------------------------------------------------")
    lines.append("")
    header = (f"{'Strategy':<25} {'Return%':>8} {'WinR%':>6} {'PF':>6} "
              f"{'MaxDD%':>7} {'Traded':>6} {'Skipped':>7} {'Robust':>7}")
    lines.append(header)
    lines.append("-" * 80)

    for p in perf_rows:
        robust = "NO" if p["moonshot_dependent"] else "YES"
        lines.append(
            f"{p['strategy_id']:<25} "
            f"{p['total_return_pct']:>8.2f} "
            f"{p['win_rate_pct']:>6.1f} "
            f"{p['profit_factor']:>6.3f} "
            f"{p['max_drawdown_pct']:>7.2f} "
            f"{p['signals_traded']:>6} "
            f"{p['signals_skipped']:>7} "
            f"{robust:>7}"
        )
    lines.append("")
    lines.append("------------------------------------------------------------")
    lines.append("DETAILED STRATEGY METRICS")
    lines.append("------------------------------------------------------------")

    for p in perf_rows:
        lines.append(f"\n  Strategy: {p['strategy_id']}")
        lines.append(f"    Signals Considered : {p['signals_considered']}")
        lines.append(f"    Signals Traded     : {p['signals_traded']} (Entry Rate: {p['entry_rate_pct']}%)")
        lines.append(f"    Signals Skipped    : {p['signals_skipped']}")
        lines.append(f"    Completed Trades   : {p['n_completed_trades']}")
        lines.append(f"    Win Rate           : {p['win_rate_pct']}%")
        lines.append(f"    Total Realized P&L : ${p['total_realized_pnl']:+.2f} ({p['total_return_pct']:+.2f}%)")
        lines.append(f"    Avg / Median Trade : {p['avg_trade_pct']:+.2f}% / {p['median_trade_pct']:+.2f}%")
        lines.append(f"    Profit Factor      : {p['profit_factor']}")
        lines.append(f"    Max Drawdown       : {p['max_drawdown_pct']:.2f}%")
        lines.append(f"    Avg MFE / MAE      : +{p['avg_mfe']:.2f}% / {p['avg_mae']:.2f}%")
        lines.append(f"    Avg Holding Time   : {p['avg_holding_seconds']:.1f}s")
        lines.append(f"    Best / Worst Trade : +{p['best_trade_pct']:.2f}% / {p['worst_trade_pct']:.2f}%")
        lines.append(f"    Consecutive Losses : {p['consecutive_losses']}")
        lines.append(f"    Ret w/o Top 1 Trade: {p['return_without_top_1']:+.2f}%")
        lines.append(f"    Ret w/o Top 2 Trade: {p['return_without_top_2']:+.2f}%")
        lines.append(f"    Moonshot Dependent : {'YES' if p['moonshot_dependent'] else 'NO'}")

    lines.append("\n============================================================")
    lines.append("END OF FORWARD-TEST REPORT")
    lines.append("============================================================")

    report_text = "\n".join(lines)
    with open(_path("PAPER_LAB_REPORT.txt"), "w", encoding="utf-8") as f:
        f.write(report_text)
    print("  [REPORT] PAPER_LAB_REPORT.txt generated")


def generate_s6_forward_paper_report(db_path=None):
    """
    Generates S6_FORWARD_PAPER_REPORT.txt strictly for forward S6 v1.2 trades.
    Excludes all historical backtest rows.
    """
    import sqlite3
    import numpy as np

    path = db_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "trading.db"))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM paper_lab_trades
        WHERE strategy_id = 'S6_Moonshot_Ladder' AND strategy_version = '1.2'
        ORDER BY id ASC
    """)
    trades = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM paper_lab_s6_forward_metadata
        ORDER BY id ASC
    """)
    metadata_rows = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM paper_lab_equity
        WHERE strategy_id = 'S6_Moonshot_Ladder'
        ORDER BY timestamp ASC
    """)
    equity_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    start_eq = 500.0
    current_eq = equity_rows[-1]["equity"] if equity_rows else start_eq
    net_pnl = current_eq - start_eq
    return_pct = (net_pnl / start_eq) * 100.0 if start_eq > 0 else 0.0

    completed_trades = [t for t in trades if t["status"] == "CLOSED"]
    n_entries = len(trades)
    pnls = [t.get("realized_pnl", 0.0) for t in completed_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = (len(wins) / len(completed_trades) * 100.0) if completed_trades else 0.0
    gross_gp = sum(wins)
    gross_gl = abs(sum(losses))
    pf = (gross_gp / gross_gl) if gross_gl > 0 else (999.0 if gross_gp > 0 else 0.0)

    avg_w = np.mean(wins) if wins else 0.0
    avg_l = np.mean(losses) if losses else 0.0

    # Drawdown from equity series
    eq_vals = [e["equity"] for e in equity_rows] if equity_rows else [start_eq]
    peak = start_eq
    max_dd = 0.0
    for v in eq_vals:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100.0 if peak > 0 else 0.0
        if dd > max_dd: max_dd = dd

    allocs = [t.get("invested", 0.0) for t in trades]
    avg_alloc = np.mean(allocs) if allocs else 0.0

    num_exploratory = sum(1 for a in allocs if a <= 2.50)
    num_normal = sum(1 for a in allocs if 2.50 < a <= 6.50)
    num_strong = sum(1 for a in allocs if 6.50 < a <= 12.50)
    num_exceptional = sum(1 for a in allocs if a > 12.50)

    lines = []
    lines.append("============================================================")
    lines.append("  S6_MOONSHOT_LADDER v1.2 FORWARD PAPER-LAB VALIDATION REPORT")
    lines.append("============================================================")
    lines.append(f"  Report Time             : {datetime.now().isoformat()}")
    lines.append(f"  Starting Equity         : ${start_eq:.2f}")
    lines.append(f"  Current Equity          : ${current_eq:.2f}")
    lines.append(f"  Net P&L                 : ${net_pnl:+.2f} ({return_pct:+.2f}%)")
    lines.append(f"  Total Entries           : {n_entries}")
    lines.append(f"  Completed Trades        : {len(completed_trades)}")
    lines.append(f"  Wins / Losses           : {len(wins)} / {len(losses)}")
    lines.append(f"  Win Rate                : {win_rate:.1f}%")
    lines.append(f"  Profit Factor           : {pf:.2f}")
    lines.append(f"  Gross Profit            : ${gross_gp:.2f}")
    lines.append(f"  Gross Loss              : ${gross_gl:.2f}")
    lines.append(f"  Avg Win / Avg Loss      : ${avg_w:+.2f} / ${avg_l:+.2f}")
    lines.append(f"  Max Drawdown            : {max_dd:.2f}%")
    lines.append(f"  Avg Allocation          : ${avg_alloc:.2f}")
    lines.append("  Allocation Breakdown    :")
    lines.append(f"    - $2 Exploratory Entries : {num_exploratory}")
    lines.append(f"    - $5 Normal Entries      : {num_normal}")
    lines.append(f"    - $9 Strong Entries      : {num_strong}")
    lines.append(f"    - $14 Exceptional Entries: {num_exceptional}")
    lines.append("============================================================")

    out_text = "\n".join(lines)
    _ensure_dir()
    with open(_path("S6_FORWARD_PAPER_REPORT.txt"), "w", encoding="utf-8") as f:
        f.write(out_text)
    print("  [REPORT] S6_FORWARD_PAPER_REPORT.txt generated")

    return {
        "starting_equity": start_eq,
        "current_equity": current_eq,
        "net_pnl": net_pnl,
        "return_pct": return_pct,
        "total_entries": n_entries,
        "win_rate": win_rate,
        "profit_factor": pf,
        "max_drawdown": max_dd
    }
