from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_engine.execution_recheck import ExecutionState, recheck_market
from ai_engine.s6_core import (
    S6_MIN_FINAL_SCORE,
    compute_entry_quality,
    s6_base_size,
    s6_buy_sell_multiplier,
)


@dataclass(frozen=True)
class S6ExecutionDecision:
    amount: float
    quality: float
    execution_state: ExecutionState | None
    reason: str


def _coin_to_execution_signal(coin: Any) -> dict[str, Any]:
    return {
        "signal_id": getattr(coin, "signal_id", None),
        "valid": getattr(coin, "valid", True),
        "symbol": getattr(coin, "symbol", None),
        "signal_market_cap": getattr(coin, "execution_market_cap", None),
        "signal_price": getattr(coin, "execution_price", None),
        "liquidity": getattr(coin, "execution_liquidity", None),
        "buys": getattr(coin, "execution_buys_5m", None),
        "sells": getattr(coin, "execution_sells_5m", None),
        "gt_score": getattr(coin, "gt_score", 0),
        "final_score": getattr(coin, "final_score", 0),
    }


def evaluate_s6_execution(coin: Any, portfolio: Any) -> S6ExecutionDecision | None:
    # 1. Fetch live market data at execution time
    state = recheck_market(coin)
    if not state:
        return S6ExecutionDecision(
            amount=0.0,
            quality=0.0,
            execution_state=None,
            reason="Signal invalid at execution recheck"
        )
    
    # Check symbol validity
    symbol = getattr(coin, "symbol", None)
    if not symbol:
        return S6ExecutionDecision(
            amount=0.0,
            quality=0.0,
            execution_state=state,
            reason="Missing symbol"
        )

    # 2. Check Score Eligibility
    final_score = getattr(coin, "final_score", 0)
    # LAPC-v2 rule: final_score >= 62
    if float(final_score) < 62.0:
        return S6ExecutionDecision(
            amount=0.0,
            quality=0.0,
            execution_state=state,
            reason=f"Final score {final_score:.1f} < 62.0"
        )
        
    # LAPC-v2 rule: MCx <= 2.0
    if state.mc_multiple_from_signal is not None and state.mc_multiple_from_signal > 2.0:
        return S6ExecutionDecision(
            amount=0.0,
            quality=0.0,
            execution_state=state,
            reason=f"MCx {state.mc_multiple_from_signal:.2f} > 2.0"
        )

    # Check Portfolio Equity bounds
    total_equity = float(getattr(portfolio, "total_equity", 0))
    if total_equity <= 0:
        return S6ExecutionDecision(
            amount=0.0,
            quality=0.0,
            execution_state=state,
            reason="Invalid portfolio equity"
        )

    # 3. Compute telemetry/logging variables
    evaluation_signal = _coin_to_execution_signal(coin)
    quality = compute_entry_quality(evaluation_signal)
    
    # We compute these for telemetry but do NOT use them for scaling
    base_size = s6_base_size(quality)
    multiplier = s6_buy_sell_multiplier(evaluation_signal)
    
    # ========================================================
    # LAPC-V2 SIZING FIX
    # Exact $2 probe size for all valid S6 entries
    # Removed equity scaling, DD factors, and floor/cap logic
    # ========================================================
    amount = 2.0

    reason = f"S6 execution approved: Q={quality:.3f}, MC=${state.market_cap:,.0f}, liq=${state.liquidity:,.0f}, size=${amount:.2f}"
    
    if state.signal_market_cap:
        reason += f", signal_MC=${state.signal_market_cap:,.0f}"
        
    if state.mc_multiple_from_signal:
        reason += f", MCx={state.mc_multiple_from_signal:.3f}"

    return S6ExecutionDecision(
        amount=amount,
        quality=quality,
        execution_state=state,
        reason=reason
    )
