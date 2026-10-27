import unittest
import numpy as np
import pandas as pd
from src.index_engine import analyze_vnindex, _quote_values


def index_frame(rows=700, slope=.35):
    t = np.arange(rows)
    close = 900 + slope * t + np.sin(t / 9) * 6
    return pd.DataFrame({"time": pd.bdate_range("2023-01-02", periods=rows),
                         "open": close - 1, "high": close + 5, "low": close - 5,
                         "close": close, "volume": 500_000_000 + t * 1000})


class IndexEngineTests(unittest.TestCase):
    def test_scenarios_are_ordered_and_weights_sum_to_100(self):
        scan = pd.DataFrame({"consensus_score": [40, 35, 10, -5] * 20})
        result = analyze_vnindex(index_frame(), scan, 20)
        levels = result["levels"]
        self.assertGreaterEqual(levels["bull_extended"], levels["bull_target"])
        self.assertLessEqual(levels["extreme_downside"], levels["bear_target"])
        self.assertAlmostEqual(sum(result["scenario_weights"].values()), 100.0, places=1)
        self.assertGreater(result["historical_distribution_pct"]["observations"], 40)

    def test_missing_breadth_is_disclosed(self):
        result = analyze_vnindex(index_frame(), pd.DataFrame(), 10)
        self.assertIn("BREADTH_UNAVAILABLE", result["warnings"])

    def test_selected_index_identity_is_retained(self):
        result = analyze_vnindex(index_frame(), pd.DataFrame(), 10, symbol="VN30")
        self.assertEqual(result["symbol"], "VN30")

    def test_quote_values_supports_multi_index_columns(self):
        raw = pd.DataFrame([[1820.5, 12.5]], columns=pd.MultiIndex.from_tuples([
            ("match", "match_price"), ("change", "price_change")]))
        values = _quote_values(raw)
        self.assertEqual(values["match_price"], 1820.5)
        self.assertEqual(values["price_change"], 12.5)


if __name__ == "__main__":
    unittest.main()
