"""
Module 9 — Momentum Engine v2
------------------------------
Computes velocity AND acceleration metrics from snapshot history.

v2 adds:
    mc_acceleration      : rate of change of mc_velocity (2nd derivative)
    holder_acceleration  : rate of change of holder_velocity
    volume_acceleration  : rate of change of volume_velocity
    buy_sell_ratio       : buys / (buys + sells) — proxy for buying pressure

Uses a 3-point window for acceleration:
    first → mid → last snapshots
    velocity = (last - first) / time
    acceleration = (v_last_half - v_first_half) / time

MODE: PASSIVE COLLECTION ONLY.
"""

import time


# ======================================================
# MATH HELPERS
# ======================================================

def _safe(val, default=0.0):
    return float(val) if val is not None and val != "" else default


def _pct_change(old_val, new_val) -> float:
    old_val = _safe(old_val)
    new_val = _safe(new_val)
    if old_val == 0:
        return 0.0
    return round(((new_val - old_val) / abs(old_val)) * 100.0, 4)


def _rate_per_hour(old_val, new_val, elapsed_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    delta = _safe(new_val) - _safe(old_val)
    hours = elapsed_seconds / 3600.0
    return round(delta / hours, 4)


# ======================================================
# FULL MOMENTUM CALCULATOR
# ======================================================

def calculate_momentum(snapshots: list) -> dict:
    """
    Computes velocity + acceleration from snapshot list.
    Requires ≥ 2 snapshots for velocity, ≥ 3 for acceleration.
    """
    default = {
        "mc_velocity": 0.0, "holder_velocity": 0.0,
        "volume_velocity": 0.0, "buy_velocity": 0.0,
        "liquidity_change": 0.0,
        "mc_acceleration": 0.0, "holder_acceleration": 0.0,
        "volume_acceleration": 0.0, "buy_sell_ratio": 0.0,
    }

    if not snapshots or len(snapshots) < 2:
        return default

    try:
        sorted_snaps = sorted(
            [s for s in snapshots if s.get("timestamp")],
            key=lambda s: float(s["timestamp"])
        )

        if len(sorted_snaps) < 2:
            return default

        first  = sorted_snaps[0]
        last   = sorted_snaps[-1]
        ts_first = float(first.get("timestamp", 0))
        ts_last  = float(last.get("timestamp",  0))
        elapsed  = ts_last - ts_first

        if elapsed <= 0:
            return default

        # ---- VELOCITY ----
        mc_velocity     = _rate_per_hour(first.get("market_cap"), last.get("market_cap"), elapsed)
        holder_velocity = _rate_per_hour(first.get("holders"),    last.get("holders"),    elapsed)
        volume_velocity = _pct_change(first.get("volume"),        last.get("volume"))
        buy_velocity    = _rate_per_hour(first.get("buys"),        last.get("buys"),       elapsed)
        liquidity_change = _pct_change(first.get("liquidity"),    last.get("liquidity"))

        # ---- BUY/SELL RATIO ----
        # Needs 'buys' and 'sells' fields in snapshot (may be 0 if not tracked)
        last_buys  = _safe(last.get("buys",  0))
        last_sells = _safe(last.get("sells", 0))
        first_buys  = _safe(first.get("buys",  0))
        first_sells = _safe(first.get("sells", 0))

        interval_buys  = max(last_buys  - first_buys,  0.0)
        interval_sells = max(last_sells - first_sells, 0.0)
        total_txns = interval_buys + interval_sells
        buy_sell_ratio = round(interval_buys / total_txns, 4) if total_txns > 0 else 0.5

        # ---- ACCELERATION (needs ≥ 3 snapshots) ----
        mc_acceleration     = 0.0
        holder_acceleration = 0.0
        volume_acceleration = 0.0

        if len(sorted_snaps) >= 3:
            mid_idx = len(sorted_snaps) // 2
            mid     = sorted_snaps[mid_idx]

            ts_mid     = float(mid.get("timestamp", ts_first))
            elapsed_1  = ts_mid   - ts_first  # first half
            elapsed_2  = ts_last  - ts_mid    # second half

            if elapsed_1 > 0 and elapsed_2 > 0:
                # MC acceleration
                v_mc_1 = _rate_per_hour(first.get("market_cap"), mid.get("market_cap"), elapsed_1)
                v_mc_2 = _rate_per_hour(mid.get("market_cap"),  last.get("market_cap"), elapsed_2)
                mc_acceleration = round((v_mc_2 - v_mc_1) / ((elapsed / 3600.0) or 1), 4)

                # Holder acceleration
                v_h_1 = _rate_per_hour(first.get("holders"), mid.get("holders"), elapsed_1)
                v_h_2 = _rate_per_hour(mid.get("holders"),  last.get("holders"), elapsed_2)
                holder_acceleration = round((v_h_2 - v_h_1) / ((elapsed / 3600.0) or 1), 4)

                # Volume acceleration
                v_vol_1 = _pct_change(first.get("volume"), mid.get("volume"))
                v_vol_2 = _pct_change(mid.get("volume"),  last.get("volume"))
                volume_acceleration = round(v_vol_2 - v_vol_1, 4)

        return {
            "mc_velocity":          round(mc_velocity, 4),
            "holder_velocity":      round(holder_velocity, 4),
            "volume_velocity":      round(volume_velocity, 4),
            "buy_velocity":         round(buy_velocity, 4),
            "liquidity_change":     round(liquidity_change, 4),
            "mc_acceleration":      mc_acceleration,
            "holder_acceleration":  holder_acceleration,
            "volume_acceleration":  volume_acceleration,
            "buy_sell_ratio":       buy_sell_ratio,
        }

    except Exception as e:
        print(f"[INTELLIGENCE] Momentum calculation error: {e}")
        return default


# ======================================================
# MAIN COLLECTOR
# ======================================================

def collect_momentum(coin, database) -> dict:
    """Fetches snapshots and computes full momentum. Safe defaults on failure."""
    default = {
        "mc_velocity": 0.0, "holder_velocity": 0.0,
        "volume_velocity": 0.0, "buy_velocity": 0.0,
        "liquidity_change": 0.0,
        "mc_acceleration": 0.0, "holder_acceleration": 0.0,
        "volume_acceleration": 0.0, "buy_sell_ratio": 0.0,
    }

    try:
        signal_id = getattr(coin, "signal_id", None)
        if not signal_id:
            return default

        snapshots = database.get_snapshots_for_signal(signal_id)
        return calculate_momentum(snapshots)

    except Exception as e:
        symbol = getattr(coin, "symbol", "")
        print(f"[INTELLIGENCE] Momentum collection error for {symbol}: {e}")
        return default
