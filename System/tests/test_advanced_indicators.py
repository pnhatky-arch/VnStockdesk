import unittest

import numpy as np
import pandas as pd

from src.analyzer import analyze_symbol
from src.indicators import add_indicators


def trending_frame(rows=420):
    time = pd.bdate_range("2025-01-01", periods=rows)
    close = np.linspace(20.0, 52.0, rows) + np.sin(np.arange(rows) / 8) * 0.35
    return pd.DataFrame({
        "time": time, "open": close - .1, "high": close + .4,
        "low": close - .4, "close": close,
        "volume": np.linspace(1_000_000, 2_000_000, rows),
    })


class AdvancedIndicatorTests(unittest.TestCase):
    def test_indicators_are_computed_without_external_provider(self):
        latest = add_indicators(trending_frame()).iloc[-1]
        for key in ("macd", "macd_signal", "macd_hist", "adx14", "plus_di14",
                    "minus_di14", "obv", "obv_ema20"):
            self.assertTrue(pd.notna(latest[key]), key)
        self.assertGreater(latest["plus_di14"], latest["minus_di14"])

    def test_analysis_exposes_new_evidence_and_version(self):
        result = analyze_symbol("TEST", trending_frame(), reference_date="2026-08-28")
        day = result["timeframes"]["1D"]
        self.assertIn("macd", day)
        self.assertIn("adx14", day)
        self.assertIn("obv_bias", day)
        self.assertIn("macd", day["component_scores"])
        self.assertEqual(result["engine_version"], "PRO_DECISION_4TF_MACD_ADX_OBV")


if __name__ == "__main__":
    unittest.main()
