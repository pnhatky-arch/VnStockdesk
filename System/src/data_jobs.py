"""Resumable market-data initialization. Never imports an order executor."""
from __future__ import annotations
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from .local_io import atomic_json, read_json, file_lock
from .paths import PROJECT_ROOT, STATE_DIR, DATA_DIR, PRIVATE_DIR, RUNTIME_DIR, STORAGE_CONFIG, validate_data_root
from .process_utils import process_alive

SCOPES = ("VN30", "VN100", "HOSE", "HNX", "UPCOM", "ALL", "FAVORITES")
COMPONENTS = ("prices", "news", "valuation", "futures")
MODES = ("initial", "missing", "update")


def alive(pid):
    """Return whether *pid* is active without using unsupported Windows signals."""
    return process_alive(pid)


class DataJobs:
    def __init__(self, directory=None):
        self.directory = Path(directory or STATE_DIR / "data_jobs")
        self.path = self.directory / "current.json"

    def status(self):
        job = read_json(self.path)
        if job.get("status") in ("RUNNING", "QUEUED", "PAUSING") and not alive(job.get("pid")) and time.time()-job.get("updated_at",0)>10:
            job = {**job, "status": "INTERRUPTED", "message": "Tiến trình đã dừng; có thể tiếp tục từ checkpoint."}
        return job

    def start(self, config=None, *, resume=False, launch=True):
        with file_lock(self.directory / "manager.lock"):
            old = self.status()
            if old.get("status") in ("RUNNING", "QUEUED", "PAUSING"):
                raise ValueError("Một tác vụ đang chạy. Tạm dừng trước khi tạo tác vụ khác.")
            if resume:
                if not old or old.get("status") == "COMPLETE":
                    raise ValueError("Không có tác vụ dang dở để tiếp tục.")
                job = old
                job["errors"] = []
                # A checkpoint may have been created on another synced machine.
                # Always bind resumed work to this machine's active data path.
                job["data_dir"] = str(DATA_DIR)
            else:
                config = config or {}
                scope, mode = config.get("scope", "VN30"), config.get("mode", "missing")
                components = list(dict.fromkeys(config.get("components", COMPONENTS)))
                if scope not in SCOPES or mode not in MODES or not components or any(x not in COMPONENTS for x in components):
                    raise ValueError("Phạm vi, chế độ hoặc nhóm dữ liệu không hợp lệ.")
                if old:
                    atomic_json(self.directory / f"history-{old['id']}.json", old)
                job = {"id":uuid.uuid4().hex,"scope":scope,"mode":mode,"components":components,
                       "data_dir":str(DATA_DIR),"tasks":[],"done":[],"errors":[],"analysis":{},"created_at":time.time()}
            job.update(status="QUEUED", pid=None, updated_at=time.time(), message="Đang chuẩn bị danh sách mã…")
            atomic_json(self.directory / "control.json", {"pause":False})
            atomic_json(self.path, job)
            if launch:
                # The worker inherits the selected storage; it cannot affect the baseline.
                env = {**os.environ, "VNSTOCKDESK_MARKET_DIR":job["data_dir"]}
                process_options = (
                    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                    if os.name == "nt" else {"start_new_session": True}
                )
                with (self.directory / "worker.log").open("a") as log:
                    process = subprocess.Popen([sys.executable, "-u", str(PROJECT_ROOT / "data_init_worker.py"), str(self.directory)],
                        cwd=PROJECT_ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        close_fds=True, **process_options)
                # Worker owns its state once started; do not race its atomic write.
            return job

    def pause(self):
        with file_lock(self.directory / "manager.lock"):
            atomic_json(self.directory / "control.json", {"pause":True})
        return {**self.status(), "message":"Đã yêu cầu tạm dừng; chờ lượt tải hiện tại kết thúc."}

    def run(self, discover, perform):
        with file_lock(self.directory / "worker.lock"):
            job = read_json(self.path)
            if not job:
                raise ValueError("Không có cấu hình tác vụ.")
            def save(**values):
                job.update(values, updated_at=time.time()); atomic_json(self.path, job)
            try:
                save(status="RUNNING", pid=os.getpid())
                if not job["tasks"]:
                    save(tasks=discover(job))
                    if not job["tasks"]:
                        raise ValueError("Nguồn không trả về mã nào; không báo hoàn tất giả.")
                completed = set(job["done"])
                for task in job["tasks"]:
                    key = task["key"]
                    if key in completed:
                        continue
                    if read_json(self.directory / "control.json").get("pause"):
                        save(status="PAUSED", message="Đã tạm dừng. Các mục hoàn tất được giữ nguyên."); return job
                    save(current=key, message=f"Đang tải {key}")
                    try:
                        result = perform(task, job)
                        if task["kind"] == "analysis":
                            job["analysis"][task["symbol"]] = result
                        job["done"].append(key); completed.add(key)
                    except (Exception, SystemExit) as exc:
                        job["errors"].append({"task":key,"error":f"{type(exc).__name__}: {str(exc)[:350]}"})
                    save()
                save(status="PARTIAL" if job["errors"] else "COMPLETE", current=None,
                     message="Có mục lỗi; bấm Tiếp tục để thử lại." if job["errors"] else "Hoàn tất các mục nguồn có thể cung cấp.")
            except (Exception, SystemExit) as exc:
                save(status="FAILED", message=f"{type(exc).__name__}: {str(exc)[:350]}")
            return job


def discover_tasks(job):
    from .universe import get_market_universe
    symbols = get_market_universe(job["scope"])
    tasks = []
    for symbol in symbols:
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", symbol):
            continue
        for kind in [x for x in job["components"] if x != "futures"] + ["analysis"]:
            tasks.append({"key":f"{symbol}:{kind}","symbol":symbol,"kind":kind})
    if "futures" in job["components"]:
        from .futures_data import load_futures_contracts
        contracts, meta = load_futures_contracts()
        if meta.get("provider") == "FALLBACK":
            raise ValueError("Không tải được danh sách hợp đồng hiện hành; thử lại sau.")
        for contract in contracts:
            for tf in ("15M", "1H", "1D"):
                tasks.append({"key":f"{contract['symbol']}:{tf}","symbol":contract["symbol"],"kind":"futures","timeframe":tf})
    return tasks


def perform_task(task, job):
    import pandas as pd
    from .paths import RAW_DIR, NEWS_DIR
    symbol, kind, mode = task["symbol"], task["kind"], job["mode"]
    if kind == "prices":
        from .data import get_history, refresh_history_incremental, normalize_ohlcv
        path = RAW_DIR / f"{symbol}.csv"
        if mode == "missing" and path.exists() and not normalize_ohlcv(pd.read_csv(path)).empty:
            return
        frame = refresh_history_incremental(symbol) if mode == "update" else get_history(symbol, refresh=True)
        if frame.empty: raise ValueError("Không có OHLCV")
    elif kind == "news":
        from .news import fetch_company_news, _read_cached_news
        existing, meta = _read_cached_news(symbol)
        if mode == "missing" and meta.get("fetched_at"):
            return
        _, error = fetch_company_news(symbol, refresh=True)
        if error: raise ValueError(error)
    elif kind == "valuation":
        from .valuation import fetch_valuation, CACHE_DIR
        if mode == "missing" and read_json(CACHE_DIR / f"{symbol}.json").get("history"):
            return
        value = fetch_valuation(symbol, refresh=True)
        if value.get("fetch_error") or not value.get("history"):
            raise ValueError("Nguồn chưa cung cấp lịch sử định giá; không nội suy dữ liệu thiếu.")
    elif kind == "futures":
        from .futures_data import load_futures_timeframe
        frame, meta = load_futures_timeframe(task["timeframe"], RAW_DIR / "futures", symbol=symbol, cache_only=mode=="missing")
        if mode == "missing" and not frame.empty:
            return
        if mode == "missing":
            frame, meta = load_futures_timeframe(task["timeframe"], RAW_DIR / "futures", symbol=symbol, refresh=True)
        if frame.empty or meta["source"] != "ONLINE":
            raise ValueError(meta.get("error") or "Không lấy được nến mới từ nguồn")
    elif kind == "analysis":
        from .data import normalize_ohlcv, cache_diagnostics
        from .analyzer import analyze_symbol, flatten_analysis
        from .valuation import CACHE_DIR, assess_valuation, attach_valuation, valuation_columns
        frame = normalize_ohlcv(pd.read_csv(RAW_DIR / f"{symbol}.csv"))
        if len(frame)<20: raise ValueError("Chưa đủ 20 nến để phân tích")
        result = analyze_symbol(symbol, frame)
        row = flatten_analysis(result)
        info = cache_diagnostics(frame)
        row.update(data_quality=info["data_quality"], data_end=info["end"], data_rows=info["rows"], market_scope=job["scope"])
        snapshot = read_json(CACHE_DIR / f"{symbol}.json")
        peers = [read_json(p) for p in CACHE_DIR.glob("*.json") if p.stem != "sectors"]
        row.update(valuation_columns(attach_valuation(result, assess_valuation(snapshot, peers))))
        return row


def configure_next_data_directory(value):
    target = validate_data_root(value)
    for protected in (PRIVATE_DIR, RUNTIME_DIR):
        if target == protected or target.is_relative_to(protected) or protected.is_relative_to(target):
            raise ValueError("Không chọn thư mục riêng tư hoặc môi trường Python.")
    if DataJobs().status().get("status") in ("RUNNING", "QUEUED"):
        raise ValueError("Tạm dừng tác vụ tải trước khi thay đổi thư mục.")
    target.mkdir(parents=True, exist_ok=True)
    if target != DATA_DIR and any(target.iterdir()):
        raise ValueError("Chọn thư mục trống để tránh trộn dữ liệu.")
    atomic_json(STORAGE_CONFIG, {"market_dir":str(target)})
    return "Đã khởi tạo và lưu thư mục dữ liệu. Khởi động lại hệ thống để áp dụng; dữ liệu cũ không bị xoá."
