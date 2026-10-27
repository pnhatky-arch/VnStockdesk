import unittest

from src.risk_profiles import RISK_PROFILES, normalize_risk_profile


class RiskProfileTests(unittest.TestCase):
    def test_profiles_cover_every_paper_risk_selector_value(self):
        self.assertEqual(set(RISK_PROFILES), {"LOW", "MEDIUM", "HIGH"})
        self.assertEqual(normalize_risk_profile("medium"), "MEDIUM")

    def test_profile_sizing_is_bounded_and_low_is_more_conservative(self):
        self.assertLess(RISK_PROFILES["LOW"]["risk_multiplier"], 1)
        self.assertLess(RISK_PROFILES["LOW"]["position_multiplier"], 1)
        self.assertEqual(RISK_PROFILES["MEDIUM"]["risk_multiplier"], 1)
        self.assertTrue(RISK_PROFILES["HIGH"]["allow_watch_buy"])


if __name__ == "__main__":
    unittest.main()
