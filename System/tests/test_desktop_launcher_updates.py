import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DesktopLauncherUpdateTests(unittest.TestCase):
    def test_synced_source_change_restarts_managed_dashboard(self):
        source = (ROOT / "desktop_launcher.py").read_text(encoding="utf-8")
        self.assertIn("from src.paths import RUNTIME_DIR", source)
        self.assertIn('PID_PATH = RUNTIME_DIR / "dashboard_process.json"', source)
        self.assertNotIn('PID_PATH = STATE_DIR', source)
        self.assertIn("def _source_signature()", source)
        self.assertIn('state.get("source_signature") == source_signature', source)
        self.assertIn('"source_signature": source_signature', source)
        self.assertIn("def _replace_legacy_mac_dashboard()", source)
        self.assertIn('PORT = int(os.getenv("VNSTOCKDESK_PORT"', source)
        self.assertIn('["lsof", f"-tiTCP:{PORT}", "-sTCP:LISTEN"]', source)
        self.assertIn('legacy_root.parent.name != "VnStockDesk"', source)
        self.assertIn('"--server.fileWatcherType", "poll"', source)


if __name__ == "__main__":
    unittest.main()
