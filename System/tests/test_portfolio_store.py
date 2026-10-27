import tempfile
import unittest
from pathlib import Path

from src.portfolio_store import PortfolioStore


class PortfolioStoreTests(unittest.TestCase):
    def test_save_load_list_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PortfolioStore(Path(directory) / "portfolios.json")
            saved = store.save("Dài hạn", "VN30", [
                {"symbol": "fpt", "quantity": 500, "buy_price": 123.456},
                {"symbol": "", "quantity": 0, "buy_price": 0},
            ])
            self.assertEqual(saved["positions"][0]["buy_price"], 123.456)
            self.assertEqual(store.list()[0]["name"], "Dài hạn")
            self.assertEqual(store.get("Dài hạn")["basket"], "VN30")
            store.delete("Dài hạn")
            self.assertEqual(store.list(), [])

    def test_rejects_empty_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PortfolioStore(Path(directory) / "portfolios.json")
            with self.assertRaises(ValueError):
                store.save("Test", "VN30", [])

    def test_save_futures_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PortfolioStore(Path(directory) / "futures.json")
            saved = store.save_futures("Trong ngày", [
                {"symbol":"vn30f1m", "side":"long", "quantity":3, "entry_price":1950.125}
            ])
            self.assertEqual(saved["positions"][0], {
                "symbol":"VN30F1M", "side":"LONG", "quantity":3, "entry_price":1950.125,
            })
            self.assertEqual(store.get("Trong ngày")["positions"][0]["side"], "LONG")


if __name__ == "__main__":
    unittest.main()
