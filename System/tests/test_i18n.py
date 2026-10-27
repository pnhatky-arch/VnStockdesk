import unittest

from src.i18n import LANGUAGES, T, tr


class InternationalizationTests(unittest.TestCase):
    def test_five_supported_languages_have_flags(self):
        self.assertEqual(set(LANGUAGES), {"vi", "en", "zh", "ru", "de"})
        flags = {"🇻🇳", "🇬🇧", "🇨🇳", "🇷🇺", "🇩🇪"}
        self.assertTrue(all(label.split()[0] in flags for label in LANGUAGES.values()))

    def test_all_languages_cover_vietnamese_ui_keys(self):
        reference = set(T["vi"])
        for language in LANGUAGES:
            self.assertEqual(set(T[language]), reference, language)

    def test_formatting_and_fallback(self):
        self.assertIn("1 day", tr("en", "candle", period="1 day"))
        self.assertEqual(tr("unknown", "market"), T["vi"]["market"])


if __name__ == "__main__":
    unittest.main()
