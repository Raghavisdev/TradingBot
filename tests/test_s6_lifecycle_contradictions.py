import unittest
import os
import sys
from unittest.mock import patch, MagicMock



from engine.pipeline import process_message
from trading.portfolio import Portfolio
from ai_engine.execution_recheck import ExecutionState
import database

class TestS6LifecycleContradictions(unittest.TestCase):
    def setUp(self):
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
        
        self.patcher_collect = patch('engine.pipeline.collect_all')
        self.mock_collect = self.patcher_collect.start()
        self.patcher_gemtools = patch('engine.pipeline.analyze_gemtools')
        self.mock_gemtools = self.patcher_gemtools.start()
        self.patcher_fundamentals = patch('engine.pipeline.analyze_fundamentals')
        self.mock_fundamentals = self.patcher_fundamentals.start()
        self.patcher_parse = patch('engine.pipeline.parse_signal')
        self.mock_parse = self.patcher_parse.start()

        self.patcher_db_create = patch('engine.pipeline.database.create_signal')
        self.mock_db_create = self.patcher_db_create.start()
        self.patcher_db_update = patch('engine.pipeline.database.update_signal')
        self.mock_db_update = self.patcher_db_update.start()
        
        self.patcher_tracker = patch('engine.pipeline.tracker_manager.start_tracking')
        self.mock_tracker = self.patcher_tracker.start()
        self.patcher_recheck = patch('ai_engine.s6_execution.recheck_market')
        self.mock_recheck = self.patcher_recheck.start()
        
        # We DO NOT mock make_decision here, because we WANT to see its legacy behavior
        # However, to avoid requiring a real ML model, we will mock make_decision 
        # to simulate its exact behavior (setting coin.decision and coin.decision_reason)
        self.patcher_decision = patch('engine.pipeline.make_decision')
        self.mock_decision = self.patcher_decision.start()

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

    def test_eligible_s6_no_contradiction(self):
        # Emulate the RBS case: score=58 -> Legacy SKIP -> S6 V2 BUY
        class DummyCoin:
            contract = 'DUMMY'
            symbol = 'RBS'
            signal_id = 'SIG1'
            decision = None
            decision_reason = None
            buy_blocked_by = None
            bought = False
        coin_obj = DummyCoin()
        self.mock_parse.return_value = coin_obj
        
        self.mock_collect.side_effect = lambda c: c
        self.mock_gemtools.side_effect = lambda c: c
        self.mock_fundamentals.side_effect = lambda c: c
        
        def mock_make_decision(coin):
            coin.final_score = 58.0
            coin.decision = "SKIP"
            coin.decision_reason = "Final Score: 58/100 -> SKIP"
            coin.strategy_id = "S6_Moonshot_Ladder"
            coin.signal_market_cap = 50000.0
            coin.valid = True
            return coin
        
        self.mock_decision.side_effect = mock_make_decision
        
        self.mock_recheck.return_value = ExecutionState(
            checked_at=1000.0,
            market_cap=50000.0,
            price=1.0,
            liquidity=10000.0,
            volume_5m=5000.0,
            buys_5m=50,
            sells_5m=10,
            signal_market_cap=50000.0,
            signal_price=1.0,
            mc_multiple_from_signal=1.0,
            price_multiple_from_signal=1.0,
            signal_age_seconds=5.0
        )
        
        mock_paper_trader = MagicMock()
        mock_position = MagicMock()
        mock_position.symbol = "RBS"
        mock_position.entry_price = 1.0
        mock_position.entry_market_cap = 50000.0
        mock_paper_trader.buy.return_value = mock_position

        with patch('engine.pipeline.trader', mock_paper_trader):
            final_coin = process_message({"token": "RBS"})
        
        # Assert contradiction is resolved
        self.assertEqual(final_coin.decision, "BUY")
        self.assertTrue("S6 V2 APPROVED" in final_coin.decision_reason)
        self.assertNotIn("SKIP", final_coin.decision_reason) # NO SKIP IN REASON!
        self.assertEqual(final_coin.buy_blocked_by, "")
        self.assertTrue(final_coin.bought)

    def test_rejected_s6_no_contradiction(self):
        # Emulate score=54 -> Legacy SKIP -> S6 V2 SKIP (because < 55)
        class DummyCoin:
            contract = 'DUMMY2'
            symbol = 'BAD'
            signal_id = 'SIG2'
            decision = None
            decision_reason = None
            buy_blocked_by = None
            bought = False
        coin_obj = DummyCoin()
        self.mock_parse.return_value = coin_obj
        self.mock_collect.side_effect = lambda c: c
        self.mock_gemtools.side_effect = lambda c: c
        self.mock_fundamentals.side_effect = lambda c: c
        
        def mock_make_decision(coin):
            coin.final_score = 54.0
            coin.decision = "SKIP"
            coin.decision_reason = "Final Score: 54/100 -> SKIP"
            coin.strategy_id = "S6_Moonshot_Ladder"
            coin.signal_market_cap = 50000.0
            coin.valid = True
            return coin
        
        self.mock_decision.side_effect = mock_make_decision
        
        mock_paper_trader = MagicMock()
        
        with patch('engine.pipeline.trader', mock_paper_trader):
            final_coin = process_message({"token": "BAD"})
        
        self.assertEqual(final_coin.decision, "SKIP")
        self.assertTrue("S6 V2 REJECTED" in final_coin.decision_reason)
        self.assertTrue("Final score 54.0 < 55.0" in final_coin.decision_reason)
        self.assertEqual(final_coin.buy_blocked_by, "S6 Execution Evaluator")
        self.assertFalse(final_coin.bought)


class TestPaperSessionID(unittest.TestCase):
    def test_session_id_in_db(self):
        # Test that Database Manager's open_trade properly injects the PAPER_SESSION_ID
        from database.trade_logger import TradeLogger
        import sqlite3
        
        # Use an in-memory DB or test DB to verify insertion
        logger = TradeLogger()
        logger.connection = sqlite3.connect(":memory:")
        logger.connection.row_factory = sqlite3.Row
        
        # Create table for test
        cursor = logger.connection.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades(
            trade_id TEXT UNIQUE,
            session_id TEXT DEFAULT 'S6_FORWARD_2026_08_22',
            strategy_id TEXT,
            strategy_version TEXT,
            signal_id TEXT,
            symbol TEXT,
            contract TEXT,
            status TEXT,
            entry_time REAL,
            entry_price REAL,
            entry_market_cap REAL,
            invested REAL,
            tokens REAL,
            remaining_pct REAL,
            exit_time REAL,
            exit_price REAL,
            exit_market_cap REAL,
            exit_reason TEXT,
            realized_pnl REAL,
            realized_pct REAL,
            mfe REAL,
            mae REAL,
            fees REAL,
            slippage REAL,
            cost_mode TEXT,
            network_fee REAL,
            commission REAL,
            updated_at REAL,
            probe_entry_time REAL,
            probe_entry_market_cap REAL,
            scale_in_completed INTEGER,
            post_probe_snapshot_count INTEGER
        )
        """)
        
        class DummyPosition:
            trade_id = "TEST_TRADE_1"
            strategy_id = "S6_Moonshot_Ladder"
            strategy_version = "1.0"
            signal_id = "SIG_1"
            symbol = "TEST"
            contract = "TESTCONT"
            status = "OPEN"
            entry_time = 1000.0
            entry_price = 1.0
            entry_market_cap = 50000.0
            invested_amount = 10.0
            tokens = 10.0
            remaining_pct = 100.0
            probe_entry_time = 1000.0
            probe_entry_market_cap = 50000.0
            scale_in_completed = 0
            post_probe_snapshot_count = 0
            
        pos = DummyPosition()
        
        # 1. Test with explicit Env Var
        os.environ["PAPER_SESSION_ID"] = "MY_SPECIAL_SESSION_123"
        logger.open_trade(pos)
        
        cursor.execute("SELECT session_id FROM paper_trades WHERE trade_id='TEST_TRADE_1'")
        row = cursor.fetchone()
        self.assertEqual(row["session_id"], "MY_SPECIAL_SESSION_123")
        
        # 2. Test Default Env Var
        del os.environ["PAPER_SESSION_ID"]
        pos.trade_id = "TEST_TRADE_2"
        logger.open_trade(pos)
        
        cursor.execute("SELECT session_id FROM paper_trades WHERE trade_id='TEST_TRADE_2'")
        row = cursor.fetchone()
        self.assertEqual(row["session_id"], "S6_RUNTIME_PAPER")
        
if __name__ == '__main__':
    unittest.main()
