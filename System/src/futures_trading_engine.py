from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .futures_broker import PaperFuturesBroker
from .futures_data import load_futures_bundle, load_futures_quote
from .futures_engine import analyze_vn30f1m
from .paths import data_dir as storage_data_dir, state_dir as storage_state_dir
from .risk_profiles import normalize_risk_profile, risk_profile


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def session_state(now: datetime | None = None) -> dict:
    now = now.astimezone(VN_TZ) if now and now.tzinfo else (now.replace(tzinfo=VN_TZ) if now else datetime.now(VN_TZ))
    clock = now.time()
    weekday = now.weekday() < 5
    morning = time(8, 45) <= clock <= time(11, 30)
    afternoon = time(13, 0) <= clock <= time(14, 45)
    entry_window = weekday and (time(8, 50) <= clock <= time(11, 15) or time(13, 0) <= clock <= time(14, 15))
    force_close = weekday and time(14, 25) <= clock <= time(15, 0)
    return {"market_open": weekday and (morning or afternoon), "entry_window": entry_window,
            "force_close": force_close, "time": now.isoformat()}


def _confirmed_candle(frame: pd.DataFrame, side: str) -> bool:
    if frame is None or frame.empty: return False
    bar = frame.iloc[-1]
    return float(bar["close"]) > float(bar["open"]) if side == "LONG" else float(bar["close"]) < float(bar["open"])


def futures_paper_cycle(root: Path, *, now: datetime | None = None,
                        frames: dict | None = None, symbol: str = "VN30F1M",
                        risk_level: str = "MEDIUM") -> dict:
    root = Path(root)
    symbol = str(symbol).upper()
    risk_level = normalize_risk_profile(risk_level)
    profile = risk_profile(risk_level)
    live_quote = None
    if frames is None:
        frames, diagnostics = load_futures_bundle(storage_data_dir(root) / "raw" / "futures", refresh=True, symbol=symbol)
        live_quote = load_futures_quote(symbol)
        diagnostics["quote"] = live_quote
    else:
        diagnostics = {tf: {"source": "INJECTED", "rows": len(df)} for tf, df in frames.items()}
    broker = PaperFuturesBroker(storage_state_dir(root) / f"paper_futures_{symbol.lower()}.json")
    mark_frame = frames.get("15M", pd.DataFrame())
    candle_price = float(mark_frame.iloc[-1]["close"]) if not mark_frame.empty else 0.0
    quote_is_fresh = (
        live_quote and live_quote.get("status") == "OK"
        and (live_quote.get("market_age_seconds") is None or float(live_quote["market_age_seconds"]) <= 15)
    )
    price = float(live_quote["price"]) if quote_is_fresh else candle_price
    account = broker.snapshot(price)
    analysis = analyze_vn30f1m(frames, account_equity_vnd=account["equity_vnd"], symbol=symbol)
    session = session_state(now)
    orders, bot_action, reason = [], "WAIT", "Chưa đủ điều kiện kích hoạt."
    if analysis.get("status") != "OK" or price <= 0:
        return {"mode":"PAPER_FUTURES","symbol":symbol,"price":price,"analysis":analysis,
                "orders":orders,"account":account,"session":session,"bot_action":"DATA_LOCK","reason":"Không đủ dữ liệu.","diagnostics":diagnostics}

    side = broker.state["side"]
    if side != "FLAT":
        broker.state["last_price"] = price
        stop = float(broker.state["stop_loss"]); target1 = float(broker.state["target"])
        target2 = float(broker.state.get("target_2") or target1)
        stop_hit = price <= stop if side == "LONG" else price >= stop
        target1_hit = price >= target1 if side == "LONG" else price <= target1
        target2_hit = price >= target2 if side == "LONG" else price <= target2
        opposite = analysis["action"] in ({"SHORT"} if side == "LONG" else {"LONG"})
        if stop_hit:
            orders.append(broker.close(price, "STOP_LOSS")); bot_action, reason = "CLOSE", "Chạm stop loss."
        elif session["force_close"]:
            orders.append(broker.close(price, "END_OF_DAY")); bot_action, reason = "CLOSE", "Đóng vị thế cuối ngày."
        elif target2_hit and broker.state.get("target_1_done"):
            orders.append(broker.close(price, "TARGET_2")); bot_action, reason = "CLOSE", "Hoàn tất mục tiêu 2."
        elif target1_hit and not broker.state.get("target_1_done"):
            close_qty = max(1, int(broker.state["quantity"]) // 2)
            orders.append(broker.close(price, "TARGET_1_PARTIAL", quantity=close_qty))
            if broker.state["side"] != "FLAT":
                broker.state["target_1_done"] = True; broker.state["stop_loss"] = broker.state["entry_price"]; broker._save()
            bot_action, reason = "PARTIAL_TAKE_PROFIT", "Chốt TP1 và dời stop về hòa vốn."
        elif opposite and analysis["confidence"] >= 75:
            orders.append(broker.close(price, "OPPOSITE_SIGNAL")); bot_action, reason = "CLOSE", "Tín hiệu đối nghịch đủ mạnh."
        else:
            broker._save(); bot_action, reason = "MANAGE", "Theo dõi stop, TP1 và TP2."
    else:
        action = analysis["action"]
        no_blockers = not analysis.get("risk_flags")
        confirmed = action in {"LONG", "SHORT"} and _confirmed_candle(mark_frame, action)
        qualified = (
            analysis["confidence"] >= profile["confidence"]
            and analysis["alignment"] >= profile["alignment"]
            and analysis["position_size"]["contracts"] > 0
        )
        if session["entry_window"] and no_blockers and confirmed and qualified:
            plan = analysis["plan"]
            base_contracts = int(analysis["position_size"]["contracts"])
            contracts = max(1, int(base_contracts * profile["position_multiplier"]))
            orders.append(broker.open(action, contracts, price,
                                      plan["stop_loss"], plan["target_1"], "AUTO_CONFIRMED_15M", target_2=plan["target_2"]))
            bot_action, reason = f"OPEN_{action}", "15M, 1H và 1D đạt điều kiện mở vị thế."
        elif not session["entry_window"]:
            reason = "Ngoài khung giờ được phép mở vị thế."
        elif analysis.get("risk_flags"):
            reason = "Bị khóa bởi: " + " • ".join(analysis["risk_flags"])
        elif not confirmed:
            reason = "Nến 15M chưa xác nhận hướng vào lệnh."
        elif not qualified:
            reason = "Score, confidence, alignment hoặc sizing chưa đạt ngưỡng."
    return {"mode":"PAPER_FUTURES","symbol":symbol,"price":price,"analysis":analysis,
            "orders":orders,"account":broker.snapshot(price),"session":session,
            "bot_action":bot_action,"reason":reason,"risk_level":risk_level,"diagnostics":diagnostics}


def futures_paper_scan_cycle(root: Path, symbols: list[str], *, now: datetime | None = None,
                             risk_level: str = "MEDIUM") -> dict:
    """Run one auditable PAPER cycle over a selected futures basket."""
    results, errors, orders = [], [], []
    for symbol in dict.fromkeys(str(value).upper() for value in symbols if value):
        try:
            result = futures_paper_cycle(root, now=now, symbol=symbol, risk_level=risk_level)
            results.append(result)
            orders.extend({**order, "symbol":symbol} for order in result.get("orders", []))
        except BaseException as exc:
            errors.append({"symbol":symbol,"error":f"{type(exc).__name__}: {exc}"})
    actions = {item["symbol"]:item.get("bot_action","WAIT") for item in results}
    return {
        "mode":"PAPER_FUTURES_SCAN", "scanned":len(results), "total":len(symbols),
        "risk_level":normalize_risk_profile(risk_level),
        "results":results, "orders":orders, "errors":errors, "actions":actions,
        "bot_action":"ORDERS" if orders else "SCAN_COMPLETE",
        "reason":f"Đã quét {len(results)}/{len(symbols)} hợp đồng · {len(orders)} lệnh.",
    }
