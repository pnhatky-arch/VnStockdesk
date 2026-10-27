from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import webbrowser

# Google Drive can intermittently reject atomic updates to ``__pycache__``.
# Bytecode is disposable runtime output, so keep the synced System tree clean.
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(__file__).resolve().parent
from src.paths import RUNTIME_DIR
from src.bot_manager import cleanup_legacy_bot_workers
from src.process_utils import process_alive
# Process identity and logs are machine-local. Keeping these inside synced Data
# makes macOS and Windows overwrite each other's PID and launcher state.
PID_PATH = RUNTIME_DIR / "dashboard_process.json"
LOG_PATH = RUNTIME_DIR / "dashboard.log"
PORT = int(os.getenv("VNSTOCKDESK_PORT", "8506" if sys.platform == "darwin" else "8503"))
URL = f"http://localhost:{PORT}/"


def _open_dashboard() -> None:
    """Open the UI through the operating system's registered browser."""
    if sys.platform == "darwin":
        # Python's webbrowser detection is unreliable when launched by a
        # background AppleScript applet (the server starts but no window is
        # shown).  Launch Services via /usr/bin/open works in that context.
        subprocess.Popen(
            ["/usr/bin/open", URL], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    else:
        webbrowser.open(URL)


def _port_open(port: int = PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.35):
            return True
    except OSError:
        return False


def _read_state() -> dict:
    try: return json.loads(PID_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError): return {}


def _alive(pid: int) -> bool:
    return process_alive(pid)


def _source_signature() -> str:
    """Stable build identity so a synced source update restarts Streamlit."""
    digest = hashlib.sha256()
    sources = [ROOT / "app.py", *sorted((ROOT / "src").glob("*.py"))]
    for path in sources:
        try:
            digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


def _replace_legacy_mac_dashboard() -> bool:
    """Replace only a localhost server whose cwd is another VnStockDesk/System."""
    if sys.platform != "darwin":
        return False
    try:
        found = subprocess.run(
            ["lsof", f"-tiTCP:{PORT}", "-sTCP:LISTEN"], capture_output=True,
            text=True, check=False, timeout=3,
        )
        pid = int((found.stdout or "").strip().splitlines()[0])
        cwd_result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True, text=True, check=False, timeout=3,
        )
        cwd_line = next(line[1:] for line in cwd_result.stdout.splitlines() if line.startswith("n/"))
        legacy_root = Path(cwd_line).resolve()
        if legacy_root.name != "System" or legacy_root.parent.name != "VnStockDesk":
            return False
        if legacy_root == ROOT.resolve():
            return False
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not _port_open():
                return True
            time.sleep(.1)
    except (OSError, ValueError, IndexError, StopIteration, subprocess.SubprocessError):
        return False
    return not _port_open()


def start() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_legacy_bot_workers(ROOT)
    state = _read_state()
    source_signature = _source_signature()
    # The listening port is authoritative. A stale/reused PID can still pass
    # kill(pid, 0), especially when macOS denies process inspection, while no
    # dashboard is actually serving requests.
    if _port_open():
        if state.get("source_signature") == source_signature:
            _open_dashboard()
            return
        # Only replace a process created by this launcher. Never kill an
        # unknown service that happens to use the same port.
        managed_pid = int(state.get("pid", 0) or 0)
        if managed_pid > 0 and _alive(managed_pid):
            stop()
        elif _replace_legacy_mac_dashboard():
            pass
        else:
            _open_dashboard()
            return
    log = open(LOG_PATH, "a", encoding="utf-8")
    command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
               "--server.port", str(PORT), "--server.headless", "true",
               "--server.fileWatcherType", "poll",
               "--browser.gatherUsageStats", "false"]
    process_options = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
    }
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT,
                               close_fds=True, **process_options)
    PID_PATH.write_text(json.dumps({"pid": process.pid, "started_at": time.time(),
                                   "python": sys.executable, "url": URL,
                                   "system_root": str(ROOT.resolve()),
                                   "source_signature": source_signature}, indent=2), encoding="utf-8")
    for _ in range(80):
        if _port_open():
            _open_dashboard()
            return
        if not _alive(process.pid): break
        time.sleep(.25)
    raise RuntimeError(f"Dashboard không khởi động được. Xem {LOG_PATH}")


def stop() -> None:
    state = _read_state(); pid = int(state.get("pid", 0) or 0)
    if _alive(pid):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            try: os.killpg(pid, signal.SIGTERM)
            except PermissionError:
                try: os.kill(pid, signal.SIGTERM)
                except (PermissionError, ProcessLookupError): pass
            except ProcessLookupError: pass
        for _ in range(30):
            if not _alive(pid): break
            time.sleep(.1)
    try: PID_PATH.unlink()
    except FileNotFoundError: pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    stop() if args.stop else start()
