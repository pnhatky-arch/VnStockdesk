from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import json
from pathlib import Path

from .analyzer import analyze_symbol
from .data import get_history
from .paper_broker import PaperBroker
from .trading_config import DEFAULT_CONFIG, TradingConfig
from .universe import MARKET_SCOPES, get_market_universe
from .paths import state_dir as storage_state_dir
from .risk_profiles import normalize_risk_profile, risk_profile


def position_size(equity_vnd: float, cash_vnd: float, entry: float, stop: float,
                  config: TradingConfig = DEFAULT_CONFIG) -> int:
    risk_per_share = max((entry - stop) * config.price_multiplier, 0)
    if risk_per_share <= 0: return 0
    by_risk = equity_vnd * config.risk_per_trade / risk_per_share
    by_position = equity_vnd * config.max_position_pct / (entry * config.price_multiplier)
    by_cash = cash_vnd / ((entry * config.price_multiplier) * (1 + config.buy_fee_rate))
    return max(0, int(min(by_risk, by_position, by_cash)) // config.lot_size * config.lot_size)


def paper_cycle(root: Path, symbol: str, refresh: bool = False,
                fixed_buy_quantity: int | None = None,
                risk_level: str = "MEDIUM") -> dict:
    risk_level = normalize_risk_profile(risk_level)
    profile = risk_profile(risk_level)
    broker = PaperBroker(storage_state_dir(root) / "paper_portfolio.json")
    df = get_history(symbol, refresh=refresh)
    analysis = analyze_symbol(symbol, df)
    day = analysis["timeframes"].get("1D", {})
    price = float(day.get("close") or df.iloc[-1]["close"])
    prices = {symbol: price}
    pos = broker.state["positions"].get(symbol)
    action, order, skip_reason, skip_code = analysis["system_action"], None, None, None

    if pos:
        pos["last_price"] = price
        available_qty = broker.available_quantity(symbol)
        pending_qty = max(0, int(pos.get("quantity", 0)) - available_qty)
        stop_hit = pos.get("stop_loss") is not None and price <= float(pos["stop_loss"])
        target_hit = pos.get("target") is not None and price >= float(pos["target"])
        if stop_hit or target_hit or action == "BÁN_CÓ_XÁC_NHẬN":
            if available_qty > 0:
                order = broker.sell(symbol, available_qty, price, "STOP" if stop_hit else "TARGET" if target_hit else action)
                if pending_qty:
                    skip_code = "T_PLUS_2_PARTIAL_LOCK"
                    skip_reason = f"Đã bán {available_qty} CP khả dụng; còn {pending_qty} CP mua chờ về theo T+2."
            else:
                skip_code = "T_PLUS_2_SELL_LOCK"
                trigger = "Stop Loss" if stop_hit else "Take Profit" if target_hit else "tín hiệu bán"
                skip_reason = f"{trigger} đã kích hoạt nhưng {pending_qty} CP chưa về; chưa thể bán trước 13:00 ngày T+2."
                broker._save()
        elif action == "GIẢM_TỶ_TRỌNG":
            qty = min(available_qty, broker.normalize_quantity(pos["quantity"] // 2))
            if qty > 0: order = broker.sell(symbol, qty, price, action)
            elif pending_qty:
                skip_code, skip_reason = "T_PLUS_2_SELL_LOCK", f"Chưa thể giảm tỷ trọng: {pending_qty} CP đang chờ về theo T+2."
        else:
            broker._save()
    confidence = float(analysis.get("confidence", 0) or 0)
    alignment = float(analysis.get("timeframe_alignment", 0) or 0)
    confirmed_buy = action == "MUA_CÓ_XÁC_NHẬN"
    watch_buy = profile["allow_watch_buy"] and action == "THEO_DÕI_MUA"
    entry_action = confirmed_buy or watch_buy
    # MEDIUM preserves the original execution rule. LOW adds stricter
    # evidence gates; HIGH may promote a strong WATCH_BUY into an entry.
    entry_qualified = (
        confirmed_buy and (risk_level != "LOW" or (
            confidence >= profile["confidence"] and alignment >= profile["alignment"]
        ))
    ) or (
        watch_buy and confidence >= profile["confidence"] and alignment >= profile["alignment"]
    )
    if not pos and entry_action and not entry_qualified:
        skip_code = "RISK_PROFILE_THRESHOLD"
        skip_reason = (
            f"Quản trị rủi ro {profile['label']}: cần confidence ≥ {profile['confidence']}% "
            f"và đồng thuận ≥ {profile['alignment']}%."
        )
    elif not pos and entry_qualified:
        if broker.daily_loss_locked(prices):
            skip_code, skip_reason = "DAILY_LOSS_LOCK", "Tài khoản đã chạm khóa lỗ trong ngày; không mở vị thế mới."
        else:
            plan = analysis.get("strategy_plan", {})
            stop = float(plan.get("stop_loss") or price * 0.93)
            sized_config = replace(
                broker.config,
                risk_per_trade=broker.config.risk_per_trade * profile["risk_multiplier"],
                max_position_pct=min(.30, broker.config.max_position_pct * profile["position_multiplier"]),
            )
            allowed_qty = position_size(broker.equity(prices), broker.state["cash_vnd"], price, stop, sized_config)
            qty = allowed_qty
            if fixed_buy_quantity is not None:
                requested_qty = broker.normalize_quantity(int(fixed_buy_quantity))
                qty = requested_qty if requested_qty > 0 and allowed_qty >= requested_qty else 0
                if qty == 0:
                    required_cash = broker.market_value_vnd(requested_qty, price) * (1 + broker.config.buy_fee_rate)
                    if required_cash > float(broker.state["cash_vnd"]):
                        skip_code, skip_reason = "INSUFFICIENT_CASH", f"Không đủ tiền mặt để mua đúng {requested_qty} cổ phiếu."
                    else:
                        skip_code, skip_reason = "RISK_OR_WEIGHT_LIMIT", f"Lệnh {requested_qty} cổ phiếu vượt tỷ trọng hoặc hạn mức rủi ro cho phép."
            if qty > 0:
                order = broker.buy(symbol, qty, price, stop, plan.get("target_1"), action)

    return {"mode": "PAPER", "symbol": symbol, "price": price, "analysis": analysis,
            "order": order, "skip_code": skip_code, "skip_reason": skip_reason,
            "risk_level": risk_level,
            "portfolio": broker.snapshot(prices)}


def _record_scope_alert(root: Path, *, scope: str, symbol: str, code: str, reason: str) -> dict:
    path = storage_state_dir(root) / "bot_alerts.json"
    try:
        alerts = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(alerts, list): alerts = []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        alerts = []
    now = datetime.now(timezone.utc)
    # Avoid repeating the same audible warning on every scan cycle.
    for previous in reversed(alerts[-20:]):
        if previous.get("scope") == scope and previous.get("symbol") == symbol and previous.get("code") == code:
            try:
                if (now - datetime.fromisoformat(previous["time"])).total_seconds() < 1800:
                    return previous
            except (KeyError, TypeError, ValueError):
                pass
    alert = {
        "id": f"{now.timestamp():.6f}-{scope}-{symbol}-{code}", "time": now.isoformat(),
        "scope": scope, "symbol": symbol, "code": code, "reason": reason,
        "severity": "WARNING",
    }
    alerts.append(alert)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(alerts[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return alert


def paper_scope_cycle(root: Path, scope: str, *, fixed_buy_quantity: int = 500,
                      refresh: bool = False, progress_callback=None,
                      risk_level: str = "MEDIUM") -> dict:
    """Scan a basket/market and trade PAPER while preserving portfolio risk locks."""
    scope = str(scope).upper()
    if scope not in MARKET_SCOPES:
        raise ValueError(f"Phạm vi BOT không hợp lệ: {scope}")
    broker = PaperBroker(storage_state_dir(root) / "paper_portfolio.json")
    held = list(broker.state.get("positions", {}))
    universe = get_market_universe(scope)
    symbols = held + [symbol for symbol in universe if symbol not in set(held)]
    results, orders, errors = [], [], []
    for index, symbol in enumerate(symbols, 1):
        try:
            result = paper_cycle(root, symbol, refresh=refresh, fixed_buy_quantity=fixed_buy_quantity,
                                 risk_level=risk_level)
            results.append({
                "symbol": symbol, "price": result["price"],
                "action": result["analysis"]["system_action"], "order": result["order"],
                "skip_code": result.get("skip_code"), "skip_reason": result.get("skip_reason"),
            })
            if result["order"]:
                orders.append(result["order"])
            if result.get("skip_reason"):
                _record_scope_alert(root, scope=scope, symbol=symbol,
                                    code=result["skip_code"], reason=result["skip_reason"])
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
        if progress_callback:
            progress_callback(index, len(symbols), symbol, orders, errors)
    final_broker = PaperBroker(storage_state_dir(root) / "paper_portfolio.json")
    buy_orders = [order for order in orders if order.get("side") == "BUY"]
    return {
        "mode": "PAPER", "scope": scope, "scope_label": MARKET_SCOPES[scope],
        "risk_level": normalize_risk_profile(risk_level),
        "fixed_buy_quantity": int(fixed_buy_quantity), "scanned": len(symbols),
        "successful": len(results), "errors": errors, "orders": orders,
        "buy_orders": buy_orders, "results": results,
        "portfolio": final_broker.snapshot(),
    }
