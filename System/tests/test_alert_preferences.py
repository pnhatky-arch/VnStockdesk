from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import alert_preferences


class AlertPreferencesTests(unittest.TestCase):
    def test_enabling_push_requests_a_visual_and_audio_check(self):
        app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertIn("st.session_state.push_notification_test_pending = True", app_source)
        self.assertIn('def render_push_notification_test()', app_source)
        self.assertIn('_play_trade_alert_sound()', app_source)
        self.assertIn('THÔNG BÁO ĐẨY ĐÃ BẬT', app_source)
        self.assertIn('def _repeating_trade_alert_sound(', app_source)
        self.assertIn('window.setInterval(play,', app_source)
        self.assertIn('push-test-button-spacer', app_source)

    def test_push_notifications_default_on_and_persist_toggle(self):
        with TemporaryDirectory() as tmp, patch.object(alert_preferences, "STATE_DIR", Path(tmp)):
            self.assertTrue(alert_preferences.load_alert_preferences()["push_enabled"])
            alert_preferences.set_push_enabled(False)
            self.assertFalse(alert_preferences.load_alert_preferences()["push_enabled"])
            alert_preferences.set_push_enabled(True)
            self.assertTrue(alert_preferences.load_alert_preferences()["push_enabled"])

    def test_custom_sound_is_stored_and_can_be_reset(self):
        with TemporaryDirectory() as tmp, patch.object(alert_preferences, "STATE_DIR", Path(tmp)):
            self.assertTrue(alert_preferences.save_alert_sound("notice.mp3", b"ID3-test"))
            path, name = alert_preferences.selected_alert_sound()
            self.assertEqual(name, "notice.mp3")
            self.assertEqual(path.read_bytes(), b"ID3-test")
            alert_preferences.reset_alert_sound()
            self.assertEqual(alert_preferences.selected_alert_sound(), (None, "Bốn kênh"))

    def test_custom_sound_rejects_unsupported_extension(self):
        with TemporaryDirectory() as tmp, patch.object(alert_preferences, "STATE_DIR", Path(tmp)):
            with self.assertRaises(ValueError):
                alert_preferences.save_alert_sound("notice.exe", b"bad")


if __name__ == "__main__":
    unittest.main()
