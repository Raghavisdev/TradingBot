import unittest
import os
import json
import time

from ai_engine.s6_canonical_exit import evaluate_s6_exit

class MockPosition:
    def __init__(self, entry_price):
        self.entry_price = entry_price
        self.high_water_mark = entry_price
        self.fired_ladder_levels = set()

class TestS6OptimalExit(unittest.TestCase):

    def setUp(self):
        # Create test config for the FixedLadderTrailing strategy discovered by optimizer
        self.config_path = os.path.join(os.path.dirname(__file__), "..", "analytics", "paper_lab", "s6_exit_config.json")
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        self.test_config = {
            "policy": "FixedLadderTrailing",
            "hard_stop_pct": -30.0,
            "trail_activation_pct": 50.0,
            "trailing_stop_pct": 30.0,
            "profit_rungs": [
                {"trigger_pct": 150.0, "sell_pct": 50.0}
            ],
            "scale_in_enabled": False
        }
        with open(self.config_path, "w") as f:
            json.dump(self.test_config, f)

    def tearDown(self):
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def test_hard_stop(self):
        pos = MockPosition(entry_price=10.0)
        # Price drops 30%
        action, pct, reason = evaluate_s6_exit(pos, 7.0)
        self.assertEqual(action, "SELL_ALL")
        self.assertEqual(pct, 100.0)
        self.assertEqual(reason, "Hard Stop")

    def test_profit_rung_and_duplicate_prevention(self):
        pos = MockPosition(entry_price=10.0)
        # Price pumps 150%
        action, pct, reason = evaluate_s6_exit(pos, 25.0)
        self.assertEqual(action, "SELL_PCT")
        self.assertEqual(pct, 50.0)
        self.assertEqual(reason, "Rung 150.0%")
        
        # Second tick at same price shouldn't fire again
        action, pct, reason = evaluate_s6_exit(pos, 25.0)
        self.assertEqual(action, "HOLD")
        
    def test_high_water_mark_and_trailing_stop(self):
        pos = MockPosition(entry_price=10.0)
        # Pump to +60% ($16) -> Activates trail (Activation=50%)
        action, pct, reason = evaluate_s6_exit(pos, 16.0)
        self.assertEqual(action, "HOLD")
        self.assertEqual(pos.high_water_mark, 16.0)
        
        # Drop by 30% from +60% MFE -> This is 60 - 30 = +30% unrealized
        # So price at 13.0 should trigger Trailing Stop
        action, pct, reason = evaluate_s6_exit(pos, 13.0)
        self.assertEqual(action, "SELL_ALL")
        self.assertEqual(pct, 100.0)
        self.assertEqual(reason, "Trailing Stop")
        
    def test_qINU_regression_path(self):
        # qINU Entry was $2. Hit +126.18% MFE, then bled down
        pos = MockPosition(entry_price=2.0)
        
        # Tick 1: +126.18%
        price_126 = 2.0 * (1 + 1.2618)
        action, pct, reason = evaluate_s6_exit(pos, price_126)
        # The rung is 150%, so it HOLDs. But it sets high_water_mark.
        self.assertEqual(action, "HOLD")
        self.assertAlmostEqual(pos.high_water_mark, 4.5236)
        
        # Trailing stop activates at 50%. The max return was 126.18%.
        # Trailing stop is 30% behind max_return. 
        # So trailing stop fires if unrealized_pct <= 96.18%.
        price_trail = 2.0 * (1 + 0.9618)
        
        # Drop to +96.18%
        action, pct, reason = evaluate_s6_exit(pos, price_trail)
        self.assertEqual(action, "SELL_ALL")
        self.assertEqual(reason, "Trailing Stop")
        # In reality, the optimizer caught it right when it crossed this threshold.
        # This prevents the -80% MAE bleeding observed in production!

if __name__ == '__main__':
    unittest.main()
