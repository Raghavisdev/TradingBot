from __future__ import annotations

from typing import Any

# Minimum final_score to be eligible for S6 entry
S6_MIN_FINAL_SCORE = 60.0

# Quality dimension weights (must sum to 1.0)
S6_Q_WEIGHTS = {
    "buy_sell":   0.30,
    "liquidity":  0.25,
    "market_cap": 0.15,
    "gt_score":   0.15,
    "final_score": 0.15,
}


def compute_entry_quality(signal: dict[str, Any]) -> float:
    """
    Compute a normalized quality score in [0, 1] from execution-time signal data.
    Used for telemetry/logging only — does NOT influence LAPC-v2 probe amount.
    """
    # --- Buy/sell ratio component ---
    buys  = signal.get("buys")  if signal.get("buys")  is not None else signal.get("buys_5m")
    sells = signal.get("sells") if signal.get("sells") is not None else signal.get("sells_5m")
    b_cnt = float(buys  or 0)
    s_cnt = float(sells or 0)
    bs_ratio = float(b_cnt) / float(s_cnt) if float(s_cnt) > 0 else 0.2
    if   bs_ratio < 0.8: q_bs = 0.5
    elif bs_ratio < 1.2: q_bs = 0.8
    elif bs_ratio < 1.5: q_bs = 1.2
    else:                q_bs = 1.5
    q_bs = min(q_bs, 3.0) / 3.0

    # --- Liquidity component ---
    liq_val = signal.get("liquidity", 0.0)
    liq = float(liq_val or 0.0)
    if   liq < 1000:   q_liq = 0.0
    elif liq < 10000:  q_liq = 0.3
    elif liq < 15000:  q_liq = 0.4
    elif liq < 16000:  q_liq = 0.4
    elif liq < 25000:  q_liq = 0.6
    elif liq < 35000:  q_liq = 0.7
    elif liq < 40000:  q_liq = 0.8
    elif liq < 44000:  q_liq = 0.8
    else:              q_liq = 1.0

    # --- Market cap component ---
    mc_val = signal.get("signal_market_cap") or signal.get("snap_mc", 0)
    mc = float(mc_val or 0)
    if   mc < 10000:  q_mc = 0.0
    elif mc < 25000:  q_mc = 0.4
    elif mc < 35000:  q_mc = 0.6
    elif mc < 40000:  q_mc = 0.7
    elif mc < 44000:  q_mc = 0.8
    elif mc < 60000:  q_mc = 0.8
    elif mc < 100000: q_mc = 0.6
    else:             q_mc = 0.5

    # --- GemTools score component ---
    gt_val = signal.get("gt_score", 0)
    gt = float(gt_val or 0)
    if   gt >= 3: q_gt = 1.0
    elif gt == 2: q_gt = 0.8
    elif gt == 1: q_gt = 0.5
    else:         q_gt = 0.2

    # --- Final score component ---
    fs_val = signal.get("final_score", 0)
    fs = float(fs_val or 0)
    if   fs >= 70.0: q_fs = 1.0
    elif fs >= 65.0: q_fs = 0.7
    elif fs >= 60.0: q_fs = 0.3
    else:            q_fs = 0.0

    quality = (
        S6_Q_WEIGHTS["buy_sell"]    * q_bs +
        S6_Q_WEIGHTS["liquidity"]   * q_liq +
        S6_Q_WEIGHTS["market_cap"]  * q_mc +
        S6_Q_WEIGHTS["gt_score"]    * q_gt +
        S6_Q_WEIGHTS["final_score"] * q_fs
    )
    return min(max(quality, 0.0), 1.0)


def s6_base_size(quality: float) -> float:
    """
    Legacy quality-to-base-size mapping.
    RETAINED FOR TELEMETRY ONLY — not used in LAPC-v2 probe amount.
    """
    if quality < 0.35: return 2.0
    if quality < 0.60: return 5.0
    if quality < 0.80: return 9.0
    return 14.0


def s6_buy_sell_multiplier(signal: dict[str, Any]) -> float:
    """
    Buy/sell ratio multiplier.
    RETAINED FOR TELEMETRY ONLY — not used in LAPC-v2 probe amount.
    """
    buys  = signal.get("buys")  if signal.get("buys")  is not None else signal.get("buys_5m")
    sells = signal.get("sells") if signal.get("sells") is not None else signal.get("sells_5m")

    if buys is not None and sells is not None and float(sells or 0) > 0:
        bs_ratio = float(buys) / float(sells)
    elif signal.get("buy_sell_ratio") is not None:
        bs_ratio = float(signal.get("buy_sell_ratio"))
    else:
        bs_ratio = 1.0

    if   bs_ratio < 1.0: return 0.75
    elif bs_ratio < 1.2: return 1.0
    elif bs_ratio < 1.5: return 1.25
    else:                return 1.5
