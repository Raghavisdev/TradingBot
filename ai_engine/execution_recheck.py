from __future__ import annotations

import time
from dataclasses import dataclass

from collectors.live_market import update_market


@dataclass(frozen=True)
class ExecutionState:
    checked_at: float
    market_cap: float
    price: float
    liquidity: float
    volume_5m: float
    buys_5m: int
    sells_5m: int
    signal_market_cap: float | None
    signal_price: float | None
    mc_multiple_from_signal: float | None
    price_multiple_from_signal: float | None
    signal_age_seconds: float | None


def recheck_market(coin) -> ExecutionState | None:
    """
    Refresh live market data and return a frozen ExecutionState snapshot.
    Returns None if the API call fails.
    """
    update_market(coin, force_refresh=True)

    if not getattr(coin, "last_api_success", False):
        return None

    market_cap = float(getattr(coin, "live_market_cap", 0) or 0)
    price      = float(getattr(coin, "price", 0) or 0)
    liquidity  = float(getattr(coin, "liquidity", 0) or 0)
    volume_5m  = float(getattr(coin, "volume_5m", 0) or 0)
    buys_5m    = int(getattr(coin, "buys_5m", 0) or 0)
    sells_5m   = int(getattr(coin, "sells_5m", 0) or 0)

    # Signal market cap and price
    signal_mc_raw = getattr(coin, "signal_market_cap", None)
    signal_mc     = float(signal_mc_raw) if signal_mc_raw else 0.0

    signal_price_raw = getattr(coin, "signal_price", None)
    signal_price     = float(signal_price_raw) if signal_price_raw else 0.0

    # Signal age in seconds
    signal_time_raw = getattr(coin, "signal_time", None)
    signal_age      = 0.0
    if signal_time_raw:
        try:
            from datetime import datetime
            signal_dt  = datetime.fromisoformat(str(signal_time_raw))
            now        = time.time()
            signal_age = max(0.0, now - signal_dt.timestamp())
        except (TypeError, ValueError, OSError):
            signal_age = 0.0

    mc_multiple = (
        float(market_cap) / float(signal_mc)
        if signal_mc and signal_mc > 0
        else 0.0
    )

    price_multiple = (
        float(price) / float(signal_price)
        if signal_price and signal_price > 0
        else 0.0
    )

    # Write back to coin so downstream code sees fresh values
    coin.execution_rechecked_at  = time.time()
    coin.execution_market_cap    = market_cap
    coin.execution_price         = price
    coin.execution_liquidity     = liquidity
    coin.execution_volume_5m     = volume_5m
    coin.execution_buys_5m       = buys_5m
    coin.execution_sells_5m      = sells_5m
    coin.signal_to_execution_seconds = signal_age
    coin.execution_mc_multiple   = mc_multiple
    coin.execution_price_multiple = price_multiple

    return ExecutionState(
        checked_at=time.time(),
        market_cap=market_cap,
        price=price,
        liquidity=liquidity,
        volume_5m=volume_5m,
        buys_5m=buys_5m,
        sells_5m=sells_5m,
        signal_market_cap=signal_mc if signal_mc > 0 else None,
        signal_price=signal_price if signal_price > 0 else None,
        mc_multiple_from_signal=mc_multiple if mc_multiple > 0 else None,
        price_multiple_from_signal=price_multiple if price_multiple > 0 else None,
        signal_age_seconds=signal_age if signal_age > 0 else None,
    )
