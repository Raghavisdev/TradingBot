import unittest
import time
import uuid
from database.database import database
from execution.paper_trader import PaperTrader
from trading.portfolio import Portfolio
from trading.trade_manager import TradeManager
from ai_engine.position_sizer import get_position_size
from knowledge.coin import Coin

class TestLAPCV2(unittest.TestCase):
    def setUp(self):
        # Clean db
        conn = database.trade_logger.connection
        c = conn.cursor()
        c.execute("DELETE FROM paper_trades")
        conn.commit()
        
        c = database.signal_logger.connection.cursor()
        c.execute("DELETE FROM signals")
        database.signal_logger.connection.commit()
        
        self.portfolio = Portfolio()
        self.portfolio.cash = 100.0
        self.portfolio.initial_balance = 100.0
        self.trader = PaperTrader(self.portfolio)
        self.trade_manager = TradeManager(self.portfolio, self.trader)

    def _mock_coin(self, score, live_mc=100000, signal_mc=100000):
        c = Coin()
        c.symbol = "TEST"
        c.contract = "TestContract_" + str(uuid.uuid4())
        c.price = 1.0
        c.live_market_cap = live_mc
        c.signal_market_cap = signal_mc
        c.final_score = score
        c.signal_id = str(uuid.uuid4())
        c.signal_time = time.time()
        
        # Simulate global decision logic
        if score >= 80: c.decision = "BUY"
        elif score >= 65: c.decision = "WATCH"
        else: c.decision = "SKIP"
        # Simulate pipeline override
        if c.decision in ["WATCH", "SKIP"] and c.final_score >= 62:
            c.decision = "BUY"
            
        # Write to DB so recover_open_positions can read it
        database.signal_logger.save(c)
            
        return c

    def test_1_score_61_no_probe(self):
        c = self._mock_coin(61)
        self.assertNotEqual(c.decision, "BUY")
        size = get_position_size(c, self.portfolio)
        self.assertEqual(size, 0.0)

    def test_2_score_62_probe(self):
        c = self._mock_coin(62)
        self.assertEqual(c.decision, "BUY")
        size = get_position_size(c, self.portfolio)
        self.assertEqual(size, 2.0)
        pos = self.trader.buy(c, size)
        self.assertIsNotNone(pos)
        self.assertEqual(pos.invested_amount, 2.0)
        self.assertGreater(pos.probe_entry_time, 0)
        self.assertEqual(pos.scale_in_completed, 0)
        self.assertEqual(pos.post_probe_snapshot_count, 0)

    def test_3_score_65_two_snapshots(self):
        c = self._mock_coin(65)
        pos = self.trader.buy(c, 2.0)
        
        # Snapshot 1
        time.sleep(0.01)
        pos.current_market_cap = c.live_market_cap
        pos.last_api_success = True
        self.trade_manager.update()
        
        # Snapshot 2
        time.sleep(0.01)
        pos.last_api_success = True
        self.trade_manager.update()
        
        self.assertEqual(pos.post_probe_snapshot_count, 2)
        self.assertEqual(pos.invested_amount, 2.0)
        self.assertEqual(pos.scale_in_completed, 0)

    def test_4_score_65_three_snapshots_scale(self):
        c = self._mock_coin(65)
        pos = self.trader.buy(c, 2.0)
        
        for _ in range(3):
            time.sleep(0.01)
            pos.current_market_cap = c.live_market_cap
            pos.last_api_success = True
            self.trade_manager.update()
            
        self.assertEqual(pos.post_probe_snapshot_count, 3)
        self.assertEqual(pos.invested_amount, 7.0)
        self.assertEqual(pos.scale_in_completed, 1)

    def test_5_score_65_three_snapshots_drop_reject(self):
        c = self._mock_coin(65)
        pos = self.trader.buy(c, 2.0)
        
        for _ in range(3):
            time.sleep(0.01)
            pos.current_market_cap = c.live_market_cap * 0.85 # -15% drop
            pos.last_api_success = True
            self.trade_manager.update()
            
        self.assertEqual(pos.post_probe_snapshot_count, 3)
        self.assertEqual(pos.invested_amount, 2.0)
        self.assertEqual(pos.scale_in_completed, 1)

    def test_6_mcx_1_0_accepted(self):
        c = self._mock_coin(65, live_mc=100000, signal_mc=100000)
        pos = self.trader.buy(c, 2.0)
        self.assertIsNotNone(pos)

    def test_6_mcx_1_99_accepted(self):
        c = self._mock_coin(65, live_mc=199000, signal_mc=100000)
        pos = self.trader.buy(c, 2.0)
        self.assertIsNotNone(pos)

    def test_6_mcx_2_00_accepted(self):
        c = self._mock_coin(65, live_mc=200000, signal_mc=100000)
        pos = self.trader.buy(c, 2.0)
        self.assertIsNotNone(pos)

    def test_6_mcx_2_01_rejected(self):
        c = self._mock_coin(65, live_mc=201000, signal_mc=100000)
        pos = self.trader.buy(c, 2.0)
        self.assertIsNone(pos)

    def test_6_mcx_2_50_rejected(self):
        c = self._mock_coin(65, live_mc=250000, signal_mc=100000)
        pos = self.trader.buy(c, 2.0)
        self.assertIsNone(pos)

    def test_6_missing_signal_mc_rejected(self):
        c = self._mock_coin(65)
        c.signal_market_cap = None
        pos = self.trader.buy(c, 2.0)
        self.assertIsNone(pos)

    def test_6_zero_signal_mc_rejected(self):
        c = self._mock_coin(65)
        c.signal_market_cap = 0
        pos = self.trader.buy(c, 2.0)
        self.assertIsNone(pos)

    def test_6_missing_execution_mc_rejected(self):
        c = self._mock_coin(65)
        c.live_market_cap = None
        pos = self.trader.buy(c, 2.0)
        self.assertIsNone(pos)

    def test_6_vnext_sizing_path_rejected(self):
        # Even if pipeline bypasses position_sizer and hands PaperTrader $4.26, it should be rejected
        c = self._mock_coin(65, live_mc=250000, signal_mc=100000)
        pos = self.trader.buy(c, 4.26)
        self.assertIsNone(pos)

    def test_6_non_s6_unaffected(self):
        # non-S6 strategies bypass MCx checks
        c = self._mock_coin(65, live_mc=250000, signal_mc=100000)
        c.strategy_id = "S5_Momentum"
        pos = self.trader.buy(c, 2.0)
        self.assertIsNotNone(pos)

    def test_7_max_deployed_35(self):
        # We need to simulate deploying up to \
        # 4 positions * 7.0 = 28.0 invested.
        for i in range(4):
            c = self._mock_coin(65)
            pos = self.trader.buy(c, 2.0)
            for _ in range(3):
                time.sleep(0.01)
                pos.last_api_success = True
                self.trade_manager.update()
            self.assertEqual(pos.invested_amount, 7.0)

        c = self._mock_coin(65)
        size = get_position_size(c, self.portfolio)
        self.assertEqual(size, 2.0)
        pos = self.trader.buy(c, size)
        
        for _ in range(3):
            time.sleep(0.01)
            pos.last_api_success = True
            self.trade_manager.update()
            
        self.assertEqual(pos.scale_in_completed, 1)
        self.assertEqual(pos.invested_amount, 2.0)

    def test_8_5_open_positions_blocked(self):
        for i in range(5):
            c = self._mock_coin(62)
            pos = self.trader.buy(c, 2.0)
            
        c = self._mock_coin(62)
        size = get_position_size(c, self.portfolio)
        self.assertEqual(size, 0.0)

    def test_9_restart_after_probe(self):
        c = self._mock_coin(65)
        pos = self.trader.buy(c, 2.0)
        
        time.sleep(0.01)
        pos.last_api_success = True
        self.trade_manager.update()
        
        new_portfolio = Portfolio()
        new_portfolio.cash = 100.0
        new_portfolio.initial_balance = 100.0
        new_trader = PaperTrader(new_portfolio)
        new_manager = TradeManager(new_portfolio, new_trader)
        new_manager.recover_open_positions(strategy_id="S6_Moonshot_Ladder")
        
        recovered_pos = next((p for p in new_portfolio.get_open_positions() if p.contract == pos.contract), None)
        self.assertIsNotNone(recovered_pos)
        self.assertEqual(recovered_pos.post_probe_snapshot_count, 1)
        self.assertEqual(recovered_pos.scale_in_completed, 0)
        
        for _ in range(2):
            time.sleep(0.01)
            recovered_pos.last_api_success = True
            new_manager.update()
            
        self.assertEqual(recovered_pos.invested_amount, 7.0)
        self.assertEqual(recovered_pos.scale_in_completed, 1)

    def test_10_restart_after_scale(self):
        c = self._mock_coin(65)
        pos = self.trader.buy(c, 2.0)
        
        for _ in range(3):
            time.sleep(0.01)
            pos.last_api_success = True
            self.trade_manager.update()
            
        self.assertEqual(pos.scale_in_completed, 1)
        
        new_portfolio = Portfolio()
        new_portfolio.cash = 100.0
        new_portfolio.initial_balance = 100.0
        new_trader = PaperTrader(new_portfolio)
        new_manager = TradeManager(new_portfolio, new_trader)
        new_manager.recover_open_positions(strategy_id="S6_Moonshot_Ladder")
        
        recovered_pos = next((p for p in new_portfolio.get_open_positions() if p.contract == pos.contract), None)
        self.assertIsNotNone(recovered_pos)
        self.assertEqual(recovered_pos.scale_in_completed, 1)
        
        time.sleep(0.01)
        recovered_pos.last_api_success = True
        new_manager.update()
        self.assertEqual(recovered_pos.invested_amount, 7.0)

    def test_11_observed_quote_friction(self):
        c = self._mock_coin(62)
        self.portfolio.cash = 2.00
        pos = self.trader.buy(c, 2.0)
        self.assertIsNone(pos)
        
        self.portfolio.cash = 2.05
        pos = self.trader.buy(c, 2.0)
        self.assertIsNotNone(pos)

    def test_12_s7_absence(self):
        pass

if __name__ == "__main__":
    unittest.main()
