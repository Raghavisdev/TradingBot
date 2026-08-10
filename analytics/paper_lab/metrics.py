"""
analytics/paper_lab/metrics.py
--------------------------------
Forward testing performance metrics calculator for Paper Lab (Phase 3).

Pure functions — accepts trade list, portfolio, and signals considered count.
Returns structured performance metrics dictionary per strategy.
"""

import math


def _safe_div(a, b):
    return a / b if b else 0.0


def _median(vals):
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def compute_lab_strategy_metrics(strategy_id, trades, portfolio, signals_considered_count=0):
    """
    Computes complete forward-test performance metrics for a strategy.
    """
    n = len(trades)
    initial_cash = portfolio.initial_cash if portfolio else 100.0

    if n == 0:
        return {
            "strategy_id":             strategy_id,
            "signals_considered":      signals_considered_count,
            "signals_traded":          0,
            "signals_skipped":         signals_considered_count,
            "entry_rate_pct":          0.0,
            "n_completed_trades":      0,
            "win_rate_pct":            0.0,
            "total_realized_pnl":      0.0,
            "total_return_pct":        0.0,
            "avg_trade_pct":           0.0,
            "median_trade_pct":        0.0,
            "profit_factor":           0.0,
            "max_drawdown_pct":        portfolio.max_drawdown_pct if portfolio else 0.0,
            "avg_mfe":                 0.0,
            "avg_mae":                 0.0,
            "avg_holding_seconds":     0.0,
            "best_trade_pct":          0.0,
            "worst_trade_pct":         0.0,
            "consecutive_losses":      0,
            "capital_utilization_pct": 0.0,
            "return_without_top_1":    0.0,
            "return_without_top_2":    0.0,
            "moonshot_dependent":      False,
        }

    pnl_pcts  = [t.get("realized_pct", t.get("total_pnl_pct", 0.0)) for t in trades]
    pnl_dolls = [t.get("realized_pnl", t.get("total_pnl", 0.0)) for t in trades]
    invested  = [t.get("invested", 0.0) for t in trades]
    mfes      = [t.get("mfe", 0.0) for t in trades]
    maes      = [t.get("mae", 0.0) for t in trades]
    holding   = [t.get("holding_seconds", 0.0) for t in trades if t.get("holding_seconds")]

    wins   = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]

    win_rate = _safe_div(len(wins), n) * 100.0
    gp = sum(p for p in pnl_dolls if p > 0)
    gl = abs(sum(p for p in pnl_dolls if p < 0))
    profit_factor = _safe_div(gp, gl)

    tot_pnl_d = sum(pnl_dolls)
    tot_ret_pct = _safe_div(tot_pnl_d, initial_cash) * 100.0

    # Consecutive losses
    max_consec = 0
    cur_consec = 0
    for p in pnl_pcts:
        if p <= 0:
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
        else:
            cur_consec = 0

    # Top trade dependency
    sorted_pnl = sorted(pnl_dolls, reverse=True)
    rem1 = sorted_pnl[1:] if len(sorted_pnl) > 1 else []
    rem2 = sorted_pnl[2:] if len(sorted_pnl) > 2 else []
    ret_wo1 = _safe_div(sum(rem1), initial_cash) * 100.0
    ret_wo2 = _safe_div(sum(rem2), initial_cash) * 100.0

    moonshot_dep = (ret_wo1 <= 0 and tot_ret_pct > 0)

    cap_util = _safe_div(sum(invested), n * initial_cash) * 100.0
    avg_hold = _safe_div(sum(holding), len(holding)) if holding else 0.0

    traded_cnt  = len(set(t.get("signal_id") for t in trades if t.get("signal_id")))
    skipped_cnt = max(0, signals_considered_count - traded_cnt)
    entry_rate  = _safe_div(traded_cnt, signals_considered_count) * 100.0 if signals_considered_count else 0.0

    return {
        "strategy_id":             strategy_id,
        "signals_considered":      signals_considered_count,
        "signals_traded":          traded_cnt,
        "signals_skipped":         skipped_cnt,
        "entry_rate_pct":          round(entry_rate, 2),
        "n_completed_trades":      n,
        "win_rate_pct":            round(win_rate, 2),
        "total_realized_pnl":      round(tot_pnl_d, 4),
        "total_return_pct":        round(tot_ret_pct, 4),
        "avg_trade_pct":           round(_safe_div(sum(pnl_pcts), n), 4),
        "median_trade_pct":        round(_median(pnl_pcts), 4),
        "profit_factor":           round(profit_factor, 4),
        "max_drawdown_pct":        round(portfolio.max_drawdown_pct if portfolio else 0.0, 4),
        "avg_mfe":                 round(_safe_div(sum(mfes), len(mfes)), 2),
        "avg_mae":                 round(_safe_div(sum(maes), len(maes)), 2),
        "avg_holding_seconds":     round(avg_hold, 1),
        "best_trade_pct":          round(max(pnl_pcts), 4),
        "worst_trade_pct":         round(min(pnl_pcts), 4),
        "consecutive_losses":      max_consec,
        "capital_utilization_pct": round(cap_util, 2),
        "return_without_top_1":    round(ret_wo1, 4),
        "return_without_top_2":    round(ret_wo2, 4),
        "moonshot_dependent":      moonshot_dep,
    }
