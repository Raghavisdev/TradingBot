import unittest
import os
import sys

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

    def test_4_s6_execution_recheck_and_amount(self):
        """Test 4 & 5: S6 execution no longer fails with 'Invalid portfolio equity' and returns amount > 0."""
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        portfolio = Portfolio()
        coin = MockCoin()
        
        # Run execution
        amount, reason = evaluate_s6_production_entry(coin, portfolio)
        
        # Confirm no 'Invalid portfolio equity' reason
        self.assertNotEqual(reason, "Invalid portfolio equity")
        self.assertEqual(reason, "Success")
        
        # Confirm returned amount is > 0
        self.assertGreater(amount, 0.0)
        print(f"\n[TEST RESULT] Mock S6 allocation amount: ${amount:.2f}")

if __name__ == '__main__':
    unittest.main()
