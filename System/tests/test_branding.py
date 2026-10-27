import plistlib
import unittest
from pathlib import Path

from src.branding import PROJECT_NAME
from src.i18n import LANGUAGES, tr


class BrandingTests(unittest.TestCase):
    def test_name_in_all_languages(self):
        self.assertEqual(PROJECT_NAME, "VnStockDesk")
        for language in LANGUAGES:
            self.assertEqual(tr(language, "brand_title"), PROJECT_NAME)

    def test_launchers_use_local_environment(self):
        root = Path(__file__).resolve().parents[1]
        for action in ("start", "stop"):
            source = (root / f"launcher_{action}.applescript").read_text()
            self.assertIn("path to me", source)
            self.assertIn("/.venv/bin/python", source)
            self.assertNotIn("/Downloads/", source)
            bundle = root / f"{action.upper()} VnStockDesk.app"
            with (bundle / "Contents/Info.plist").open("rb") as f:
                meta = plistlib.load(f)
            self.assertEqual(meta["CFBundleName"], f"{action.upper()} VnStockDesk")
            self.assertEqual(meta["CFBundleIdentifier"], f"com.nhatkypham.vnstockdesk.{action}.system")
