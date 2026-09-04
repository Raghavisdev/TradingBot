import unittest
from parsers.signal_parser import parse_signal

class TestSignalParser(unittest.TestCase):
    def test_old_format(self):
        text = "🚀 $PEPE\n8BseCGzEktUvUpxF12R1X7XqH4rA5k3z4C3tUoB7QzYQ\nMC: $50M · Age: 1d · Holders: 1,000\nGTscore: ⭐⭐⭐⭐"
        coin = parse_signal(text)
        self.assertIsNotNone(coin)
        self.assertEqual(coin.symbol, "PEPE")
        self.assertEqual(coin.contract, "8BseCGzEktUvUpxF12R1X7XqH4rA5k3z4C3tUoB7QzYQ")

    def test_new_gemtools_format(self):
        text = "💎 $LARP\nDEWF4aou8aTXeTzr78WGESXw9ee5C62tHWQU3JcUpump\nMC: $50M · Age: 1d · Holders: 1,000\nGTscore: ⭐⭐⭐⭐"
        coin = parse_signal(text)
        self.assertIsNotNone(coin)
        self.assertEqual(coin.symbol, "LARP")
        self.assertEqual(coin.contract, "DEWF4aou8aTXeTzr78WGESXw9ee5C62tHWQU3JcUpump")

    def test_live_dtm_format(self):
        text = """🚀 $DTM (Duct-Taped Man)
3Ga3SdQUouCuuzFULcVnCYweVNY7RETq9cXf8tmZpump
GTscore: ⭐☆☆☆☆
Delayed 25s · VIP gets it instantly ...
MC now: $52.5K (+9% since alert)
MC: $48.2K · Age: 1m · Holders: 416
Top10: 20% · Bundled: 17% · First50: 31%
Jeeters: 12% · Fresh: — · Snipers: 0.0%
Insiders: 0.0% · Dev: 0.0%
Safe: 46% · Poor: 2.0%
11C · 33W · 36.1%"""
        coin = parse_signal(text)
        self.assertIsNotNone(coin)
        self.assertEqual(coin.symbol, "DTM")
        self.assertEqual(coin.name, "Duct-Taped Man")
        self.assertEqual(coin.contract, "3Ga3SdQUouCuuzFULcVnCYweVNY7RETq9cXf8tmZpump")
        self.assertEqual(coin.gt_score, 1)
        self.assertEqual(coin.market_cap, 48200.0)
        self.assertEqual(coin.age, "1m")
        self.assertEqual(coin.holders, 416)
        self.assertEqual(coin.top10, 20.0)
        self.assertEqual(coin.bundled, 17.0)
        self.assertEqual(coin.first50, 31.0)
        self.assertEqual(coin.jeeters, 12.0)
        self.assertEqual(coin.fresh, 0.0)
        self.assertEqual(coin.snipers, 0.0)
        self.assertEqual(coin.insiders, 0.0)
        self.assertEqual(coin.dev, 0.0)
        self.assertEqual(coin.safe, 46.0)
        self.assertEqual(coin.poor, 2.0)
        self.assertEqual(coin.community, 11)
        self.assertEqual(coin.whales, 33)
        self.assertEqual(coin.win_rate, 36.1)
        
    def test_new_gemtools_format_no_space(self):
        text = "🟢$DEBTCOIN\nDEWF4aou8aTXeTzr78WGESXw9ee5C62tHWQU3JcUpump\nMC: $50M"
        coin = parse_signal(text)
        self.assertIsNotNone(coin)
        self.assertEqual(coin.symbol, "DEBTCOIN")

    def test_performance_update_rejected(self):
        text = "🚀 $DICK x2 🚀\n8BseCGzEktUvUpxF12R1X7XqH4rA5k3z4C3tUoB7QzYQ"
        coin = parse_signal(text)
        self.assertIsNone(coin)
        
        text2 = "💎 $LARP 5x\nDEWF4aou8aTXeTzr78WGESXw9ee5C62tHWQU3JcUpump"
        coin2 = parse_signal(text2)
        self.assertIsNone(coin2)

    def test_random_text_rejected(self):
        text = "Just chatting about how good solana is today"
        coin = parse_signal(text)
        self.assertIsNone(coin)
        
    def test_no_ticker_rejected(self):
        text = "💎 LARP\nDEWF4aou8aTXeTzr78WGESXw9ee5C62tHWQU3JcUpump\nMC: 50M"
        coin = parse_signal(text)
        self.assertIsNone(coin)
