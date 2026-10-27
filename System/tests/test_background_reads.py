import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from src.background_reads import BackgroundReads
from src.futures_data import load_futures_bundle


class BackgroundReadsTests(unittest.TestCase):
    def test_stalled_provider_never_blocks_or_duplicates(self):
        gate = threading.Event()
        entered = threading.Event()
        calls = []
        def loader():
            calls.append(1)
            entered.set()
            gate.wait(2)
            return {"price": 123}
        reads = BackgroundReads(max_workers=1)
        try:
            start = time.monotonic()
            self.assertIsNone(reads.poll("one", loader)["value"])
            self.assertLess(time.monotonic()-start, .25)
            self.assertTrue(entered.wait(1))
            for _ in range(20):
                self.assertTrue(reads.poll("one", loader, force=True)["running"])
            self.assertFalse(reads.poll("two", loader)["running"])
            self.assertEqual(len(calls), 1)
        finally:
            gate.set()

    def wait_done(self, reads, key, loader):
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            state = reads.poll(key, loader)
            if state["done"] is not None and not state["running"]:
                return state
            threading.Event().wait(.005)
        self.fail("Worker did not complete")

    def test_result_is_copied_and_error_retains_last_value(self):
        reads = BackgroundReads()
        loader = lambda: {"price": 123}
        state = self.wait_done(reads, "one", loader)
        state["value"]["price"] = 0
        self.assertEqual(reads.poll("one", loader)["value"]["price"],123)
        def failed():
            raise SystemExit("Provider failed")
        reads.poll("one", failed, force=True)
        state = self.wait_done(reads, "one", failed)
        self.assertEqual(state["value"]["price"],123)
        self.assertIn("Provider failed",state["error"])

    def test_ttl_does_not_restart_recent_read(self):
        now = [0]
        reads = BackgroundReads(clock=lambda: now[0])
        loader = Mock(return_value={"price":123})
        self.wait_done(reads,"one",loader)
        now[0] = 299
        reads.poll("one",loader,ttl=300)
        self.assertEqual(loader.call_count,1)
        now[0] = 301
        reads.poll("one",loader,ttl=300)
        self.wait_done(reads,"one",loader)
        self.assertEqual(loader.call_count,2)

    def test_cache_only_never_calls_provider_or_rewrites_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"vn30f1m_1d.csv"
            data = pd.DataFrame({"time":["2026-08-26"],"open":[1900],"high":[1910],"low":[1890],"close":[1905],"volume":[500]})
            data.to_csv(path,index=False)
            original = path.read_bytes()
            provider = Mock(side_effect=AssertionError("Network must not run"))
            frames,meta = load_futures_bundle(Path(tmp),market_factory=provider,cache_only=True)
            provider.assert_not_called()
            self.assertEqual(frames["1D"].iloc[-1]["close"],1905)
            self.assertEqual(meta["1D"]["source"],"CACHE")
            self.assertEqual(meta["15M"]["source"],"UNAVAILABLE")
            self.assertEqual(path.read_bytes(),original)
