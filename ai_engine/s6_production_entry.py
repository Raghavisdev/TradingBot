from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_engine.s6_execution import S6ExecutionDecision, evaluate_s6_execution


@dataclass(frozen=True)
class S6ProductionEntry:
    eligible: bool
    decision: S6ExecutionDecision | None
    reason: str


def evaluate_s6_production_entry(coin: Any, portfolio: Any) -> S6ProductionEntry:
    print(f"[S6 ENTRY] called: {getattr(coin, 'symbol', '?')} final_score={getattr(coin, 'final_score', 0)}")
    
    if not getattr(coin, "valid", True):
        return S6ProductionEntry(eligible=False, decision=None, reason="Signal invalid")
        
    if not getattr(coin, "symbol", None):
        return S6ProductionEntry(eligible=False, decision=None, reason="Missing symbol")
        
    final_score = float(getattr(coin, "final_score", 0.0))
    # Note: Enforce 55+ in execution evaluator; production entry acts as gateway
    if final_score < 55.0:
        return S6ProductionEntry(eligible=False, decision=None, reason=f"Final score {final_score:.1f} < 55.0")
        
    decision = evaluate_s6_execution(coin, portfolio)
    
    if not decision or not getattr(decision, "amount", 0):
        print("[S6 RESULT] Execution market refresh failed or rejected")
        reason = decision.reason if decision else "Execution market refresh failed"
        final_decision = S6ProductionEntry(eligible=False, decision=decision, reason=reason)
    else:
        print(f"[S6 RESULT] eligible=True decision={decision.amount}")
        final_decision = S6ProductionEntry(eligible=True, decision=decision, reason=decision.reason)

    # ----------------------------------------------------
    # FORWARD PAPER RESEARCH LEDGER TELEMETRY
    # ----------------------------------------------------
    import time
    import json
    from analytics.paper_lab.persistence import PaperLabPersistence
    try:
        requested_amount = 4.0 # Base candidate amount
        sig_dict = {
            "signal_id": getattr(coin, "signal_id", None),
            "timestamp": int(time.time()),
            "symbol": getattr(coin, "symbol", "UNKNOWN"),
            "contract": getattr(coin, "contract", "UNKNOWN"),
            "final_score": float(getattr(coin, "final_score", 0.0)),
            "gt_score": float(getattr(coin, "gt_score", 0.0)),
            "liquidity": float(getattr(coin, "liquidity", 0.0) or getattr(decision.execution_state, "liquidity", 0.0) if decision and getattr(decision, "execution_state", None) else 0.0),
            "buys": int(getattr(coin, "buys", 0)),
            "sells": int(getattr(coin, "sells", 0)),
            "effective_entry_mc": float(getattr(coin, "signal_market_cap", 0.0)),
            "current_price": float(getattr(coin, "price", 0.0) or getattr(decision.execution_state, "price", 0.0) if decision and getattr(decision, "execution_state", None) else 0.0),
            "portfolio_equity_before": float(getattr(portfolio, "total_equity", 0.0)),
            "cash_before": float(getattr(portfolio, "cash", 0.0)),
            "active_s6_exposure": float(sum(getattr(p, "invested_amount", 0.0) for p in getattr(portfolio, "get_open_positions", lambda: [])() if getattr(p, "strategy_id", "default").startswith("S6"))),
            "requested_amount": float(getattr(decision, "telemetry", {}).get("calculated_size", 0.0) if decision else 0.0),
            "final_amount": float(decision.amount if decision else 0.0),
            "all_sizing_inputs": json.dumps(decision.telemetry) if decision and hasattr(decision, "telemetry") else "{}",
            "sizing_formula_version": "production_live_v1.3_conditional_fractional_kelly",
            "experiment_id": "FORWARD_TEST_01",
            "strategy_id": "S6_Moonshot_Ladder"
        }
        PaperLabPersistence().save_forward_signal(sig_dict)
    except Exception as e:
        print(f"[FORWARD LEDGER ERROR] Failed to save live signal: {e}")

    return final_decision
