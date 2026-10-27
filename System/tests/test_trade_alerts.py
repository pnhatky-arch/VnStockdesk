import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import trade_alerts


class TradeAlertTests(unittest.TestCase):
    def test_alert_stays_pending_until_explicit_dismissal(self):
        with TemporaryDirectory() as tmp, patch.object(trade_alerts, "STATE_DIR", Path(tmp)):
            order = {"time":"2026-09-04T09:00:00+07:00", "side":"BUY", "quantity":500,
                     "price":20.875, "status":"FILLED"}
            first = trade_alerts.record_fill(order, "PAPER", "FPT", "equity")
            duplicate = trade_alerts.record_fill(order, "PAPER", "FPT", "equity")
            self.assertEqual(first["id"], duplicate["id"])
            self.assertEqual(trade_alerts.pending_fill()["id"], first["id"])
            trade_alerts.dismiss_fill(first["id"])
            self.assertIsNone(trade_alerts.pending_fill())

    def test_non_filled_order_is_ignored(self):
        with TemporaryDirectory() as tmp, patch.object(trade_alerts, "STATE_DIR", Path(tmp)):
            self.assertIsNone(trade_alerts.record_fill({"status":"REJECTED"}, "PAPER", "FPT", "equity"))

    def test_recent_ledger_fill_is_recovered_for_existing_workers(self):
        with TemporaryDirectory() as tmp, patch.object(trade_alerts, "STATE_DIR", Path(tmp) / "runtime"):
            state_dir = Path(tmp) / "state"
            state_dir.mkdir()
            order = {"time": datetime.now(timezone.utc).isoformat(), "side":"BUY", "quantity":500,
                     "price":20.875, "status":"FILLED", "symbol":"FPT"}
            (state_dir / "paper_portfolio.json").write_text(json.dumps({"orders":[order]}))
            recovered = trade_alerts.sync_latest_fill_from_ledgers(state_dir)
            self.assertEqual(recovered["symbol"], "FPT")
            self.assertEqual(trade_alerts.pending_fill()["order"]["quantity"], 500)


if __name__ == "__main__":
    unittest.main()
