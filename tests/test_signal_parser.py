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
