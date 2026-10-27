"""Read-only, best-effort live equity quotes for PAPER mark-to-market."""
from __future__ import annotations

from datetime import date, datetime, timezone
import re
import time
from typing import Callable

import pandas as pd


EQUITY_QUOTE_PROVIDERS = ("KBS", "VCI")


def load_equity_quote(symbol: str, market_factory: Callable | None = None) -> dict:
    """Fetch a current quote without affecting cached candles or PAPER orders."""
    symbol = _safe_symbol(symbol)
    if market_factory is None:
        from vnstock.ui import Market
        market_factory = Market
    errors = {}
    for provider in EQUITY_QUOTE_PROVIDERS:
        started = time.perf_counter()
        try:
            raw = market_factory().equity(symbol).quote(source=provider)
            if raw is None or getattr(raw, "empty", True):
                raise ValueError("Dữ liệu quote rỗng.")
            values = _last_row_values(raw)
            price = _number(values, "match_price", "close_price", "last_price")
            bid = _number(values, "bid_price_1", "bid_price")
            ask = _number(values, "ask_price_1", "ask_price")
            if price is None and bid and ask:
                price = (bid + ask) / 2
            if price is None:
                raise ValueError("Quote không có giá khớp/bid-ask hợp lệ.")
            provider_time_raw = str(values.get("sending_time") or values.get("time") or "")
            market_time, market_age_seconds = _market_time(values, provider_time_raw)
            return {"status": "OK", "symbol": symbol, "price": price, "bid": bid, "ask": ask,
                    "reference_price": _number(values, "reference_price", "ref_price"),
                    "volume": _number(values, "accumulated_volume", "volume_accumulated", "match_vol"),
                    "provider": provider, "source_label": f"{provider} qua VNStock",
                    "provider_time": provider_time_raw, "market_time": market_time,
                    "market_age_seconds": market_age_seconds,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "request_latency_ms": round((time.perf_counter() - started) * 1000), "errors": errors}
        except BaseException as exc:
            errors[provider] = f"{type(exc).__name__}: {exc}"
    return {"status": "ERROR", "symbol": symbol, "price": None, "provider": None,
            "received_at": datetime.now(timezone.utc).isoformat(), "errors": errors}


def _safe_symbol(symbol: str) -> str:
    value = str(symbol or "").upper().strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", value):
        raise ValueError("Mã cổ phiếu không hợp lệ.")
    return value


def _last_row_values(raw) -> dict:
    values = {}
    for column, value in raw.iloc[-1].items():
        key = str(column[-1] if isinstance(column, tuple) else column).lower()
        if key not in values or pd.isna(values[key]):
            values[key] = value
    return values


def _number(values: dict, *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(values.get(key, 0) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _market_time(values: dict, provider_time_raw: str) -> tuple[str | None, float | None]:
    try:
        if provider_time_raw.isdigit():
            unit = "ms" if len(provider_time_raw) >= 13 else "s"
            stamp = pd.to_datetime(int(provider_time_raw), unit=unit, utc=True)
        else:
            trading_date = str(values.get("trading_date") or date.today().isoformat())
            stamp = pd.Timestamp(f"{trading_date} {provider_time_raw}", tz="Asia/Ho_Chi_Minh")
        age = max(0.0, (pd.Timestamp.now(tz="UTC") - stamp.tz_convert("UTC")).total_seconds())
        return stamp.isoformat(), round(age, 1)
    except (TypeError, ValueError, OverflowError):
        return None, None
