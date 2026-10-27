from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.futures_broker import PaperFuturesBroker
from src.futures_engine import FuturesRiskConfig, analyze_vn30f1m, position_size
from src.futures_trading_engine import futures_paper_cycle, session_state


def frame(periods: int, start: float, step: float, freq: str) -> pd.DataFrame:
    close = start + np.arange(periods) * step
    return pd.DataFrame({
        "time": pd.date_range(end=pd.Timestamp.now().floor("min"), periods=periods, freq=freq),
        "open": close - step * .3, "high": close + 1.2, "low": close - 1.2,
        "close": close, "volume": np.linspace(10_000, 30_000, periods),
    })


class FuturesSystemTests(unittest.TestCase):
    def test_position_size_respects_risk_and_margin(self):
        cfg = FuturesRiskConfig(risk_per_trade=.005, target_margin_utilization=.30)
        sized = position_size(1_000_000_000, 1900, 4, cfg)
        self.assertEqual(sized["contracts"], min(sized["by_risk"], sized["by_margin"]))
        self.assertLessEqual(sized["estimated_max_loss_vnd"], 5_000_000)
        self.assertLessEqual(sized["estimated_margin_vnd"], 300_000_000)

    def test_trend_engine_builds_long_plan_with_bounded_stop(self):
        frames = {
            "15M": frame(260, 1750, .45, "15min"),
            "1H": frame(260, 1650, 1.1, "h"),
            "1D": frame(260, 1300, 2.2, "D"),
        }
        result = analyze_vn30f1m(frames)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["action"], "LONG")
        self.assertGreaterEqual(result["stop_points"], 2)
        self.assertLessEqual(result["stop_points"], 4)
        self.assertLess(result["plan"]["stop_loss"], result["plan"]["entry_low"])
        self.assertLessEqual(result["plan"]["entry_high"], result["plan"]["trigger"])
        self.assertLess(result["plan"]["trigger"], result["plan"]["target_1"])
        self.assertLess(result["plan"]["target_1"], result["plan"]["target_2"])
        for tf in ("15M", "1H", "1D"):
            self.assertIn("wyckoff_event", result["frames"][tf])
            self.assertIn("wyckoff_phase", result["frames"][tf])
            self.assertIn("wyckoff_bias", result["frames"][tf])
            self.assertEqual(result["frames"][tf]["fibonacci"]["status"], "OK")
            self.assertIn("0.618", result["frames"][tf]["fibonacci"]["levels"])
            self.assertIn("1.618", result["frames"][tf]["fibonacci"]["extensions"])
            self.assertIn("direction_source", result["frames"][tf]["fibonacci"])

    def test_paper_futures_long_and_short_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            broker = PaperFuturesBroker(Path(tmp) / "futures.json", 1_000_000_000)
            broker.open("LONG", 2, 1900, 1896, 1908)
            self.assertEqual(broker.snapshot(1903)["unrealized_pnl_vnd"], 600_000)
            broker.close(1903)
            self.assertEqual(broker.snapshot(1903)["side"], "FLAT")
            broker.open("SHORT", 1, 1900, 1904, 1892)
            self.assertEqual(broker.snapshot(1897)["unrealized_pnl_vnd"], 300_000)
            report = broker.performance_report(1897)
            self.assertEqual(report["realized_pnl_vnd"], 600_000)
            self.assertEqual(report["unrealized_pnl_vnd"], 300_000)
            self.assertEqual(report["total_pnl_vnd"], 900_000)
            self.assertEqual(report["capital_before_pnl_vnd"], 1_000_000_000)
            self.assertEqual(report["equity_after_total_vnd"], 1_000_900_000)
            self.assertEqual(report["closed_trades"], 1)
            self.assertEqual(report["win_rate_pct"], 100)

    def test_daily_trade_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FuturesRiskConfig(max_trades_per_day=1)
            broker = PaperFuturesBroker(Path(tmp) / "futures.json", config=cfg)
            broker.open("LONG", 1, 1900, 1896, 1908); broker.close(1901)
            with self.assertRaises(RuntimeError):
                broker.open("LONG", 1, 1900, 1896, 1908)

    def test_session_policy_blocks_lunch_and_allows_morning(self):
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        self.assertTrue(session_state(datetime(2026, 8, 24, 9, 0, tzinfo=tz))["entry_window"])
        self.assertFalse(session_state(datetime(2026, 8, 24, 12, 0, tzinfo=tz))["entry_window"])
        self.assertTrue(session_state(datetime(2026, 8, 24, 14, 30, tzinfo=tz))["force_close"])

    def test_auto_cycle_opens_only_in_entry_window(self):
        frames = {"15M": frame(260, 1750, .45, "15min"), "1H": frame(260, 1650, 1.1, "h"), "1D": frame(260, 1300, 2.2, "D")}
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        with tempfile.TemporaryDirectory() as tmp:
            result = futures_paper_cycle(Path(tmp), now=datetime(2026, 8, 24, 9, 0, tzinfo=tz), frames=frames)
            self.assertEqual(result["bot_action"], "OPEN_LONG")
            self.assertEqual(result["account"]["side"], "LONG")


if __name__ == "__main__":
    unittest.main()
