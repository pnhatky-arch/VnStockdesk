"""Bounded, non-blocking provider reads for dashboard rendering only.

No Streamlit calls or order execution in workers. A hung provider consumes one
slot, never queues unlimited work or blocks the render thread.
"""
from copy import deepcopy
import threading
import time


class BackgroundReads:
    def __init__(self, max_workers=6, clock=time.monotonic):
        self._lock = threading.Lock()
        self._jobs = {}
        self._max_workers = max_workers
        self._clock = clock

    def poll(self, key, loader, *, ttl=300, force=False):
        with self._lock:
            job = self._jobs.setdefault(key, {"running": False, "value": None, "done": None, "error": None})
            due = job["done"] is None or self._clock() - job["done"] >= ttl or force
            if due and not job["running"] and sum(j["running"] for j in self._jobs.values()) < self._max_workers:
                job["running"] = True
                threading.Thread(target=self._run, args=(job, loader), daemon=True, name="dashboard-provider-read").start()
            return deepcopy({"value": job["value"], "running": job["running"],
                             "error": job["error"], "done": job["done"]})

    def _run(self, job, loader):
        try:
            value = loader()
        except BaseException as exc:
            # Some provider libraries raise SystemExit; never terminate the UI.
            with self._lock:
                job.update(running=False, done=self._clock(), error=f"{type(exc).__name__}: {exc}")
        else:
            with self._lock:
                job.update(value=value, running=False, done=self._clock(), error=None)
