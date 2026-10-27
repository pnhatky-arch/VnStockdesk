from __future__ import annotations

import argparse, json, os, tempfile, time
from pathlib import Path

from src.futures_trading_engine import futures_paper_cycle, futures_paper_scan_cycle
from src.futures_data import load_futures_contracts

ROOT = Path(__file__).resolve().parent


def _write_heartbeat(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, default=str)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run_once(symbol: str = "VN30F1M", risk_level: str = "MEDIUM") -> dict:
    result = futures_paper_cycle(ROOT, symbol=symbol, risk_level=risk_level)
    print(json.dumps({"mode":result["mode"],"symbol":symbol,"price":result["price"],
                      "action":result["bot_action"],"reason":result["reason"],
                      "orders":result["orders"],"equity_vnd":result["account"]["equity_vnd"]}, ensure_ascii=False, default=str), flush=True)
    return result


def run_scope(scope: str, risk_level: str = "MEDIUM") -> dict:
    if scope != "ALL":
        result = run_once(scope, risk_level)
        return {"mode":"PAPER_FUTURES_SCAN","scanned":1,"total":1,"results":[result],
                "orders":result.get("orders",[]),"errors":[],"actions":{scope:result["bot_action"]},
                "bot_action":result["bot_action"],"reason":result["reason"]}
    contracts, _ = load_futures_contracts()
    return futures_paper_scan_cycle(ROOT, [item["symbol"] for item in contracts], risk_level=risk_level)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="PAPER Futures bot")
    parser.add_argument("--loop",action="store_true"); parser.add_argument("--minutes",type=int,default=15)
    parser.add_argument("--heartbeat"); parser.add_argument("--process-token"); parser.add_argument("--live",action="store_true")
    parser.add_argument("--symbol",default="VN30F1M")
    parser.add_argument("--risk-level",choices=["LOW","MEDIUM","HIGH"],default="MEDIUM")
    args=parser.parse_args()
    if args.live: raise RuntimeError("LIVE Futures đang khóa; chỉ PAPER được phép.")
    if args.heartbeat:
        path=Path(args.heartbeat); path.parent.mkdir(parents=True,exist_ok=True)
        payload={"updated_at":time.time(),"mode":"PAPER_FUTURES_SCAN","symbol":args.symbol,
                 "action":"STARTING","reason":"Đang khởi tạo vòng quét phái sinh.",
                 "orders":[],"scanned":0,"total":0,"actions":{},"errors":[],"token":args.process_token}
        payload["risk_level"] = args.risk_level
        _write_heartbeat(path, payload)
    while True:
        try:
            output=run_scope(args.symbol, args.risk_level)
            if args.heartbeat:
                path=Path(args.heartbeat); path.parent.mkdir(parents=True,exist_ok=True)
                first = output.get("results", [{}])[0] if output.get("results") else {}
                payload={"updated_at":time.time(),"mode":"PAPER_FUTURES_SCAN","symbol":args.symbol,
                         "action":output["bot_action"],"reason":output["reason"],"orders":output["orders"],
                         "price":first.get("price"),"scanned":output.get("scanned",0),"total":output.get("total",0),
                         "actions":output.get("actions",{}),"errors":output.get("errors",[]),"token":args.process_token}
                payload["risk_level"] = args.risk_level
                _write_heartbeat(path, payload)
        except BaseException as exc: print(f"[FUTURES BOT ERROR] {type(exc).__name__}: {exc}",flush=True)
        if not args.loop: break
        time.sleep(max(1,args.minutes)*60)
