import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from src.data_jobs import DataJobs, alive
from src.local_io import _local_lock_path, atomic_csv, atomic_json, read_json
from src.paths import DATA_DIR, DATA_ROOT, MARKET_DIR, PRIVATE_DIR, PROJECT_ROOT, RUNTIME_DIR, STATE_DIR


class StorageLayoutTests(unittest.TestCase):
    def test_data_job_uses_shared_process_liveness_check(self):
        with patch("src.data_jobs.process_alive", return_value=True) as checker:
            self.assertTrue(alive(12345))
        checker.assert_called_once_with(12345)

    def test_system_and_data_are_separate_siblings(self):
        self.assertEqual(PROJECT_ROOT.name, "System")
        self.assertEqual(DATA_ROOT, PROJECT_ROOT.parent / "Data")
        self.assertEqual(MARKET_DIR, DATA_ROOT / "market")
        self.assertEqual(PRIVATE_DIR, DATA_ROOT / "private")
        self.assertEqual(STATE_DIR, PRIVATE_DIR / "state")
        self.assertNotEqual(RUNTIME_DIR, DATA_ROOT / "runtime")
        self.assertTrue(RUNTIME_DIR.is_absolute())

    def test_job_checkpoint_can_pause_and_resume_without_process(self):
        with TemporaryDirectory() as folder:
            manager = DataJobs(Path(folder))
            manager.start({"scope":"VN30", "mode":"missing", "components":["prices"]}, launch=False)
            result = manager.run(lambda job:[{"key":"ACB:prices","symbol":"ACB","kind":"prices"}], lambda task,job:None)
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["done"], ["ACB:prices"])

    def test_resumed_job_rebinds_synced_checkpoint_to_current_machine_data(self):
        with TemporaryDirectory() as folder:
            manager = DataJobs(Path(folder))
            manager.start({"scope":"VN30", "mode":"missing", "components":["prices"]}, launch=False)
            job = read_json(manager.path)
            job.update(status="PAUSED", data_dir="C:\\stale-machine\\Data\\market")
            atomic_json(manager.path, job)
            resumed = manager.start(resume=True, launch=False)
            self.assertEqual(resumed["data_dir"], str(DATA_DIR))

    def test_atomic_csv_survives_concurrent_writers(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "ACB.csv"
            frames = [pd.DataFrame({"value":[number]}) for number in range(20)]
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda frame: atomic_csv(path, frame), frames))
            result = pd.read_csv(path)
            self.assertEqual(len(result), 1)
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    def test_google_drive_lock_is_kept_in_local_runtime(self):
        cloud_lock = Path("/Users/example/Drive của tôi/VnStockDesk/Data/market/raw/ACB.csv.lock")
        local_lock = _local_lock_path(cloud_lock)
        self.assertNotEqual(local_lock, cloud_lock)
        self.assertEqual(local_lock.parent.name, "locks")
        self.assertTrue(local_lock.name.endswith(".lock"))


if __name__ == "__main__":
    unittest.main()
