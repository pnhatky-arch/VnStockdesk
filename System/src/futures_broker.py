from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from .futures_engine import DEFAULT_FUTURES_RISK, FuturesRiskConfig


class PaperFuturesBroker:
    def __init__(self, path: Path, initial_balance_vnd: float = 1_000_000_000,
                 config: FuturesRiskConfig = DEFAULT_FUTURES_RISK):
        self.path, self.initial_balance_vnd, self.config = Path(path), float(initial_balance_vnd), config
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _initial(self) -> dict:
        return {"balance_vnd": self.initial_balance_vnd, "side": "FLAT", "quantity": 0,
                "entry_price": 0.0, "last_price": 0.0, "stop_loss": None, "target": None,
                "target_2": None, "target_1_done": False,
                "orders": [], "day": date.today().isoformat(), "day_start_equity_vnd": self.initial_balance_vnd,
                "trades_today": 0, "capital_adjustments": []}

    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state.get("side") not in {"FLAT", "LONG", "SHORT"}: raise ValueError("invalid side")
            if state.get("day") != date.today().isoformat():
                state["day"], state["day_start_equity_vnd"], state["trades_today"] = date.today().isoformat(), self.equity_from(state), 0
            return state
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._initial()

    def _save(self):
        tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(self.path)

    def equity_from(self, state: dict, price: float | None = None) -> float:
        mark = float(price or state.get("last_price") or state.get("entry_price") or 0)
        direction = 1 if state.get("side") == "LONG" else -1 if state.get("side") == "SHORT" else 0
        pnl = direction * int(state.get("quantity", 0)) * (mark - float(state.get("entry_price", 0))) * self.config.contract_multiplier_vnd
        return float(state.get("balance_vnd", 0)) + pnl

    def snapshot(self, price: float | None = None) -> dict:
        out = dict(self.state); out["equity_vnd"] = self.equity_from(self.state, price)
        out["unrealized_pnl_vnd"] = out["equity_vnd"] - float(self.state["balance_vnd"])
        return out

    def performance_report(self, price: float | None = None) -> dict:
        """Build an auditable PAPER performance report from filled close orders."""
        snapshot = self.snapshot(price)
        close_orders = [
            dict(order) for order in self.state.get("orders", [])
            if str(order.get("action", "")).startswith("CLOSE_")
            and order.get("status") == "FILLED"
        ]
        realized = float(sum(float(order.get("pnl_vnd", 0)) for order in close_orders))
        unrealized = float(snapshot.get("unrealized_pnl_vnd", 0))
        cash_after_realized = float(snapshot.get("balance_vnd", 0))
        capital_before_pnl = cash_after_realized - realized
        equity_after_total = float(snapshot.get("equity_vnd", cash_after_realized))
        total_pnl = realized + unrealized
        return_pct = total_pnl / capital_before_pnl * 100 if capital_before_pnl else 0.0

        wins = [float(order.get("pnl_vnd", 0)) for order in close_orders if float(order.get("pnl_vnd", 0)) > 0]
        losses = [float(order.get("pnl_vnd", 0)) for order in close_orders if float(order.get("pnl_vnd", 0)) < 0]
        gross_profit, gross_loss = sum(wins), abs(sum(losses))

        adjustments = [dict(item) for item in self.state.get("capital_adjustments", []) if "delta_vnd" in item]
        initial_curve_capital = capital_before_pnl - sum(float(item.get("delta_vnd", 0)) for item in adjustments)
        events = [
            {"time": item.get("time"), "kind": "CAPITAL", "change_vnd": float(item.get("delta_vnd", 0))}
            for item in adjustments
        ] + [
            {"time": order.get("time"), "kind": "REALIZED_PNL", "change_vnd": float(order.get("pnl_vnd", 0))}
            for order in close_orders
        ]
        events.sort(key=lambda item: str(item.get("time") or ""))
        running, peak, max_drawdown = initial_curve_capital, initial_curve_capital, 0.0
        equity_curve = []
        if events:
            equity_curve.append({"time": events[0]["time"], "equity_vnd": running, "kind": "START"})
        for event in events:
            running += event["change_vnd"]
            peak = max(peak, running)
            drawdown = (running - peak) / peak * 100 if peak else 0.0
            max_drawdown = min(max_drawdown, drawdown)
            equity_curve.append({**event, "equity_vnd": running, "drawdown_pct": drawdown})
        equity_curve.append({
            "time": datetime.now(timezone.utc).isoformat(), "kind": "CURRENT_MARK",
            "change_vnd": unrealized, "equity_vnd": equity_after_total,
            "drawdown_pct": (equity_after_total - max(peak, equity_after_total)) / max(peak, equity_after_total) * 100
            if max(peak, equity_after_total) else 0.0,
        })
        max_drawdown = min(max_drawdown, float(equity_curve[-1]["drawdown_pct"]))
        return {
            "capital_before_pnl_vnd": capital_before_pnl,
            "cash_after_realized_vnd": cash_after_realized,
            "equity_after_total_vnd": equity_after_total,
            "realized_pnl_vnd": realized,
            "unrealized_pnl_vnd": unrealized,
            "total_pnl_vnd": total_pnl,
            "return_pct": return_pct,
            "day_pnl_vnd": equity_after_total - float(snapshot.get("day_start_equity_vnd", equity_after_total)),
            "closed_trades": len(close_orders), "winning_trades": len(wins), "losing_trades": len(losses),
            "win_rate_pct": len(wins) / len(close_orders) * 100 if close_orders else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "average_trade_vnd": realized / len(close_orders) if close_orders else 0.0,
            "max_drawdown_pct": max_drawdown,
            "close_orders": close_orders, "equity_curve": equity_curve,
        }

    def set_balance(self, amount: float) -> None:
        value = float(amount)
        if not 10_000_000 <= value <= 100_000_000_000_000: raise ValueError("Số dư PAPER Futures không hợp lệ.")
        delta = value - float(self.state["balance_vnd"]); self.state["balance_vnd"] = value
        self.state["day_start_equity_vnd"] += delta
        self.state["capital_adjustments"].append({"time": datetime.now(timezone.utc).isoformat(), "type": "SET_BALANCE", "delta_vnd": delta, "after_vnd": value})
        self._save()

    def reset(self, amount: float | None = None) -> None:
        self.initial_balance_vnd = float(amount or self.initial_balance_vnd); self.state = self._initial()
        self.state["capital_adjustments"] = [{"time": datetime.now(timezone.utc).isoformat(), "type": "RESET", "after_vnd": self.initial_balance_vnd}]
        self._save()

    def open(self, side: str, quantity: int, price: float, stop_loss: float, target: float,
             reason="MANUAL_PAPER", target_2: float | None = None) -> dict:
        side, quantity, price = side.upper(), int(quantity), float(price)
        if side not in {"LONG", "SHORT"} or quantity <= 0: raise ValueError("Lệnh PAPER Futures không hợp lệ.")
        if self.state["side"] != "FLAT": raise RuntimeError("Phải đóng vị thế hiện tại trước.")
        if self.state["trades_today"] >= self.config.max_trades_per_day: raise RuntimeError("Đã đạt giới hạn số lệnh trong ngày.")
        if self.equity_from(self.state, price) <= self.state["day_start_equity_vnd"] * (1 - self.config.max_daily_loss_pct): raise RuntimeError("Đã chạm ngưỡng khóa lỗ trong ngày.")
        self.state.update(side=side, quantity=quantity, entry_price=price, last_price=price,
                          stop_loss=float(stop_loss), target=float(target),
                          target_2=None if target_2 is None else float(target_2), target_1_done=False)
        self.state["trades_today"] += 1
        order = {"time": datetime.now(timezone.utc).isoformat(), "action": f"OPEN_{side}", "quantity": quantity, "price": price, "reason": reason, "status": "FILLED"}
        self.state["orders"].append(order); self._save()
        try:
            from .paths import STATE_DIR
            from .trade_alerts import record_fill
            if self.path.parent.resolve() == STATE_DIR.resolve():
                record_fill(order, "PAPER", str(self.path.stem).removeprefix("paper_futures_").upper(), "futures")
        except (OSError, ValueError, TypeError):
            pass
        return order

    def close(self, price: float, reason="MANUAL_PAPER", quantity: int | None = None) -> dict:
        if self.state["side"] == "FLAT": raise RuntimeError("Không có vị thế để đóng.")
        price = float(price); held = int(self.state["quantity"]); quantity = held if quantity is None else int(quantity)
        if quantity <= 0 or quantity > held: raise ValueError("Khối lượng đóng PAPER Futures không hợp lệ.")
        direction = 1 if self.state["side"] == "LONG" else -1
        pnl = direction * quantity * (price - float(self.state["entry_price"])) * self.config.contract_multiplier_vnd
        order = {"time": datetime.now(timezone.utc).isoformat(), "action": f"CLOSE_{self.state['side']}", "quantity": quantity, "price": price, "pnl_vnd": round(pnl), "reason": reason, "status": "FILLED"}
        self.state["balance_vnd"] += pnl; self.state["quantity"] -= quantity; self.state["last_price"] = price
        if self.state["quantity"] == 0:
            self.state.update(side="FLAT", quantity=0, entry_price=0.0, stop_loss=None, target=None, target_2=None, target_1_done=False)
        self.state["orders"].append(order); self._save()
        try:
            from .paths import STATE_DIR
            from .trade_alerts import record_fill
            if self.path.parent.resolve() == STATE_DIR.resolve():
                record_fill(order, "PAPER", str(self.path.stem).removeprefix("paper_futures_").upper(), "futures")
        except (OSError, ValueError, TypeError):
            pass
        return order
