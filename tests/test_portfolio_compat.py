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

# Define ExecutionState fallback locally for test setup
try:
    from ai_engine.execution_recheck import ExecutionState
except ImportError:
    from dataclasses import dataclass
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
        mc_multiple_from_signal: float | None
        signal_age_seconds: float | None

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
        self.price = 1.0
        self.volume_5m = 10000.0

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

    @patch('ai_engine.s6_execution.recheck_market')
    def test_4_s6_execution_recheck_and_amount(self, mock_recheck_market):
        """Test 4 & 5: Mock S6 execution returns S6ProductionEntry with positive amount and no equity errors."""
        import time
        now = time.time()
        
        # Return a valid ExecutionState object populated with deterministic values
        mock_recheck_market.return_value = ExecutionState(
            checked_at=now,
            market_cap=50000.0,
            price=1.0,
            liquidity=25000.0,
            volume_5m=10000.0,
            buys_5m=50,
            sells_5m=30,
            signal_market_cap=40000.0,
            mc_multiple_from_signal=1.25,
            signal_age_seconds=60.0
        )
        
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        portfolio = Portfolio()
        coin = MockCoin()
        
        # Populate Coin execution state attributes expected by S6 sizing mapper
        coin.execution_market_cap = 50000.0
        coin.execution_price = 1.0
        coin.execution_liquidity = 25000.0
        coin.execution_volume_5m = 10000.0
        coin.execution_buys_5m = 50
        coin.execution_sells_5m = 30
        coin.signal_to_execution_seconds = 60.0
        coin.execution_mc_multiple = 1.25
        
        # Run execution
        result = evaluate_s6_production_entry(coin, portfolio)
        
        # Assert type/attributes matching S6ProductionEntry requirements
        self.assertEqual(result.__class__.__name__, "S6ProductionEntry")
        self.assertTrue(result.eligible)
        self.assertIsNotNone(result.decision)
        self.assertGreater(result.decision.amount, 0.0)
        self.assertNotIn("Invalid portfolio equity", result.reason)
        
        print(f"\n[TEST RESULT] Mock S6 allocation amount: ${result.decision.amount:.2f}")

if __name__ == '__main__':
    unittest.main()
