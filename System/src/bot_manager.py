from __future__ import annotations

import json, os, secrets, signal, subprocess, sys, time
from pathlib import Path
from .paths import PROJECT_ROOT, RUNTIME_DIR, state_dir as storage_state_dir
from .process_utils import process_alive


def _system_root(root: Path) -> Path:
    """Resolve the executable folder across both legacy and split layouts."""
    candidate = Path(root).resolve()
    if (candidate / "market_bot.py").is_file():
        return candidate
    sibling = candidate.parent / "System"
    if (sibling / "market_bot.py").is_file():
        return sibling.resolve()
    return candidate


def _runtime_state_dir(root: Path) -> Path:
    root = _system_root(root)
    return RUNTIME_DIR / "bot_state" if root == PROJECT_ROOT.resolve() else storage_state_dir(root)


def cleanup_legacy_bot_workers(root: Path) -> list[int]:
    """Stop orphan workers launched before the System/Data migration."""
    try:
        import psutil
    except ImportError:
        return []
    root = Path(root).resolve(); stopped = []
    legacy_cwds = {root.parent.resolve(), (root.parent / "Data").resolve()}
    try:
        workers = psutil.process_iter(["pid", "cmdline", "cwd"])
        # On sandboxed macOS, process_iter can fail while obtaining the PID
        # list, before iteration begins. Materialize inside the protected block.
        workers = list(workers)
    except (PermissionError, OSError, psutil.AccessDenied):
        return []
    for worker in workers:
        try:
            if worker.pid == os.getpid(): continue
            command = " ".join(worker.info.get("cmdline") or [])
            cwd = Path(worker.info.get("cwd") or "/").resolve()
            if cwd in legacy_cwds and ("market_bot.py" in command or "futures_bot.py" in command):
                worker.terminate(); stopped.append(worker.pid)
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, ValueError):
            continue
    return stopped


def _read(path: Path) -> dict:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError): return {}


def _alive(pid: int) -> bool:
    return process_alive(pid)


def bot_status(root: Path) -> dict:
    root = _system_root(root)
    state_root = _runtime_state_dir(root)
    state = _read(state_root / "bot_process.json")
    heartbeat = _read(state_root / "bot_heartbeat.json")
    pid = int(state.get("pid", 0) or 0)
    token_valid = bool(state.get("token") and heartbeat.get("token") == state.get("token"))
    now = time.time()
    heartbeat_age = now - float(heartbeat.get("updated_at", 0) or 0)
    stale_after = max(120.0, float(state.get("interval_minutes", 30) or 30) * 60 * 2.5)
    heartbeat_fresh = token_valid and 0 <= heartbeat_age <= stale_after
    starting = now - float(state.get("started_at", 0) or 0) < 20
    running = _alive(pid) and (heartbeat_fresh or starting)
    return {**state, "running": running, "heartbeat": heartbeat, "token_valid": token_valid,
            "heartbeat_age_seconds": round(heartbeat_age, 1), "heartbeat_fresh": heartbeat_fresh}


def start_bot(root: Path, interval: int, symbol: str | None = None, scope: str | None = None,
              risk_level: str = "MEDIUM") -> dict:
    root = _system_root(root)
    if interval not in {15, 30, 60}: raise ValueError("Chu kỳ hợp lệ: 15, 30 hoặc 60 phút.")
    if bool(symbol) == bool(scope): raise ValueError("Chọn đúng một mã hoặc một phạm vi quét.")
    from .risk_profiles import normalize_risk_profile
    risk_level = normalize_risk_profile(risk_level)
    if bot_status(root).get("running"): raise RuntimeError("Bot PAPER đang chạy.")
    state_dir = _runtime_state_dir(root); state_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    log = open(state_dir / "bot.log", "a", encoding="utf-8")
    target_args = ["--scope", str(scope).upper()] if scope else ["--symbol", str(symbol).upper()]
    cmd = [sys.executable, "-u", str(root / "market_bot.py"), "--loop", "--minutes", str(interval),
           *target_args, "--risk-level", risk_level,
           "--heartbeat", str(state_dir / "bot_heartbeat.json"), "--process-token", token]
    env = os.environ.copy()
    env.pop("VN100_APP_DATA_DIR", None)
    env["VNSTOCKDESK_DATA_ROOT"] = str(storage_state_dir(root).parents[1])
    process_options = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
    }
    process = subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=log,
                               stderr=subprocess.STDOUT, close_fds=True, env=env, **process_options)
    state = {"pid": process.pid, "mode": "PAPER", "symbol": symbol, "scope": scope,
             "target_type": "SCOPE" if scope else "SYMBOL", "fixed_buy_quantity": 500 if scope else None,
             "interval_minutes": interval, "risk_level": risk_level,
             "started_at": time.time(), "token": token}
    (state_dir / "bot_process.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    for _ in range(40):
        status = bot_status(root)
        if status.get("token_valid"): return status
        if not _alive(process.pid): break
        time.sleep(.25)
    if _alive(process.pid): os.kill(process.pid, signal.SIGTERM)
    raise RuntimeError(f"Bot không khởi động được. Xem {state_dir / 'bot.log'}.")


def stop_bot(root: Path) -> dict:
    root = _system_root(root)
    status = bot_status(root)
    if status.get("running"):
        os.kill(int(status["pid"]), signal.SIGTERM)
        for _ in range(30):
            if not _alive(int(status["pid"])): break
            time.sleep(.1)
    try: (_runtime_state_dir(root) / "bot_process.json").unlink()
    except FileNotFoundError: pass
    return {**status, "running": False, "stopped": True}
