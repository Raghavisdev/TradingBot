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
    # Note: Enforce 62+ in execution evaluator; production entry acts as gateway
    if final_score < 60.0:
        return S6ProductionEntry(eligible=False, decision=None, reason=f"Final score {final_score:.1f} < 60.0")
        
    decision = evaluate_s6_execution(coin, portfolio)
    
    if not decision or not getattr(decision, "amount", 0):
        print("[S6 RESULT] Execution market refresh failed or rejected")
        reason = decision.reason if decision else "Execution market refresh failed"
        return S6ProductionEntry(eligible=False, decision=decision, reason=reason)
        
    print(f"[S6 RESULT] eligible=True decision={decision.amount}")
    return S6ProductionEntry(eligible=True, decision=decision, reason=decision.reason)
