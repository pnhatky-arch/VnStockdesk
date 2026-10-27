from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.analyzer import analyze_symbol
from src.data import cache_diagnostics


def sample(rows: int, end: str, volume: int = 2_000_000) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=rows)
    close = np.linspace(20.0, 25.0, rows)
    return pd.DataFrame({
        "time": dates,
        "open": close * .995,
        "high": close * 1.01,
        "low": close * .99,
        "close": close,
        "volume": volume,
    })


class DataQualityGuardTests(unittest.TestCase):
    def test_good_recent_liquid_data_can_be_scored(self):
        frame = sample(500, "2026-08-21")
        info = cache_diagnostics(frame, reference_date="2026-08-23")
        self.assertEqual(info["data_quality"], "GOOD")

    def test_low_liquidity_caps_grade_and_locks_action(self):
        frame = sample(500, "2026-08-21", volume=100)
        result = analyze_symbol("TEST", frame, reference_date="2026-08-23")
        self.assertEqual(result["data_quality"]["data_quality"], "WATCH")
        self.assertEqual(result["system_action"], "CHỜ_XÁC_NHẬN")
        self.assertIn(result["decision_grade"], {"C", "D"})
        self.assertEqual(result["strategy_plan"]["status"], "NO_TRADE")

    def test_short_or_stale_data_is_rejected_and_never_trades(self):
        for frame, reference in (
            (sample(119, "2026-08-21"), "2026-08-23"),
            (sample(500, "2026-06-01"), "2026-08-23"),
        ):
            with self.subTest(rows=len(frame), end=str(frame.iloc[-1]["time"])):
                result = analyze_symbol("TEST", frame, reference_date=reference)
                self.assertEqual(result["data_quality"]["data_quality"], "REJECT")
                self.assertEqual(result["final_signal"], "WATCH")
                self.assertEqual(result["system_action"], "CHỜ_XÁC_NHẬN")
                self.assertEqual(result["decision_grade"], "D")
                self.assertEqual(result["strategy_plan"]["status"], "NO_TRADE")


if __name__ == "__main__":
    unittest.main()
