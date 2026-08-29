import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from trading.portfolio import Portfolio
from trading.position import Position
from ai_engine.s6_production_entry import evaluate_s6_production_entry

class MockCoin:
    def __init__(self):
        self.signal_id = "test_s6_signal"
        self.symbol = "MOCK_S6"
        self.contract = "MockContractAddress"
        self.final_score = 63.0
        self.gt_score = 1
        self.valid = True
        self.liquidity = 20000.0
        self.signal_market_cap = 40000.0
        self.buys_5m = 50
        self.sells_5m = 50

class TestPortfolioCompat(unittest.TestCase):
    
    def test_1_fresh_portfolio(self):
        """Test 1: Fresh Portfolio with $500 balance has matching equity, cash, and balance."""
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        portfolio = Portfolio()
        
        self.assertEqual(portfolio.initial_balance, 500.0)
        self.assertEqual(portfolio.total_equity, 500.0)
        self.assertEqual(portfolio.initial_cash, 500.0)
        self.assertEqual(portfolio.cash, 500.0)
        self.assertEqual(portfolio._peak_equity, 500.0)

    def test_2_simulated_pnl_change(self):
        """Test 2: After simulated position / P&L changes, total_equity reflects the updated value."""
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        portfolio = Portfolio()
        
        # Open a simulated position
        pos = Position()
        pos.invested_amount = 100.0
        pos.entry_price = 1.0
        pos.current_price = 1.0
        pos.status = "OPEN"
        pos.tokens = 100.0
        
        portfolio.cash -= 100.0
        portfolio.add_position(pos)
        
        # Verify initial state after entry
        self.assertEqual(portfolio.portfolio_value(), 500.0)
        self.assertEqual(portfolio.total_equity, 500.0)
        
        # Simulate P&L change (+50% price increase)
        pos.current_price = 1.50
        pos.pnl_dollars = 50.0
        
        # total_equity should reflect the $50 gain
        self.assertEqual(portfolio.portfolio_value(), 550.0)
        self.assertEqual(portfolio.total_equity, 550.0)

    def test_3_peak_equity_tracking(self):
        """Test 3: Peak equity tracking increases on new high and remains unchanged during a drawdown."""
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        portfolio = Portfolio()
        
        self.assertEqual(portfolio._peak_equity, 500.0)
        
        # 1. New high (simulate profit)
        pos = Position()
        pos.invested_amount = 100.0
        pos.entry_price = 1.0
        pos.current_price = 1.5
        pos.pnl_dollars = 50.0
        pos.status = "OPEN"
        
        portfolio.cash -= 100.0
        portfolio.add_position(pos)  # calls update_peak_equity()
        
        # Verify peak increased to 550
        self.assertEqual(portfolio.portfolio_value(), 550.0)
        self.assertEqual(portfolio._peak_equity, 550.0)
        
        # 2. Drawdown (simulate price crash)
        pos.current_price = 0.50
        pos.pnl_dollars = -50.0
        
        # Value drops to 450, but peak remains 550
        self.assertEqual(portfolio.portfolio_value(), 450.0)
        portfolio.update_peak_equity()
        self.assertEqual(portfolio._peak_equity, 550.0)

    @patch('requests.get')
    @patch('collectors.live_market._fetch_dexscreener')
    @patch('collectors.live_market.update_market')
    @patch('collectors.dexscreener.update_dex_data')
    @patch('ai_engine.execution_recheck.check_execution', create=True)
    def test_4_s6_execution_recheck_and_amount(self, mock_check_exec, mock_update_dex, mock_update_market, mock_fetch_dex, mock_requests_get):
        """Test 4 & 5: Mock S6 execution returns S6ProductionEntry with positive amount and no equity errors."""
        mock_check_exec.return_value = True
        mock_update_dex.return_value = True
        mock_update_market.return_value = True
        
        # Mock requests.get to return a valid pair
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pairs": [{
                "priceUsd": "1.0",
                "liquidity": {"usd": 50000.0},
                "volume": {"h24": 100000.0},
                "fdv": 1000000.0
            }]
        }
        mock_requests_get.return_value = mock_resp
        mock_fetch_dex.return_value = mock_resp.json.return_value
        
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        portfolio = Portfolio()
        coin = MockCoin()
        
        # Run execution
        result = evaluate_s6_production_entry(coin, portfolio)
        
        # Assert type matches S6ProductionEntry
        self.assertEqual(result.__class__.__name__, "S6ProductionEntry")
        
        # Assertions required by the prompt
        self.assertTrue(result.eligible)
        self.assertIsNotNone(result.decision)
        self.assertGreater(result.decision.amount, 0.0)
        self.assertNotIn("Invalid portfolio equity", result.reason)
        
        print(f"\n[TEST RESULT] Mock S6 allocation amount: ${result.decision.amount:.2f}")

if __name__ == '__main__':
    unittest.main()
