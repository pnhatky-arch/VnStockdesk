import unittest
from datetime import datetime, timedelta, timezone
from src.bot_alerts import is_recent_alert


class BotAlertTests(unittest.TestCase):
    def test_only_recent_alerts_notify(self):
        now = datetime(2026, 8, 26, 8, 10, tzinfo=timezone.utc)
        for seconds, expected in ((0, True), (300, True), (301, False), (-1, False)):
            with self.subTest(seconds=seconds):
                self.assertEqual(is_recent_alert({"time": (now-timedelta(seconds=seconds)).isoformat()}, now), expected)

    def test_historical_trc_alert_does_not_replay(self):
        self.assertFalse(is_recent_alert({"time": "2026-08-26T07:49:22.810740+00:00"},
                                        datetime(2026, 8, 26, 8, 10, tzinfo=timezone.utc)))

    def test_missing_invalid_or_unzoned_timestamp_is_not_recent(self):
        for value in (None, "bad", "2026-08-26T08:10:00"):
            self.assertFalse(is_recent_alert({"time": value}))
