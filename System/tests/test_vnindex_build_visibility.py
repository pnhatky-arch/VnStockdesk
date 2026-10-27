import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class VNIndexBuildVisibilityTests(unittest.TestCase):
    def test_build_marker_and_windows_verifier_exist(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        verifier = (ROOT / "VERIFY_AND_RESTART_WINDOWS.cmd").read_text(encoding="utf-8")
        self.assertIn('BUILD_ID = "VNINDEX-20260903-1123"', app)
        self.assertIn("VNINDEX-20260903-1123", verifier)
        self.assertIn("STOP_VnStockDesk.cmd", verifier)
        self.assertIn("START_VnStockDesk.cmd", verifier)

    def test_workers_are_launched_from_system_not_data(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("ROOT = PROJECT_ROOT", app)
        self.assertNotIn("ROOT = PROCESSED_DIR.parent.parent", app)

    def test_filled_order_alert_is_persistent_and_audible(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('@st.dialog("THÔNG BÁO KHỚP LỆNH"', app)
        self.assertIn('st.container(key="trade_fill_overlay")', app)
        self.assertIn("@st.fragment(run_every=1)\ndef watch_trade_fill_alert", app)
        self.assertIn("(523.25, 659.25, 783.99, 1046.50)", app)
        self.assertIn('st.audio(tone, sample_rate=sample_rate, autoplay=True', app)
        self.assertIn('details.button("Xem chi tiết lệnh"', app)
        self.assertIn('"Tắt thông báo",', app)
        self.assertIn("_dismiss_trade_fill_alert(event_id)", app)
        self.assertIn("st.rerun()", app)


if __name__ == "__main__":
    unittest.main()
