import unittest
import os
import sys
from unittest.mock import patch, MagicMock
import sys
sys.modules['solders'] = MagicMock()
sys.modules['solders.transaction'] = MagicMock()
sys.modules['solders.keypair'] = MagicMock()

from engine.pipeline import process_message
from trading.portfolio import Portfolio
from ai_engine.execution_recheck import ExecutionState
import database

class TestPipelineS6E2E(unittest.TestCase):
    def setUp(self):
        # We need to mock the entire portfolio since process_message loads it from db/env
        self.patcher_portfolio = patch('engine.pipeline.Portfolio')
        self.mock_portfolio_class = self.patcher_portfolio.start()
        self.mock_portfolio = MagicMock(spec=Portfolio)
        self.mock_portfolio.cash = 237.35
        self.mock_portfolio.initial_balance = 100.0
        self.mock_portfolio.total_equity = 237.35
        self.mock_portfolio.can_open_trade.return_value = True
        self.mock_portfolio.has_position.return_value = False
        self.mock_portfolio.get_open_positions.return_value = []
        
        self.mock_portfolio_class.return_value = self.mock_portfolio
        
        # Mock network/API calls
        self.patcher_collect = patch('engine.pipeline.collect_all')
        self.mock_collect = self.patcher_collect.start()
        
        self.patcher_gemtools = patch('engine.pipeline.analyze_gemtools')
        self.mock_gemtools = self.patcher_gemtools.start()
        
        self.patcher_fundamentals = patch('engine.pipeline.analyze_fundamentals')
        self.mock_fundamentals = self.patcher_fundamentals.start()

        # Mock parse_signal since it expects raw text
        self.patcher_parse = patch('engine.pipeline.parse_signal')
        self.mock_parse = self.patcher_parse.start()

        self.patcher_db_create = patch('engine.pipeline.database.create_signal')
        self.mock_db_create = self.patcher_db_create.start()
        
        self.patcher_db_update = patch('engine.pipeline.database.update_signal')
        self.mock_db_update = self.patcher_db_update.start()
        
        self.patcher_tracker = patch('engine.pipeline.tracker_manager.start_tracking')
        self.mock_tracker = self.patcher_tracker.start()

        # Mock make_decision so we can control final_score easily without running the ML model
        self.patcher_decision = patch('engine.pipeline.make_decision')
        self.mock_decision = self.patcher_decision.start()

        # Mock execution market recheck which hits live API
        self.patcher_recheck = patch('ai_engine.s6_execution.recheck_market')
        self.mock_recheck = self.patcher_recheck.start()

    def tearDown(self):
        self.patcher_portfolio.stop()
        self.patcher_collect.stop()
        self.patcher_gemtools.stop()
        self.patcher_fundamentals.stop()
        self.patcher_parse.stop()
        self.patcher_decision.stop()
        self.patcher_db_create.stop()
        self.patcher_db_update.stop()
        self.patcher_tracker.stop()
        self.patcher_recheck.stop()

    @patch('engine.pipeline.PaperTrader')
    def test_pipeline_e2e_valid_s6(self, mock_paper_trader_class):
        # 1. Valid high-score signal with MCx = 1.0
        message = {"token": "E2ETEST1", "contract": "E2ETEST1CONTRACT", "market_cap": 50000.0}
        
        class DummyCoin: 
            contract = 'DUMMY'
            decision = 'BUY'
            buy_blocked_by = None
            symbol = 'TEST'
        coin_obj = DummyCoin()
        self.mock_parse.return_value = coin_obj
        
        def mock_decision_effect(coin):
            coin.final_score = 65.0
            coin.decision = "BUY"
            coin.strategy_id = "S6_Moonshot_Ladder"
            coin.signal_market_cap = 50000.0
            coin.valid = True
            return coin
        
        self.mock_collect.side_effect = lambda c: c
        self.mock_gemtools.side_effect = lambda c: c
        self.mock_fundamentals.side_effect = lambda c: c
        self.mock_decision.side_effect = mock_decision_effect

        self.mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=50000.0,
            price=1.0,
            liquidity=20000.0,
            volume_5m=5000.0,
            buys_5m=50,
            sells_5m=50,
            signal_market_cap=50000.0,
            mc_multiple_from_signal=1.0,
            signal_age_seconds=10.0
        )

        with patch.dict(os.environ, {"S6_Moonshot_VNext_MODE": "SHADOW", "LIVE_TRADING": "False"}):
            coin = process_message(message)
            
        # Verify it went through successfully and wasn't blocked by Position Sizer
        self.assertTrue(getattr(coin, 'buy_blocked_by', None) is None or "Position Sizer" not in getattr(coin, 'buy_blocked_by', ''))
        
    @patch('engine.pipeline.trader')
    def test_pipeline_amount_passed_to_execution(self, mock_trader):
        mock_paper = mock_trader
        mock_paper.buy.return_value.entry_price = 1.0
        mock_paper.buy.return_value.entry_market_cap = 50000.0
        message = {"token": "E2ETEST_SUCCESS", "contract": "SUCCESS_CONTRACT", "market_cap": 50000.0}
        class DummyCoin: 
            contract = 'DUMMY'
            decision = 'BUY'
            buy_blocked_by = None
            symbol = 'TEST'
        self.mock_parse.return_value = DummyCoin()
        
        def mock_decision_effect(coin):
            coin.final_score = 65.0
            coin.decision = "BUY"
            coin.strategy_id = "S6_Moonshot_Ladder"
            coin.signal_market_cap = 50000.0
            coin.valid = True
            return coin
            
        self.mock_collect.side_effect = lambda c: c
        self.mock_gemtools.side_effect = lambda c: c
        self.mock_fundamentals.side_effect = lambda c: c
        self.mock_decision.side_effect = mock_decision_effect

        self.mock_recheck.return_value = ExecutionState(
            checked_at=1000.0, market_cap=50000.0, price=1.0, liquidity=20000.0,
            volume_5m=5000.0, buys_5m=50, sells_5m=50, signal_market_cap=50000.0,
            mc_multiple_from_signal=1.0, signal_age_seconds=10.0
        )
        
        # mock paper setup removed

        with patch.dict(os.environ, {"S6_Moonshot_VNext_MODE": "SHADOW", "LIVE_TRADING": "False"}):
            coin = process_message(message)
            
        # Verify it went through successfully and wasn't blocked by Position Sizer
        self.assertTrue(getattr(coin, 'buy_blocked_by', None) is None or "Position Sizer" not in getattr(coin, 'buy_blocked_by', ''))
        
        # Verify trade_executor.buy was called with amount=2.0
        mock_paper.buy.assert_called_once()
        args, kwargs = mock_paper.buy.call_args
        # buy(coin, amount)
        self.assertEqual(kwargs.get('amount') or args[1], 2.0)

    @patch('engine.pipeline.PaperTrader')
    def test_pipeline_e2e_score_below_62_rejected(self, mock_paper_trader_class):
        message = {"token": "E2ETEST_SCORE", "contract": "SCORE_CONTRACT", "market_cap": 50000.0}
        class DummyCoin: 
            contract = 'DUMMY'
            decision = 'BUY'
            buy_blocked_by = None
            symbol = 'TEST'
        self.mock_parse.return_value = DummyCoin()
        
        def mock_decision_effect(coin):
            coin.final_score = 61.0 # < 62.0
            coin.decision = "BUY"
            coin.valid = True
            return coin
            
        self.mock_collect.side_effect = lambda c: c
        self.mock_gemtools.side_effect = lambda c: c
        self.mock_fundamentals.side_effect = lambda c: c
        self.mock_decision.side_effect = mock_decision_effect

        self.mock_recheck.return_value = ExecutionState(
            checked_at=1000.0, market_cap=50000.0, price=1.0, liquidity=20000.0,
            volume_5m=5000.0, buys_5m=50, sells_5m=50, signal_market_cap=50000.0,
            mc_multiple_from_signal=1.0, signal_age_seconds=10.0
        )
        
        mock_paper = MagicMock()
        mock_paper_trader_class.return_value = mock_paper

        with patch.dict(os.environ, {"S6_Moonshot_VNext_MODE": "SHADOW", "LIVE_TRADING": "False"}):
            coin = process_message(message)
            
        # Verify blocked by position sizer due to amount = 0
        self.assertIn("Position Sizer: Final score 61.0 < 62.0", getattr(coin, 'buy_blocked_by', ''))
        
        mock_paper.buy.assert_not_called()

    @patch('engine.pipeline.PaperTrader')
    def test_pipeline_e2e_mcx_gt_2_rejected(self, mock_paper_trader_class):
        message = {"token": "E2ETEST_MCX", "contract": "MCX_CONTRACT", "market_cap": 50000.0}
        class DummyCoin: 
            contract = 'DUMMY'
            decision = 'BUY'
            buy_blocked_by = None
            symbol = 'TEST'
        self.mock_parse.return_value = DummyCoin()
        
        def mock_decision_effect(coin):
            coin.final_score = 80.0
            coin.decision = "BUY"
            coin.valid = True
            return coin
            
        self.mock_collect.side_effect = lambda c: c
        self.mock_gemtools.side_effect = lambda c: c
        self.mock_fundamentals.side_effect = lambda c: c
        self.mock_decision.side_effect = mock_decision_effect

        # MCx = 2.01
        self.mock_recheck.return_value = ExecutionState(
            checked_at=1000.0, market_cap=100500.0, price=1.0, liquidity=20000.0,
            volume_5m=5000.0, buys_5m=50, sells_5m=50, signal_market_cap=50000.0,
            mc_multiple_from_signal=2.01, signal_age_seconds=10.0
        )
        
        mock_paper = MagicMock()
        mock_paper_trader_class.return_value = mock_paper

        with patch.dict(os.environ, {"S6_Moonshot_VNext_MODE": "SHADOW", "LIVE_TRADING": "False"}):
            coin = process_message(message)
            
        # Verify blocked by position sizer due to amount = 0
        self.assertIn("Position Sizer: MCx 2.01 > 2.0", getattr(coin, 'buy_blocked_by', ''))
        
        mock_paper.buy.assert_not_called()

if __name__ == '__main__':
    unittest.main()
