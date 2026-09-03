import unittest
from unittest.mock import patch, MagicMock
from trading.position import Position
from trading.trade_manager import TradeManager
import time
from datetime import datetime

class TestS6StrictExits(unittest.TestCase):
    
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_db.open_paper_trade.return_value = True
        
        self.mock_portfolio = MagicMock()
        self.mock_portfolio.cash = 1000.0
        
        self.mock_paper_trader = MagicMock()
        self.mock_paper_trader.portfolio = self.mock_portfolio
        
        self.tm = TradeManager(
            portfolio=self.mock_portfolio,
            trader=self.mock_paper_trader
        )
        self.tm.db = self.mock_db
        
        # S6 Position
        self.s6_pos = Position()
        self.s6_pos.symbol = "TEST"
        self.s6_pos.trade_id = "s6_test_1"
        self.s6_pos.strategy_id = "S6_Moonshot_Ladder"
        self.s6_pos.status = "OPEN"
        self.s6_pos.entry_price = 10.0
        self.s6_pos.current_price = 10.0
        self.s6_pos.highest_price = 10.0
        self.s6_pos.invested_amount = 100.0
        
        # Legacy Position
        self.legacy_pos = Position()
        self.legacy_pos.symbol = "LEGACY"
        self.legacy_pos.trade_id = "legacy_test_1"
        self.legacy_pos.strategy_id = "LAPC_v2"
        self.legacy_pos.status = "OPEN"
        self.legacy_pos.entry_price = 10.0
        self.legacy_pos.current_price = 10.0
        self.legacy_pos.highest_price = 10.0
        self.legacy_pos.invested_amount = 100.0

    @patch('trading.trade_manager.get_exit_decision')
    @patch('trading.trade_manager.update_market')
    def test_s6_hold_does_not_call_legacy_exit(self, mock_update, mock_legacy_exit):
        mock_update.return_value = MagicMock(price=10.5, live_market_cap=100000)
        self.s6_pos.current_price = 10.5
        self.s6_pos.highest_price = 10.5
        
        self.mock_portfolio.get_open_positions.return_value = [self.s6_pos]
        self.tm.update()
        
        # Verify action was HOLD
        self.assertEqual(self.s6_pos.exit_action, "HOLD")
        # Ensure legacy exit AI was NEVER called
        mock_legacy_exit.assert_not_called()

    @patch('trading.trade_manager.get_exit_decision')
    @patch('trading.trade_manager.update_market')
    def test_s6_cannot_produce_partial_sells(self, mock_update, mock_legacy_exit):
        # We simulate the exact conditions that would normally trigger SELL_20 or SELL_40 in legacy AI
        # e.g., 2.5x gain with dropping liquidity
        mock_update.return_value = MagicMock(price=25.0, live_market_cap=100000)
        self.s6_pos.current_price = 25.0
        self.s6_pos.highest_price = 25.0
        
        # Mock legacy exit to return a partial sell, just in case it gets called
        mock_legacy_exit.return_value = ("SELL_40", 80.0, "Heavy selling, Liquidity dropping")
        
        self.mock_portfolio.get_open_positions.return_value = [self.s6_pos]
        self.tm.update()
        
        # Since it's S6, it should be HOLD, and mock_legacy_exit shouldn't be called
        self.assertNotEqual(self.s6_pos.exit_action, "SELL_20")
        self.assertNotEqual(self.s6_pos.exit_action, "SELL_40")
        self.assertNotEqual(self.s6_pos.exit_action, "SELL_70")
        self.assertEqual(self.s6_pos.exit_action, "HOLD")
        self.assertEqual(self.s6_pos.s6_state, "MOONSHOT")
        mock_legacy_exit.assert_not_called()

    @patch('trading.trade_manager.get_exit_decision')
    @patch('trading.trade_manager.update_market')
    def test_s6_produces_sell_all_for_hard_stop(self, mock_update, mock_legacy_exit):
        mock_update.return_value = MagicMock(price=7.5, live_market_cap=100000) # Drops below 8.0 (20% stop)
        self.s6_pos.current_price = 7.5
        self.s6_pos.highest_price = 10.0
        
        self.mock_portfolio.get_open_positions.return_value = [self.s6_pos]
        self.tm.update()
        
        self.assertEqual(self.s6_pos.exit_action, "SELL_ALL")
        mock_legacy_exit.assert_not_called()

    @patch('trading.trade_manager.get_exit_decision')
    @patch('trading.trade_manager.update_market')
    def test_s6_produces_sell_all_for_moonshot_trail_break(self, mock_update, mock_legacy_exit):
        # Peak at 20.0 (2x entry -> MOONSHOT)
        self.s6_pos.highest_price = 20.0
        self.s6_pos.s6_state = 'MOONSHOT'
        self.s6_pos.s6_stop_price = 14.0 # 20.0 * 0.70
        
        # Drops to 13.5
        mock_update.return_value = MagicMock(price=13.5, live_market_cap=100000)
        self.s6_pos.current_price = 13.5
        
        self.mock_portfolio.get_open_positions.return_value = [self.s6_pos]
        self.tm.update()
        
        self.assertEqual(self.s6_pos.exit_action, "SELL_ALL")
        self.assertIn("TRAIL BREAK", self.s6_pos.exit_reason)
        mock_legacy_exit.assert_not_called()

    @patch('trading.trade_manager.get_exit_decision')
    @patch('trading.trade_manager.update_market')
    def test_non_s6_retains_legacy_behavior(self, mock_update, mock_legacy_exit):
        mock_update.return_value = MagicMock(price=15.0, live_market_cap=100000)
        self.legacy_pos.current_price = 15.0
        self.legacy_pos.highest_price = 15.0
        
        # Legacy AI returns SELL_40
        mock_legacy_exit.return_value = ("SELL_40", 85.0, "Excellent profit, Volume decreasing")
        
        self.mock_portfolio.get_open_positions.return_value = [self.legacy_pos]
        self.tm.update()
        
        self.assertEqual(self.legacy_pos.exit_action, "SELL_40")
        mock_legacy_exit.assert_called_once_with(self.legacy_pos)

if __name__ == '__main__':
    unittest.main()
