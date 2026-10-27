"""Persistent, machine-local queue for filled-order alerts."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .local_io import atomic_json, file_lock
from .paths import STATE_DIR

MAX_EVENTS = 100


def _queue_path() -> Path:
    return STATE_DIR / "trade_fill_alerts.json"


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _event_id(order: dict, mode: str, symbol: str, market: str) -> str:
    identity = {
        "mode": mode, "market": market, "symbol": symbol,
        "action": order.get("action") or order.get("side"),
        "quantity": order.get("quantity"), "price": order.get("price"), "time": order.get("time"),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def record_fill(order: dict | None, mode: str, symbol: str, market: str) -> dict | None:
    if not isinstance(order, dict) or not order or order.get("status") != "FILLED":
        return None
    event = {"id": _event_id(order, mode, symbol, market), "created_at": time.time(),
             "mode": mode, "market": market, "symbol": symbol, "order": order}
    path = _queue_path()
    with file_lock(path.with_suffix(".lock"), wait_seconds=2):
        state = _read(path)
        events = [item for item in state.get("events", []) if isinstance(item, dict)]
        existing = next((item for item in events if item.get("id") == event["id"]), None)
        if existing:
            return existing
        events.append(event)
        dismissed = [str(item) for item in state.get("dismissed", [])]
        atomic_json(path, {"events": events[-MAX_EVENTS:], "dismissed": dismissed[-MAX_EVENTS:]})
    return event


def sync_latest_fill_from_ledgers(state_dir: Path, max_age_seconds: float = 43_200) -> dict | None:
    """Recover the latest recent fill from PAPER ledgers.

    This keeps alerts working for BOT workers that were already running when
    the alert queue was introduced; it never changes account/order data.
    """
    candidates = []
    ledgers = [(Path(state_dir) / "paper_portfolio.json", "equity")]
    ledgers.extend((path, "futures") for path in Path(state_dir).glob("paper_futures_*.json"))
    now = time.time()
    for path, market in ledgers:
        state = _read(path)
        orders = state.get("orders", [])
        if not isinstance(orders, list) or not orders:
            continue
        order = orders[-1]
        if not isinstance(order, dict) or order.get("status") != "FILLED":
            continue
        try:
            stamp = datetime.fromisoformat(str(order["time"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            created_at = stamp.timestamp()
        except (KeyError, TypeError, ValueError):
            continue
        if not -300 <= now - created_at <= max_age_seconds:
            continue
        symbol = (str(order.get("symbol") or "").upper() if market == "equity"
                  else path.stem.removeprefix("paper_futures_").upper())
        if symbol:
            candidates.append((created_at, order, symbol, market))
    if not candidates:
        return None
    _, order, symbol, market = max(candidates, key=lambda item: item[0])
    return record_fill(order, "PAPER", symbol, market)


def pending_fill() -> dict | None:
    state = _read(_queue_path())
    dismissed = {str(item) for item in state.get("dismissed", [])}
    return next((item for item in state.get("events", [])
                 if isinstance(item, dict) and item.get("id") not in dismissed), None)


def dismiss_fill(event_id: str) -> None:
    path = _queue_path()
    with file_lock(path.with_suffix(".lock"), wait_seconds=2):
        state = _read(path)
        dismissed = [str(item) for item in state.get("dismissed", [])]
        if event_id not in dismissed:
            dismissed.append(event_id)
        events = [item for item in state.get("events", []) if isinstance(item, dict)]
        atomic_json(path, {"events": events[-MAX_EVENTS:], "dismissed": dismissed[-MAX_EVENTS:]})
