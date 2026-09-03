import unittest
import os
from unittest.mock import patch, MagicMock
import config
from ai_engine.s6_execution import evaluate_s6_execution

class TestS6CandidateSizing(unittest.TestCase):
    
    def setUp(self):
        self.mock_coin = MagicMock()
        self.mock_coin.symbol = "TEST"
        self.mock_coin.valid = True
        self.mock_coin.final_score = 65.0
        self.mock_coin.price = 0.01
        
        self.mock_portfolio = MagicMock()
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.cash = 100.0
        self.mock_portfolio.roi.return_value = 0.0
        self.mock_portfolio.get_open_positions.return_value = []
        
        self.mock_state = MagicMock()
        self.mock_state.market_cap = 100000
        self.mock_state.liquidity = 10000
        self.mock_state.signal_market_cap = 100000
        self.mock_state.mc_multiple_from_signal = 1.0
        
    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_base_sizing(self, mock_recheck):
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.highest_equity = 100.0
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertIsNotNone(decision)
        self.assertAlmostEqual(decision.amount, 3.508, places=2) # 100 * 3.508%

    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_liquidity_cap(self, mock_recheck):
        self.mock_state.liquidity = 150 # 2% is 3.0
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.highest_equity = 100.0
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertEqual(decision.amount, 3.0)
        
    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_portfolio_exposure_cap(self, mock_recheck):
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.highest_equity = 100.0
        
        mock_pos = MagicMock()
        mock_pos.invested_amount = 47.0
        mock_pos.strategy_id = "S6_Moonshot_Ladder"
        self.mock_portfolio.get_open_positions.return_value = [mock_pos]
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertEqual(decision.amount, 3.0) # 50 - 47 = 3.0 available
        
    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_min_trade(self, mock_recheck):
        self.mock_state.liquidity = 50 # 2% is 1.0
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.highest_equity = 100.0
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertEqual(decision.amount, 1.0)
        
    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_cash_reserve(self, mock_recheck):
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.highest_equity = 100.0
        self.mock_portfolio.cash = 13.0
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertGreaterEqual(decision.amount, 0.0) # 13 - 3.508 = 9.492 < 10
        self.assertIn("Insufficient reserve", decision.reason)
        
    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_drawdown_breaker(self, mock_recheck):
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 80.0
        self.mock_portfolio.highest_equity = 100.0 # 20% drawdown
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)
        self.assertIn("Portfolio DD 20.0%", decision.reason)

    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_conditional_edge_negative(self, mock_recheck):
        self.mock_coin.final_score = 75.0 # p_win = 0.167 => negative edge
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 100.0
        self.mock_portfolio.highest_equity = 100.0
        
        decision = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        self.assertGreaterEqual(decision.amount, 0.0)
        self.assertIn("Expected net edge <= 0", decision.reason)

    @patch('ai_engine.s6_execution.recheck_market')
    @patch('config.S6_CANDIDATE_MODE', False)
    def test_conditional_sizing_separation(self, mock_recheck):
        mock_recheck.return_value = self.mock_state
        self.mock_portfolio.total_equity = 1000.0
        self.mock_portfolio.highest_equity = 1000.0
        
        # We use a large equity ($1000) so amounts don't get clamped to the 1% ($10) minimum.
        # Actually 1% of 1000 is 10.0, 5% is 50.0. 
        # But wait, max amount is capped at 15.0 by `amount = min(amount, 15.0)`!
        # So we should use total_equity = 400.0 so 5% is 20.0, min 1% is 4.0.
        self.mock_portfolio.total_equity = 400.0
        self.mock_portfolio.highest_equity = 400.0
        
        # Score 55 -> p_win 0.324 -> net_edge 0.1888 -> kelly_frac 0.1888 -> 0.01888 pct
        self.mock_coin.final_score = 55.0
        decision_55 = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        
        # Score 65 -> p_win 0.459 -> net_edge 0.3508 -> kelly_frac 0.3508 -> 0.03508 pct
        self.mock_coin.final_score = 65.0
        decision_65 = evaluate_s6_execution(self.mock_coin, self.mock_portfolio)
        
        self.assertGreater(decision_65.amount, decision_55.amount)
        self.assertAlmostEqual(decision_55.amount, 400.0 * 0.01888, places=1)
        self.assertAlmostEqual(decision_65.amount, 400.0 * 0.03508, places=1)

if __name__ == '__main__':
    unittest.main()
