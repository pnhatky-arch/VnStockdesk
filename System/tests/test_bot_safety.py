from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from src.broker_adapter import LockedLiveBroker
from src.paper_broker import PaperBroker
from src.trading_engine import paper_cycle, paper_scope_cycle, position_size
from src.bot_manager import _alive, bot_status


def analysis(action: str, close: float = 50.0) -> dict:
    return {
        "system_action": action,
        "timeframes": {"1D": {"close": close}},
        "strategy_plan": {"stop_loss": close - 3, "target_1": close + 8},
    }


class BotSafetyTests(unittest.TestCase):
    def test_low_risk_requires_stronger_equity_confirmation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = pd.DataFrame({"close": [50.0]})
            weak = {**analysis("MUA_CÓ_XÁC_NHẬN"), "confidence": 74, "timeframe_alignment": 74}
            with patch("src.trading_engine.get_history", return_value=frame), patch(
                "src.trading_engine.analyze_symbol", return_value=weak
            ):
                result = paper_cycle(root, "FPT", risk_level="LOW")
            self.assertIsNone(result["order"])
            self.assertEqual(result["skip_code"], "RISK_PROFILE_THRESHOLD")

    def test_high_risk_can_promote_strong_watch_buy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = pd.DataFrame({"close": [50.0]})
            watch = {**analysis("THEO_DÕI_MUA"), "confidence": 65, "timeframe_alignment": 60}
            with patch("src.trading_engine.get_history", return_value=frame), patch(
                "src.trading_engine.analyze_symbol", return_value=watch
            ):
                result = paper_cycle(root, "FPT", risk_level="HIGH")
            self.assertEqual(result["order"]["side"], "BUY")
            self.assertEqual(result["risk_level"], "HIGH")

    def test_legacy_five_position_config_cannot_reenable_count_limit(self):
        from src.trading_config import TradingConfig
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = PaperBroker(root / "state" / "paper_portfolio.json", TradingConfig(max_positions=5))
            for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
                broker.buy(symbol, 100, 10)
            frame = pd.DataFrame({"close": [50.0]})
            with patch("src.trading_engine.PaperBroker", return_value=broker), patch(
                "src.trading_engine.get_history", return_value=frame
            ), patch("src.trading_engine.analyze_symbol", return_value=analysis("MUA_CÓ_XÁC_NHẬN")):
                result = paper_cycle(root, "TRC", fixed_buy_quantity=500)
            self.assertEqual(len(result["portfolio"]["positions"]), 7)
            self.assertEqual(result["order"]["quantity"], 500)
            with self.assertRaisesRegex(RuntimeError, "Không đủ tiền mặt"):
                broker.buy("CASH", 100_000_000, 50)

    def test_sixth_position_is_allowed_but_cash_and_sizing_still_apply(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = PaperBroker(root / "state" / "paper_portfolio.json")
            self.assertEqual(broker.config.max_positions, 0)
            for symbol in ("AAA","BBB","CCC","DDD","EEE"):
                broker.buy(symbol,100,10)
            frame = pd.DataFrame({"close":[50.0]})
            with patch("src.trading_engine.get_history",return_value=frame), patch("src.trading_engine.analyze_symbol",return_value=analysis("MUA_CÓ_XÁC_NHẬN")):
                result = paper_cycle(root,"FPT")
            self.assertEqual(len(result["portfolio"]["positions"]),6)
            self.assertEqual(result["order"]["side"],"BUY")
            self.assertLessEqual(result["order"]["quantity"]*50*1000, result["portfolio"]["equity_vnd"]*.21)

    def test_position_size_respects_lot_cash_and_position_cap(self):
        qty = position_size(100_000_000, 100_000_000, 50, 47)
        self.assertGreater(qty, 0)
        self.assertEqual(qty % 100, 0)
        self.assertLessEqual(qty * 50 * 1000, 20_000_000)

    def test_confirmed_buy_creates_paper_order_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = pd.DataFrame({"close": [50.0]})
            with patch("src.trading_engine.get_history", return_value=frame), patch(
                "src.trading_engine.analyze_symbol", return_value=analysis("MUA_CÓ_XÁC_NHẬN")
            ):
                result = paper_cycle(root, "FPT")
            self.assertEqual(result["mode"], "PAPER")
            self.assertEqual(result["order"]["side"], "BUY")
            self.assertIn("FPT", result["portfolio"]["positions"])

    def test_scope_bot_buys_exactly_500_shares(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = pd.DataFrame({"close": [50.0]})
            with patch("src.trading_engine.get_market_universe", return_value=["FPT"]), patch(
                "src.trading_engine.get_history", return_value=frame
            ), patch("src.trading_engine.analyze_symbol", return_value=analysis("MUA_CÓ_XÁC_NHẬN")):
                result = paper_scope_cycle(root, "VN30", fixed_buy_quantity=500)
            self.assertEqual(len(result["buy_orders"]), 1)
            self.assertEqual(result["buy_orders"][0]["quantity"], 500)
            self.assertEqual(result["portfolio"]["positions"]["FPT"]["quantity"], 500)

    def test_scope_bot_scans_selected_universe(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = pd.DataFrame({"close": [50.0]})
            with patch("src.trading_engine.get_market_universe", return_value=["FPT", "VNM"]), patch(
                "src.trading_engine.get_history", return_value=frame
            ), patch("src.trading_engine.analyze_symbol", return_value=analysis("NẮM_GIỮ")):
                result = paper_scope_cycle(root, "HOSE", fixed_buy_quantity=500)
            self.assertEqual(result["scope"], "HOSE")
            self.assertEqual(result["scanned"], 2)
            self.assertEqual(result["orders"], [])

    def test_scope_risk_rejection_creates_audible_dashboard_alert(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = pd.DataFrame({"close": [500.0]})
            with patch("src.trading_engine.get_market_universe", return_value=["FPT"]), patch(
                "src.trading_engine.get_history", return_value=frame
            ), patch("src.trading_engine.analyze_symbol", return_value=analysis("MUA_CÓ_XÁC_NHẬN", 500)):
                result = paper_scope_cycle(root, "VN30", fixed_buy_quantity=500)
            self.assertEqual(result["buy_orders"], [])
            self.assertEqual(result["results"][0]["skip_code"], "RISK_OR_WEIGHT_LIMIT")
            alerts = json.loads((root / "state" / "bot_alerts.json").read_text(encoding="utf-8"))
            self.assertEqual(alerts[-1]["symbol"], "FPT")
            self.assertIn("vượt tỷ trọng", alerts[-1]["reason"])

    def test_stop_loss_waits_for_t_plus_two_inventory(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = PaperBroker(root / "state" / "paper_portfolio.json")
            broker.buy("FPT", 100, 50, stop_loss=47)
            frame = pd.DataFrame({"close": [46.0]})
            with patch("src.trading_engine.get_history", return_value=frame), patch(
                "src.trading_engine.analyze_symbol", return_value=analysis("NẮM_GIỮ", 46)
            ):
                result = paper_cycle(root, "FPT")
            self.assertIsNone(result["order"])
            self.assertEqual(result["skip_code"], "T_PLUS_2_SELL_LOCK")
            self.assertIn("Stop Loss", result["skip_reason"])
            self.assertIn("FPT", result["portfolio"]["positions"])

    def test_equity_can_sell_after_t_plus_two_and_cash_settles_separately(self):
        with TemporaryDirectory() as tmp:
            broker = PaperBroker(Path(tmp) / "portfolio.json")
            tz = ZoneInfo("Asia/Ho_Chi_Minh")
            trade = datetime(2026, 9, 7, 10, 0, tzinfo=tz)  # Monday
            broker.buy("FPT", 100, 50, now=trade)
            self.assertEqual(broker.available_quantity("FPT", datetime(2026, 9, 9, 12, 59, tzinfo=tz)), 0)
            self.assertEqual(broker.available_quantity("FPT", datetime(2026, 9, 9, 13, 0, tzinfo=tz)), 100)
            order = broker.sell("FPT", 100, 55, now=datetime(2026, 9, 9, 13, 1, tzinfo=tz))
            self.assertEqual(order["settlement_cycle"], "T+2")
            self.assertGreater(broker.snapshot()["pending_cash_vnd"], 0)

    def test_daily_loss_lock_blocks_new_buy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state" / "paper_portfolio.json"
            broker = PaperBroker(state_path)
            broker.state["day_start_equity_vnd"] = 1_100_000_000
            broker._save()
            frame = pd.DataFrame({"close": [50.0]})
            with patch("src.trading_engine.get_history", return_value=frame), patch(
                "src.trading_engine.analyze_symbol", return_value=analysis("MUA_CÓ_XÁC_NHẬN")
            ):
                result = paper_cycle(root, "FPT")
            self.assertIsNone(result["order"])

    def test_live_gateway_remains_locked(self):
        with self.assertRaisesRegex(RuntimeError, "LIVE đang khóa"):
            LockedLiveBroker().submit_order("FPT", "BUY", 100, 50)

    def test_permission_error_does_not_mark_existing_pid_dead(self):
        with patch("src.bot_manager.os.kill", side_effect=PermissionError):
            self.assertTrue(_alive(12345))

    def test_split_data_root_resolves_system_worker(self):
        from src.bot_manager import _system_root
        with TemporaryDirectory() as tmp:
            desk = Path(tmp)
            data, system = desk / "Data", desk / "System"
            data.mkdir(); system.mkdir()
            (system / "market_bot.py").write_text("", encoding="utf-8")
            self.assertEqual(_system_root(data), system.resolve())

    def test_stale_heartbeat_is_not_running_even_if_pid_is_reused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "state" / "bot_process.json").write_text(
                json.dumps({"pid": 12345, "token": "same", "started_at": 1, "interval_minutes": 15}),
                encoding="utf-8",
            )
            (root / "state" / "bot_heartbeat.json").write_text(
                json.dumps({"token": "same", "updated_at": 1}), encoding="utf-8"
            )
            with patch("src.bot_manager._alive", return_value=True):
                self.assertFalse(bot_status(root)["running"])

    def test_corrupt_portfolio_falls_back_to_safe_initial_state(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "portfolio.json"
            path.write_text(json.dumps({"positions": []}), encoding="utf-8")
            broker = PaperBroker(path)
            self.assertEqual(broker.state["positions"], {})
            self.assertGreater(broker.state["cash_vnd"], 0)

    def test_set_cash_preserves_positions_and_history(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "portfolio.json"
            broker = PaperBroker(path)
            broker.buy("FPT", 100, 50, stop_loss=47)
            orders_before = list(broker.state["orders"])
            record = broker.set_cash_balance(250_000_000)
            self.assertEqual(broker.state["cash_vnd"], 250_000_000)
            self.assertIn("FPT", broker.state["positions"])
            self.assertEqual(broker.state["orders"], orders_before)
            self.assertEqual(record["type"], "SET_CASH")

    def test_reset_clears_positions_and_orders_with_selected_capital(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "portfolio.json"
            broker = PaperBroker(path)
            broker.buy("FPT", 100, 50, stop_loss=47)
            snapshot = broker.reset(500_000_000)
            self.assertEqual(snapshot["cash_vnd"], 500_000_000)
            self.assertEqual(snapshot["equity_vnd"], 500_000_000)
            self.assertEqual(snapshot["positions"], {})
            self.assertEqual(snapshot["orders"], [])
            self.assertEqual(snapshot["capital_adjustments"][-1]["type"], "RESET")

    def test_invalid_paper_capital_is_rejected(self):
        with TemporaryDirectory() as tmp:
            broker = PaperBroker(Path(tmp) / "portfolio.json")
            with self.assertRaises(ValueError):
                broker.set_cash_balance(999_999)

    def test_cash_adjustment_preserves_positions_and_orders(self):
        with TemporaryDirectory() as tmp:
            broker = PaperBroker(Path(tmp) / "portfolio.json")
            broker.buy("FPT", 100, 50)
            positions_before = dict(broker.state["positions"])
            orders_before = list(broker.state["orders"])
            broker.set_cash_balance(250_000_000)
            self.assertEqual(broker.state["cash_vnd"], 250_000_000)
            self.assertEqual(broker.state["positions"], positions_before)
            self.assertEqual(broker.state["orders"], orders_before)
            self.assertEqual(broker.state["capital_adjustments"][-1]["type"], "SET_CASH")

    def test_reset_clears_paper_positions_and_history(self):
        with TemporaryDirectory() as tmp:
            broker = PaperBroker(Path(tmp) / "portfolio.json")
            broker.buy("FPT", 100, 50)
            snapshot = broker.reset(500_000_000)
            self.assertEqual(snapshot["cash_vnd"], 500_000_000)
            self.assertEqual(snapshot["equity_vnd"], 500_000_000)
            self.assertEqual(snapshot["positions"], {})
            self.assertEqual(snapshot["orders"], [])
            self.assertEqual(snapshot["capital_adjustments"][-1]["type"], "RESET")

    def test_invalid_paper_capital_is_rejected(self):
        with TemporaryDirectory() as tmp:
            broker = PaperBroker(Path(tmp) / "portfolio.json")
            with self.assertRaises(ValueError):
                broker.set_cash_balance(0)


if __name__ == "__main__":
    unittest.main()
