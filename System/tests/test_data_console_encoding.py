import unittest
from unittest.mock import patch

from src import data


class _Console:
    def __init__(self, encoding):
        self.encoding = encoding
        self.reconfigured = []

    def reconfigure(self, **kwargs):
        self.reconfigured.append(kwargs)
        self.encoding = kwargs["encoding"]


class DataConsoleEncodingTests(unittest.TestCase):
    def test_cp1252_console_is_reconfigured_for_vnstock_vietnamese_messages(self):
        stdout = _Console("cp1252")
        stderr = _Console("cp1252")
        with patch.object(data.sys, "stdout", stdout), patch.object(data.sys, "stderr", stderr):
            data._ensure_utf8_console()

        self.assertEqual(stdout.reconfigured, [{"encoding": "utf-8", "errors": "backslashreplace"}])
        self.assertEqual(stderr.reconfigured, [{"encoding": "utf-8", "errors": "backslashreplace"}])

    def test_utf8_console_is_not_reconfigured_again(self):
        stdout = _Console("utf-8")
        stderr = _Console("utf_8")
        with patch.object(data.sys, "stdout", stdout), patch.object(data.sys, "stderr", stderr):
            data._ensure_utf8_console()

        self.assertEqual(stdout.reconfigured, [])
        self.assertEqual(stderr.reconfigured, [])


if __name__ == "__main__":
    unittest.main()
