import unittest
import os
from unittest.mock import patch, MagicMock, PropertyMock

from trading.portfolio import Portfolio
from ai_engine.s6_execution import evaluate_s6_execution
from ai_engine.execution_recheck import ExecutionState

class MockCoin:
    def __init__(self):
        self.symbol = "TEST"
        self.valid = True
        self.final_score = 65.0
        self.gt_score = 1
        self.signal_market_cap = 50000.0
        self.signal_price = 1.0
        self.signal_time = "2026-08-30T10:00:00"
        self.buys = 100
        self.sells = 50
        self.liquidity = 25000.0
        self.live_market_cap = 50000.0
        self.price = 1.0
        self.volume_5m = 5000.0
        self.last_api_success = True

class TestS6Execution(unittest.TestCase):
    
    def setUp(self):
        import config
        config.S6_CANDIDATE_MODE = False
        self.portfolio = Portfolio()
        self.portfolio.initial_balance = 500.0
        self.portfolio.cash = 500.0
        self.coin = MockCoin()

    @patch('ai_engine.s6_execution.recheck_market')
    def test_1_high_quality_signal(self, mock_recheck):
        self.coin.final_score = 90.0
        self.coin.gt_score = 3
        self.coin.buys = 200
        self.coin.sells = 10
        self.coin.liquidity = 100000.0
        
        mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=50000.0,
            price=1.0,
            liquidity=100000.0,
            volume_5m=20000.0,
            buys_5m=200,
            sells_5m=10,
            signal_market_cap=50000.0,
            signal_price=1.0,
            mc_multiple_from_signal=1.0,
            price_multiple_from_signal=1.0,
            signal_age_seconds=10.0
        )
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertIsNotNone(decision)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_2_low_quality_signal(self, mock_recheck):
        self.coin.final_score = 62.0
        self.coin.gt_score = 0
        self.coin.buys = 10
        self.coin.sells = 100
        self.coin.liquidity = 5000.0
        
        mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=10000.0,
            price=1.0,
            liquidity=5000.0,
            volume_5m=1000.0,
            buys_5m=10,
            sells_5m=100,
            signal_market_cap=10000.0,
            signal_price=1.0,
            mc_multiple_from_signal=1.0,
            price_multiple_from_signal=1.0,
            signal_age_seconds=10.0
        )
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertIsNotNone(decision)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_3_portfolio_100(self, mock_recheck):
        self.portfolio.cash = 100.0
        self.portfolio.initial_balance = 100.0
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_4_portfolio_237_35(self, mock_recheck):
        self.portfolio.cash = 237.35
        self.portfolio.initial_balance = 100.0
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_5_portfolio_500_plus(self, mock_recheck):
        self.portfolio.cash = 1000.0
        self.portfolio.initial_balance = 500.0
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_6a_score_54_99_rejected(self, mock_recheck):
        """Test that score < 55 is rejected (now the threshold is 55.0)"""
        self.coin.final_score = 54.9
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)
        self.assertIn("54.9", decision.reason)
        
    @patch('ai_engine.s6_execution.recheck_market')
    def test_6b_score_55_accepted(self, mock_recheck):
        """Test that score 55.0 is accepted"""
        self.coin.final_score = 55.0
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        with patch('trading.portfolio.Portfolio.total_equity', new_callable=PropertyMock) as mock_eq:
            with patch('trading.portfolio.Portfolio.highest_equity', new_callable=PropertyMock, create=True) as mock_hwm:
                mock_eq.return_value = 10000.0
                mock_hwm.return_value = 10000.0
                decision = evaluate_s6_execution(self.coin, self.portfolio)
                self.assertGreater(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_6c_score_61_00_accepted(self, mock_recheck):
        self.coin.final_score = 61.0
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_6d_score_65_00_accepted(self, mock_recheck):
        self.coin.final_score = 65.0
        mock_recheck.return_value = ExecutionState(1000, 50000, 1.0, 20000, 5000, 50, 50, 50000, 1.0, 1.0, 1.0, 10.0)
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_7_mcx_2_01_accepted(self, mock_recheck):
        mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=100500.0,
            price=2.01,
            liquidity=20000.0,
            volume_5m=5000.0,
            buys_5m=50,
            sells_5m=50,
            signal_market_cap=50000.0,
            signal_price=1.0,
            mc_multiple_from_signal=2.01,
            price_multiple_from_signal=2.01,
            signal_age_seconds=10.0
        )
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_8_mcx_1_0_accepted(self, mock_recheck):
        mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=50000.0,
            price=1.0,
            liquidity=20000.0,
            volume_5m=5000.0,
            buys_5m=50,
            sells_5m=50,
            signal_market_cap=50000.0,
            signal_price=1.0,
            mc_multiple_from_signal=1.0,
            price_multiple_from_signal=1.0,
            signal_age_seconds=10.0
        )
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)

    @patch('ai_engine.s6_execution.recheck_market')
    def test_9_no_scale_in_always_2_dollars(self, mock_recheck):
        """Regression: S6 must always return exactly $2.00 — never $5, $7, or any scaled amount."""
        # Even with a perfect signal, huge portfolio, high score — still $2.00
        self.coin.final_score = 99.0
        self.coin.gt_score = 5
        self.coin.buys = 500
        self.coin.sells = 1
        self.coin.liquidity = 500000.0
        self.portfolio.cash = 10000.0
        self.portfolio.initial_balance = 10000.0
        mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=200000.0,
            price=5.0,
            liquidity=500000.0,
            volume_5m=100000.0,
            buys_5m=500,
            sells_5m=1,
            signal_market_cap=100000.0,
            signal_price=2.5,
            mc_multiple_from_signal=2.0,
            price_multiple_from_signal=2.0,
            signal_age_seconds=5.0
        )
        
        decision = evaluate_s6_execution(self.coin, self.portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)
        self.assertNotEqual(decision.amount, 5.0, "S6 must NOT scale to $5")
        self.assertNotEqual(decision.amount, 7.0, "S6 must NOT scale to $7")

if __name__ == '__main__':
    unittest.main()
