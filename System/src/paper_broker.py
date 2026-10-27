from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from .trading_config import DEFAULT_CONFIG, TradingConfig
from .settlement import market_now, parse_market_time, settlement_time


class PaperBroker:
    def __init__(self, state_path: Path, config: TradingConfig = DEFAULT_CONFIG):
        self.path = Path(state_path)
        self.config = config
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _initial_state(self) -> dict:
        return {
            "cash_vnd": self.config.initial_cash_vnd,
            "positions": {}, "orders": [], "capital_adjustments": [], "pending_cash": [],
            "day": date.today().isoformat(),
            "day_start_equity_vnd": self.config.initial_cash_vnd,
        }

    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(state.get("positions"), dict):
                raise ValueError("invalid portfolio")
            if state.get("day") != date.today().isoformat():
                state["day"] = date.today().isoformat()
                state["day_start_equity_vnd"] = self._equity_from_state(state)
            state.setdefault("pending_cash", [])
            # Positions created before settlement support are genuine existing
            # PAPER inventory and are migrated as fully settled.
            for position in state["positions"].values():
                position.setdefault("settled_quantity", int(position.get("quantity", 0)))
                position.setdefault("pending_lots", [])
            return state
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._initial_state()

    def _equity_from_state(self, state: dict) -> float:
        total = float(state.get("cash_vnd", 0))
        total += sum(float(item.get("amount_vnd", 0)) for item in state.get("pending_cash", []))
        for pos in state.get("positions", {}).values():
            total += self.market_value_vnd(pos["quantity"], pos["last_price"])
        return total

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _validate_capital(amount: float) -> float:
        value = float(amount)
        if not 1_000_000 <= value <= 1_000_000_000_000_000:
            raise ValueError("Vốn PAPER phải từ 1.000.000 đến 1.000.000.000.000.000 ₫.")
        return round(value)

    def set_cash_balance(self, amount: float) -> dict:
        """Adjust simulated cash while preserving positions and order history."""
        value = self._validate_capital(amount)
        previous = float(self.state.get("cash_vnd", 0))
        delta = value - previous
        self.state["cash_vnd"] = value
        # Capital deposits/withdrawals must not count as intraday PnL.
        self.state["day_start_equity_vnd"] = float(self.state.get("day_start_equity_vnd", 0)) + delta
        record = {"time": datetime.now(timezone.utc).isoformat(), "type": "SET_CASH", "before_vnd": previous, "after_vnd": value, "delta_vnd": delta}
        self.state.setdefault("capital_adjustments", []).append(record)
        self.state["capital_adjustments"] = self.state["capital_adjustments"][-100:]
        self._save()
        return record

    def reset(self, initial_cash_vnd: float | None = None) -> dict:
        """Create a clean paper account; positions and histories are removed."""
        value = self._validate_capital(initial_cash_vnd if initial_cash_vnd is not None else self.config.initial_cash_vnd)
        self.state = {
            "cash_vnd": value, "positions": {}, "orders": [],
            "capital_adjustments": [{"time": datetime.now(timezone.utc).isoformat(), "type": "RESET", "after_vnd": value}],
            "pending_cash": [],
            "day": date.today().isoformat(), "day_start_equity_vnd": value,
        }
        self._save()
        return self.snapshot()

    def normalize_quantity(self, quantity: int) -> int:
        return max(0, int(quantity) // self.config.lot_size * self.config.lot_size)

    def market_value_vnd(self, quantity: int, price: float) -> float:
        return quantity * float(price) * self.config.price_multiplier

    def settle(self, now: datetime | None = None) -> bool:
        """Release T+2 securities/cash that have reached their local cutoff."""
        now = now or market_now()
        changed = False
        remaining_cash = []
        for item in self.state.setdefault("pending_cash", []):
            if parse_market_time(item["available_at"]) <= now:
                self.state["cash_vnd"] += float(item.get("amount_vnd", 0))
                changed = True
            else:
                remaining_cash.append(item)
        self.state["pending_cash"] = remaining_cash
        for position in self.state.get("positions", {}).values():
            pending = []
            for lot in position.setdefault("pending_lots", []):
                if parse_market_time(lot["available_at"]) <= now:
                    position["settled_quantity"] = int(position.get("settled_quantity", 0)) + int(lot["quantity"])
                    changed = True
                else:
                    pending.append(lot)
            position["pending_lots"] = pending
            position["settled_quantity"] = min(int(position.get("settled_quantity", 0)), int(position.get("quantity", 0)))
        if changed:
            self._save()
        return changed

    def available_quantity(self, symbol: str, now: datetime | None = None) -> int:
        self.settle(now)
        position = self.state.get("positions", {}).get(str(symbol).upper(), {})
        return max(0, int(position.get("settled_quantity", 0)))

    def equity(self, prices: dict[str, float] | None = None) -> float:
        prices = prices or {}
        total = float(self.state["cash_vnd"])
        total += sum(float(item.get("amount_vnd", 0)) for item in self.state.get("pending_cash", []))
        for symbol, pos in self.state["positions"].items():
            total += self.market_value_vnd(pos["quantity"], prices.get(symbol, pos["last_price"]))
        return total

    def daily_loss_locked(self, prices: dict[str, float] | None = None) -> bool:
        start = float(self.state.get("day_start_equity_vnd", self.config.initial_cash_vnd))
        return self.equity(prices) <= start * (1 - self.config.max_daily_loss_pct)

    def buy(self, symbol: str, quantity: int, price: float, stop_loss: float | None = None,
            target: float | None = None, reason: str = "AUTO", now: datetime | None = None) -> dict:
        now = now or market_now()
        self.settle(now)
        symbol, quantity, price = symbol.upper(), self.normalize_quantity(quantity), float(price)
        if quantity <= 0: raise ValueError("Khối lượng sau khi làm tròn lô phải lớn hơn 0.")
        value = self.market_value_vnd(quantity, price)
        fee = value * self.config.buy_fee_rate
        if value + fee > self.state["cash_vnd"]: raise RuntimeError("Không đủ tiền mặt.")
        old = self.state["positions"].get(symbol, {"quantity": 0, "avg_price": 0, "settled_quantity": 0, "pending_lots": []})
        new_qty = old["quantity"] + quantity
        avg = (old["quantity"] * old["avg_price"] + quantity * price) / new_qty
        self.state["cash_vnd"] -= value + fee
        self.state["positions"][symbol] = {
            "quantity": new_qty, "avg_price": round(avg, 4), "last_price": price,
            "stop_loss": stop_loss, "target": target,
            "settled_quantity": int(old.get("settled_quantity", 0)),
            "pending_lots": [*old.get("pending_lots", []), {
                "quantity": quantity, "trade_time": now.isoformat(),
                "available_at": settlement_time(now, hour=13).isoformat(),
            }],
        }
        return self._record(symbol, "BUY", quantity, price, fee, 0, reason, {
            "settlement_cycle": "T+2", "securities_available_at": settlement_time(now, hour=13).isoformat(),
        }, now=now)

    def sell(self, symbol: str, quantity: int, price: float, reason: str = "AUTO",
             now: datetime | None = None) -> dict:
        now = now or market_now()
        self.settle(now)
        symbol, quantity, price = symbol.upper(), self.normalize_quantity(quantity), float(price)
        pos = self.state["positions"].get(symbol)
        available = int(pos.get("settled_quantity", 0)) if pos else 0
        if not pos or quantity <= 0 or quantity > available:
            pending = max(0, int(pos.get("quantity", 0)) - available) if pos else 0
            raise RuntimeError(
                f"Không đủ cổ phiếu khả dụng theo T+2: có thể bán {available:,} CP; "
                f"đang chờ về {pending:,} CP."
            )
        value = self.market_value_vnd(quantity, price)
        fee, tax = value * self.config.sell_fee_rate, value * self.config.sell_tax_rate
        net_proceeds = value - fee - tax
        cash_available_at = settlement_time(now, hour=8)
        self.state.setdefault("pending_cash", []).append({
            "symbol": symbol, "amount_vnd": net_proceeds, "trade_time": now.isoformat(),
            "available_at": cash_available_at.isoformat(),
        })
        pos["settled_quantity"] = available - quantity
        pos["quantity"] -= quantity; pos["last_price"] = price
        if pos["quantity"] == 0: del self.state["positions"][symbol]
        return self._record(symbol, "SELL", quantity, price, fee, tax, reason, {
            "settlement_cycle": "T+2", "cash_available_at": cash_available_at.isoformat(),
            "net_proceeds_pending_vnd": round(net_proceeds),
        }, now=now)

    def _record(self, symbol: str, side: str, quantity: int, price: float,
                fee: float, tax: float, reason: str, extra: dict | None = None,
                now: datetime | None = None) -> dict:
        now = now or market_now()
        order = {"time": now.astimezone(timezone.utc).isoformat(), "mode": "PAPER", "symbol": symbol,
                 "side": side, "quantity": quantity, "price": price, "fee_vnd": round(fee),
                 "tax_vnd": round(tax), "reason": reason, "status": "FILLED"}
        order.update(extra or {})
        self.state["orders"].append(order); self.state["orders"] = self.state["orders"][-500:]
        self._save()
        try:
            from .paths import STATE_DIR
            from .trade_alerts import record_fill
            if self.path.parent.resolve() == STATE_DIR.resolve():
                record_fill(order, "PAPER", symbol, "equity")
        except (OSError, ValueError, TypeError):
            pass
        return order

    def snapshot(self, prices: dict[str, float] | None = None) -> dict:
        self.settle()
        return {"cash_vnd": self.state["cash_vnd"], "equity_vnd": self.equity(prices),
                "positions": self.state["positions"], "orders": self.state["orders"],
                "capital_adjustments": self.state.get("capital_adjustments", []),
                "pending_cash": self.state.get("pending_cash", []),
                "pending_cash_vnd": sum(float(item.get("amount_vnd", 0)) for item in self.state.get("pending_cash", []))}

    def performance_report(self, prices: dict[str, float] | None = None) -> dict:
        """Reconstruct net realized/unrealized P&L from the PAPER order ledger."""
        prices = prices or {}
        inventory: dict[str, dict[str, float]] = {}
        closed_trades, realized = [], 0.0
        for order in self.state.get("orders", []):
            if order.get("status") != "FILLED":
                continue
            symbol = str(order.get("symbol", "")).upper()
            quantity = int(order.get("quantity", 0))
            price = float(order.get("price", 0))
            fee = float(order.get("fee_vnd", 0))
            tax = float(order.get("tax_vnd", 0))
            position = inventory.setdefault(symbol, {"quantity": 0.0, "cost_vnd": 0.0})
            if order.get("side") == "BUY":
                position["quantity"] += quantity
                position["cost_vnd"] += self.market_value_vnd(quantity, price) + fee
            elif order.get("side") == "SELL" and quantity > 0:
                held = float(position["quantity"])
                allocated_cost = position["cost_vnd"] * quantity / held if held > 0 else 0.0
                proceeds = self.market_value_vnd(quantity, price) - fee - tax
                pnl = proceeds - allocated_cost
                position["quantity"] = max(0.0, held - quantity)
                position["cost_vnd"] = max(0.0, position["cost_vnd"] - allocated_cost)
                realized += pnl
                closed_trades.append({**order, "action": f"SELL {symbol}", "pnl_vnd": pnl})

        unrealized = 0.0
        for symbol, position in inventory.items():
            quantity = float(position["quantity"])
            if quantity <= 0:
                continue
            fallback = self.state.get("positions", {}).get(symbol, {}).get("last_price", 0)
            market_value = self.market_value_vnd(quantity, prices.get(symbol, fallback))
            unrealized += market_value - float(position["cost_vnd"])
        equity = float(self.equity(prices))
        total_pnl = realized + unrealized
        capital_before_pnl = equity - total_pnl
        adjustments = [item for item in self.state.get("capital_adjustments", []) if "delta_vnd" in item]
        initial_capital = capital_before_pnl - sum(float(item.get("delta_vnd", 0)) for item in adjustments)
        events = [
            {"time": item.get("time"), "kind": "CAPITAL", "change_vnd": float(item.get("delta_vnd", 0))}
            for item in adjustments
        ] + [
            {"time": order.get("time"), "kind": "REALIZED_PNL", "change_vnd": float(order["pnl_vnd"])}
            for order in closed_trades
        ]
        events.sort(key=lambda item: str(item.get("time") or ""))
        running, peak, max_drawdown = initial_capital, initial_capital, 0.0
        curve = []
        if events:
            curve.append({"time": events[0]["time"], "kind": "START", "change_vnd": 0.0,
                          "equity_vnd": running, "drawdown_pct": 0.0})
        for event in events:
            running += event["change_vnd"]
            peak = max(peak, running)
            drawdown = (running - peak) / peak * 100 if peak else 0.0
            max_drawdown = min(max_drawdown, drawdown)
            curve.append({**event, "equity_vnd": running, "drawdown_pct": drawdown})
        current_peak = max(peak, equity)
        current_drawdown = (equity - current_peak) / current_peak * 100 if current_peak else 0.0
        curve.append({"time": datetime.now(timezone.utc).isoformat(), "kind": "CURRENT_MARK",
                      "change_vnd": unrealized, "equity_vnd": equity, "drawdown_pct": current_drawdown})
        wins = [trade["pnl_vnd"] for trade in closed_trades if trade["pnl_vnd"] > 0]
        losses = [trade["pnl_vnd"] for trade in closed_trades if trade["pnl_vnd"] < 0]
        gross_loss = abs(sum(losses))
        return {
            "capital_before_pnl_vnd": capital_before_pnl,
            "cash_after_realized_vnd": capital_before_pnl + realized,
            "equity_after_total_vnd": equity,
            "realized_pnl_vnd": realized, "unrealized_pnl_vnd": unrealized,
            "total_pnl_vnd": total_pnl,
            "return_pct": total_pnl / capital_before_pnl * 100 if capital_before_pnl else 0.0,
            "day_pnl_vnd": equity - float(self.state.get("day_start_equity_vnd", equity)),
            "closed_trades": len(closed_trades), "winning_trades": len(wins), "losing_trades": len(losses),
            "win_rate_pct": len(wins) / len(closed_trades) * 100 if closed_trades else 0.0,
            "profit_factor": sum(wins) / gross_loss if gross_loss else None,
            "average_trade_vnd": realized / len(closed_trades) if closed_trades else 0.0,
            "max_drawdown_pct": min(max_drawdown, current_drawdown),
            "close_orders": closed_trades, "equity_curve": curve,
        }
