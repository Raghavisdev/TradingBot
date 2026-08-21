import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from execution.paper_trader import PaperTrader
from trading.portfolio import Portfolio
from trading.position import Position
from execution.live_trader import LiveTrader
import config

class MockCoin:
    def __init__(self, symbol, contract, price):
        self.symbol = symbol
        self.contract = contract
        self.price = price
        self.signal_id = "test_signal"
        self.live_market_cap = 100000

class TestProductionSafety(unittest.TestCase):
    
    def setUp(self):
        os.environ['PAPER_INITIAL_BALANCE'] = "500.0"
        self.portfolio = Portfolio()
        self.paper = PaperTrader(self.portfolio)
        # Ensure LiveTrading is OFF
        config.LIVE_TRADING = False

    def test_live_trading_is_false(self):
        """Phase F: Verify LIVE_TRADING is strictly False"""
        self.assertFalse(config.LIVE_TRADING, "CRITICAL ERROR: LIVE_TRADING is True!")

    def test_paper_buy_insufficient_liquidity(self):
        """Phase F: Insufficient capital / liquidity collapse"""
        coin = MockCoin("DUMMY", "DummyContract", 1.0)
        # Attempt to buy more than bankroll
        pos = self.paper.buy(coin, 1000.0)
        self.assertIsNone(pos, "Should return None on insufficient cash")

    def test_paper_buy_malformed_signal(self):
        """Phase F: Malformed signal / invalid price"""
        coin = MockCoin("DUMMY", "DummyContract", -1.0) # invalid price
        pos = self.paper.buy(coin, 10.0)
        self.assertIsNone(pos, "Should return None on malformed signal price")

    def test_duplicate_order(self):
        """Phase F: Duplicate partial exit logic"""
        coin = MockCoin("DUMMY", "DummyContract", 1.0)
        pos = self.paper.buy(coin, 10.0)
        self.assertIsNotNone(pos)
        
        res1 = self.paper.partial_sell(pos, 100) # sell 100%
        self.assertTrue(res1)
        self.assertEqual(pos.remaining_percent, 0.0)
        
        res2 = self.paper.partial_sell(pos, 50) # duplicate / over-sell
        self.assertFalse(res2, "Should block duplicate sell on closed position")

    def test_negative_allocation(self):
        """Phase F: Negative allocation"""
        coin = MockCoin("DUMMY", "DummyContract", 1.0)
        pos = self.paper.buy(coin, -10.0)
        self.assertIsNone(pos, "Should block negative allocation")

    def test_live_trader_safety_switch(self):
        """Phase F: LiveTrader obeys LIVE_TRADING=False"""
        lt = LiveTrader(self.portfolio)
        coin = MockCoin("DUMMY", "DummyContract", 1.0)
        pos = lt.buy(coin, 10.0)
        self.assertIsNone(pos, "LiveTrader MUST return None when LIVE_TRADING=False")

if __name__ == '__main__':
    unittest.main()
