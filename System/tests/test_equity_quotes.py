import unittest

import pandas as pd

from src.equity_quotes import load_equity_quote


class _Equity:
    def quote(self, source):
        if source == "KBS":
            return pd.DataFrame([{"match_price": 72.2, "bid_price_1": 72.1, "ask_price_1": 72.3}])
        raise AssertionError("fallback should not be needed")


class _Market:
    def equity(self, symbol):
        self.symbol = symbol
        return _Equity()


class EquityQuoteTests(unittest.TestCase):
    def test_quote_returns_price_for_valid_equity_symbol(self):
        quote = load_equity_quote("FPT", market_factory=_Market)
        self.assertEqual(quote["status"], "OK")
        self.assertEqual(quote["price"], 72.2)
        self.assertEqual(quote["provider"], "KBS")

    def test_quote_rejects_invalid_symbol(self):
        with self.assertRaises(ValueError):
            load_equity_quote("not a symbol", market_factory=_Market)


if __name__ == "__main__":
    unittest.main()
