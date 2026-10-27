from __future__ import annotations

import json, os, secrets, signal, subprocess, sys, time
from pathlib import Path
from .paths import PROJECT_ROOT, RUNTIME_DIR, state_dir as storage_state_dir
from .process_utils import process_alive


def _system_root(root: Path) -> Path:
    candidate = Path(root).resolve()
    if (candidate / "futures_bot.py").is_file():
        return candidate
    sibling = candidate.parent / "System"
    if (sibling / "futures_bot.py").is_file():
        return sibling.resolve()
    return candidate


def _runtime_state_dir(root: Path) -> Path:
    root = _system_root(root)
    return RUNTIME_DIR / "bot_state" if root == PROJECT_ROOT.resolve() else storage_state_dir(root)


def _read(path: Path) -> dict:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError): return {}


def _alive(pid: int) -> bool:
    return process_alive(pid)


def futures_bot_status(root: Path) -> dict:
    root=_system_root(root)
    state_root=_runtime_state_dir(root)
    state=_read(state_root/"futures_bot_process.json"); heartbeat=_read(state_root/"futures_bot_heartbeat.json")
    pid=int(state.get("pid",0) or 0); token_valid=bool(state.get("token") and heartbeat.get("token")==state.get("token"))
    age=time.time()-float(heartbeat.get("updated_at",0) or 0); stale=max(90,float(state.get("interval_minutes",15))*60*2.5)
    starting=time.time()-float(state.get("started_at",0) or 0)<20
    return {**state,"running":_alive(pid) and (starting or (token_valid and 0<=age<=stale)),"heartbeat":heartbeat,
            "token_valid":token_valid,"heartbeat_age_seconds":round(age,1)}


def start_futures_bot(root: Path, interval: int=15, symbol: str="VN30F1M",
                      risk_level: str="MEDIUM") -> dict:
    root=_system_root(root)
    if interval not in {5,15,30}: raise ValueError("Chu kỳ Futures hợp lệ: 5, 15 hoặc 30 phút.")
    from .risk_profiles import normalize_risk_profile
    risk_level=normalize_risk_profile(risk_level)
    if futures_bot_status(root).get("running"): raise RuntimeError("BOT PAPER Futures đang chạy.")
    root=_system_root(root); state_dir=_runtime_state_dir(root); state_dir.mkdir(parents=True,exist_ok=True); token=secrets.token_hex(16)
    log=open(state_dir/"futures_bot.log","a",encoding="utf-8")
    symbol=str(symbol).upper()
    cmd=[sys.executable,"-u",str(root/"futures_bot.py"),"--loop","--minutes",str(interval),"--symbol",symbol,
         "--risk-level",risk_level,"--heartbeat",str(state_dir/"futures_bot_heartbeat.json"),"--process-token",token]
    env=os.environ.copy(); env.pop("VN100_APP_DATA_DIR",None)
    env["VNSTOCKDESK_DATA_ROOT"]=str(storage_state_dir(root).parents[1])
    process_options={"start_new_session":True} if os.name!="nt" else {"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP}
    process=subprocess.Popen(cmd,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,close_fds=True,env=env,**process_options)
    state={"pid":process.pid,"mode":"PAPER_FUTURES","symbol":symbol,"interval_minutes":interval,
           "risk_level":risk_level,"started_at":time.time(),"token":token}
    (state_dir/"futures_bot_process.json").write_text(json.dumps(state,indent=2),encoding="utf-8")
    for _ in range(40):
        status=futures_bot_status(root)
        if status.get("token_valid"): return status
        if not _alive(process.pid): break
        time.sleep(.25)
    if _alive(process.pid): os.kill(process.pid,signal.SIGTERM)
    raise RuntimeError(f"BOT Futures không khởi động được. Xem {state_dir / 'futures_bot.log'}.")


def stop_futures_bot(root: Path) -> dict:
    root=_system_root(root); status=futures_bot_status(root); pid=int(status.get("pid",0) or 0)
    if status.get("running"):
        os.kill(pid,signal.SIGTERM)
        for _ in range(30):
            if not _alive(pid): break
            time.sleep(.1)
    try: (_runtime_state_dir(root)/"futures_bot_process.json").unlink()
    except FileNotFoundError: pass
    return {**status,"running":False,"stopped":True}
