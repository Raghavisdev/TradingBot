import unittest
from unittest.mock import MagicMock, patch

from ai_engine.s6_execution import evaluate_s6_execution
from ai_engine.execution_recheck import ExecutionState

class DummyCoin:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "symbol"):
            self.symbol = "TEST"

class DummyPortfolio:
    total_equity = 100.0

class TestS6MomentumGate(unittest.TestCase):

    def setUp(self):
        self.portfolio = DummyPortfolio()

    @patch("ai_engine.s6_execution.recheck_market")
    def test_score_below_65_rejected(self, mock_recheck):
        coin = DummyCoin(final_score=64.9, gt_score=2)
        state = ExecutionState(
            checked_at=123.0, market_cap=50000, price=1.0,
            liquidity=2000, volume_5m=0, buys_5m=0, sells_5m=0,
            signal_market_cap=50000, mc_multiple_from_signal=1.0,
            signal_age_seconds=25.0
        )
        mock_recheck.return_value = state
        
        decision = evaluate_s6_execution(coin, self.portfolio)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.amount, 0.0)
        self.assertIn("Final score 64.9 < 65.0", decision.reason)

    @patch("ai_engine.s6_execution.recheck_market")
    def test_liquidity_below_1000_rejected(self, mock_recheck):
        coin = DummyCoin(final_score=75.0, gt_score=2)
        state = ExecutionState(
            checked_at=123.0, market_cap=50000, price=1.0,
            liquidity=999.0, volume_5m=0, buys_5m=0, sells_5m=0,
            signal_market_cap=50000, mc_multiple_from_signal=1.0,
            signal_age_seconds=25.0
        )
        mock_recheck.return_value = state
        
        decision = evaluate_s6_execution(coin, self.portfolio)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.amount, 0.0)
        self.assertIn("Liquidity 999 < 1000", decision.reason)

    @patch("ai_engine.s6_execution.recheck_market")
    def test_momentum_decay_rejected(self, mock_recheck):
        coin = DummyCoin(final_score=75.0, gt_score=2)
        # Price dropped 6% during 25s latency (0.94x)
        state = ExecutionState(
            checked_at=123.0, market_cap=47000, price=0.94,
            liquidity=2000.0, volume_5m=0, buys_5m=0, sells_5m=0,
            signal_market_cap=50000, mc_multiple_from_signal=0.94,
            signal_age_seconds=25.0
        )
        mock_recheck.return_value = state
        
        decision = evaluate_s6_execution(coin, self.portfolio)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.amount, 0.0)
        self.assertIn("Momentum decay: MCx 0.940 < 0.95", decision.reason)

    @patch("ai_engine.s6_execution.recheck_market")
    def test_valid_entry_gets_exact_2_dollars(self, mock_recheck):
        coin = DummyCoin(final_score=85.0, gt_score=2)
        # Price rose 5% during latency (1.05x), liq > 1000
        state = ExecutionState(
            checked_at=123.0, market_cap=52500, price=1.05,
            liquidity=5000.0, volume_5m=0, buys_5m=0, sells_5m=0,
            signal_market_cap=50000, mc_multiple_from_signal=1.05,
            signal_age_seconds=25.0
        )
        mock_recheck.return_value = state
        
        decision = evaluate_s6_execution(coin, self.portfolio)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.amount, 2.0)
        self.assertIn("S6 execution approved", decision.reason)

if __name__ == '__main__':
    unittest.main()
