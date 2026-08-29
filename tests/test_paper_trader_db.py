import unittest
import os
import sys
import time
import sqlite3
from unittest.mock import patch, MagicMock

# Force test database usage BEFORE imports
TEST_DB_PATH = "database/test_paper_trader.db"

# Remove old test DB if it exists
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except OSError:
        pass

# Ensure project root is in sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config
config.DATABASE = TEST_DB_PATH

# Setup test DB tables
from database.models import create_tables
create_tables()

from trading.portfolio import Portfolio
from trading.position import Position
from execution.paper_trader import PaperTrader
from database.database import database

class MockCoin:
    def __init__(self, symbol="TESTCOIN", contract="0xMockAddress"):
        self.symbol = symbol
        self.contract = contract
        self.signal_id = f"sig_{int(time.time())}"
        self.final_score = 63.0
        self.gt_score = 1
        self.valid = True
        self.liquidity = 20000.0
        self.signal_market_cap = 40000.0
        self.live_market_cap = 40000.0
        self.buys_5m = 50
        self.sells_5m = 50
        self.price = 1.0
        self.volume_5m = 10000.0

class TestPaperTraderDB(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure clean environment
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass
        create_tables()

    @classmethod
    def tearDownClass(cls):
        # Close connection cleanly and clean up test file
        database.close()
        time.sleep(0.5)
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass

    def setUp(self):
        # Override env variables for deterministic paper trading
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        os.environ['PAPER_USE_LIVE_QUOTES'] = "False"
        self.portfolio = Portfolio()
        self.trader = PaperTrader(self.portfolio)

    def test_paper_trade_lifecycle_and_db_persistence(self):
        coin = MockCoin(symbol="TESTCOIN", contract="0xMockAddress")
        
        # ----------------------------------------------------
        # 1. Paper BUY
        # ----------------------------------------------------
        amount = 100.0
        position = self.trader.buy(coin, amount)
        self.assertIsNotNone(position)
        
        # Verify it exists in the database
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT trade_id, symbol, status, invested, cost_mode, network_fee FROM paper_trades WHERE trade_id = ?", (position.trade_id,))
        row = cursor.fetchone()
        self.assertIsNotNone(row, "Paper trade row should be created in DB after buy")
        self.assertEqual(row[1], "TESTCOIN")
        self.assertEqual(row[2], "OPEN")
        self.assertEqual(row[3], 100.0)
        self.assertEqual(row[4], "MODELED_COST")
        self.assertEqual(row[5], 0.0)
        
        # ----------------------------------------------------
        # 2. Simulated position updates
        # ----------------------------------------------------
        # Simulate price going up by 50%
        position.update_price(1.50, 60000.0)
        
        # ----------------------------------------------------
        # 3. Partial SELL (50%)
        # ----------------------------------------------------
        success = self.trader.partial_sell(position, percent=50.0, exit_reason="Take Profit 50%")
        self.assertTrue(success)
        
        # Verify database row updates after partial sell
        cursor.execute("SELECT remaining_pct, realized_pnl, fees, slippage FROM paper_trades WHERE trade_id = ?", (position.trade_id,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 50.0)
        self.assertGreater(row[1], 0.0)
        
        # Verify partial sell table contains the event record
        cursor.execute("SELECT percent_sold, proceeds, exit_reason, cost_mode, network_fee FROM paper_partial_sells WHERE trade_id = ?", (position.trade_id,))
        partial_row = cursor.fetchone()
        self.assertIsNotNone(partial_row)
        self.assertEqual(partial_row[0], 50.0)
        self.assertEqual(partial_row[2], "Take Profit 50%")
        self.assertEqual(partial_row[3], "MODELED_COST")
        
        # ----------------------------------------------------
        # 4. Final SELL (Close the rest of the trade)
        # ----------------------------------------------------
        success = self.trader.sell_all(position, exit_reason="Close position")
        self.assertTrue(success)
        
        # Verify final database state
        cursor.execute("SELECT status, remaining_pct, exit_reason, cost_mode, network_fee, commission FROM paper_trades WHERE trade_id = ?", (position.trade_id,))
        final_row = cursor.fetchone()
        self.assertEqual(final_row[0], "CLOSED")
        self.assertEqual(final_row[1], 0.0)
        self.assertEqual(final_row[2], "Close position")
        self.assertEqual(final_row[3], "MODELED_COST")
        self.assertEqual(final_row[4], 0.0)
        self.assertEqual(final_row[5], 0.0)
        
        conn.close()

if __name__ == '__main__':
    unittest.main()
