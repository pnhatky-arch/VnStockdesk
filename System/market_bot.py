from __future__ import annotations

import argparse, json, os, tempfile, time
from pathlib import Path

from src.trading_engine import paper_cycle, paper_scope_cycle

ROOT = Path(__file__).resolve().parent


def run_once(symbol: str, risk_level: str = "MEDIUM") -> dict:
    result = paper_cycle(ROOT, symbol, risk_level=risk_level)
    print(json.dumps({"mode": result["mode"], "symbol": symbol, "price": result["price"],
                      "action": result["analysis"]["system_action"], "order": result["order"],
                      "equity_vnd": result["portfolio"]["equity_vnd"]}, ensure_ascii=False, default=str))
    return result


def _write_heartbeat(path_text: str | None, token: str | None, payload: dict) -> None:
    if not path_text:
        return
    path = Path(path_text); path.parent.mkdir(parents=True, exist_ok=True)
    body = {"updated_at": time.time(), "mode": "PAPER", "token": token, **payload}
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False, default=str)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run_scope_once(scope: str, heartbeat: str | None = None, token: str | None = None,
                   risk_level: str = "MEDIUM") -> dict:
    def progress(scanned, total, symbol, orders, errors):
        _write_heartbeat(heartbeat, token, {
            "target_type":"SCOPE", "scope":scope, "action":"SCANNING",
            "symbol":symbol, "scanned":scanned, "total":total,
            "orders_count":len(orders), "errors_count":len(errors),
            "fixed_buy_quantity":500,
            "risk_level":risk_level,
        })
    result = paper_scope_cycle(ROOT, scope, fixed_buy_quantity=500, progress_callback=progress,
                               risk_level=risk_level)
    print(json.dumps({"mode":"PAPER", "scope":scope, "scanned":result["scanned"],
                      "orders":result["orders"], "errors":len(result["errors"]),
                      "equity_vnd":result["portfolio"]["equity_vnd"]}, ensure_ascii=False, default=str))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VnStockDesk PAPER trading bot")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--minutes", type=int, default=30)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--symbol")
    target.add_argument("--scope", choices=["VN30","VN100","FAVORITES","HOSE","HNX","UPCOM","ALL"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--heartbeat", help=argparse.SUPPRESS)
    parser.add_argument("--process-token", help=argparse.SUPPRESS)
    parser.add_argument("--risk-level", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
    args = parser.parse_args()
    if args.live:
        raise RuntimeError("LIVE đang khóa: cần adapter API chính thức của công ty chứng khoán.")
    _write_heartbeat(args.heartbeat, args.process_token, {
        "target_type": "SCOPE" if args.scope else "SYMBOL",
        "scope": args.scope, "symbol": args.symbol, "action": "STARTING",
        "scanned": 0, "total": 0, "orders_count": 0, "errors_count": 0,
        "risk_level": args.risk_level,
    })
    while True:
        try:
            if args.scope:
                output = run_scope_once(args.scope, args.heartbeat, args.process_token, args.risk_level)
                _write_heartbeat(args.heartbeat, args.process_token, {
                    "target_type":"SCOPE", "scope":args.scope, "action":"SCAN_COMPLETE",
                    "scanned":output["scanned"], "total":output["scanned"],
                    "orders_count":len(output["orders"]), "errors_count":len(output["errors"]),
                    "fixed_buy_quantity":500,
                    "risk_level":args.risk_level,
                })
            else:
                output = run_once(args.symbol, args.risk_level)
                _write_heartbeat(args.heartbeat, args.process_token, {
                    "target_type":"SYMBOL", "symbol":args.symbol,
                    "action":output["analysis"]["system_action"], "order":output["order"],
                    "price":output["price"],
                    "risk_level":args.risk_level,
                })
        except Exception as exc:
            print(f"[BOT ERROR] {type(exc).__name__}: {exc}", flush=True)
        if not args.loop: break
        time.sleep(max(1, args.minutes) * 60)
