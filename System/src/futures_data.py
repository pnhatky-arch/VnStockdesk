from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
import re
import time

import pandas as pd

from .data import normalize_ohlcv
from .local_io import atomic_csv


FUTURES_SYMBOL = "VN30F1M"
FUTURES_INTERVALS = {"15M": "15m", "1H": "1H", "1D": "1D"}
FUTURES_COUNTS = {"15M": 900, "1H": 700, "1D": 500}
FUTURES_PROVIDER_PRIORITY = ("VCI", "KBS")


def load_futures_quote(symbol: str = FUTURES_SYMBOL, market_factory: Callable | None = None) -> dict:
    """Fetch the freshest valid futures quote with explicit provider diagnostics."""
    symbol = _safe_symbol(symbol)
    if market_factory is None:
        from vnstock.ui import Market
        market_factory = Market
    errors = {}
    for provider in FUTURES_PROVIDER_PRIORITY:
        started = time.perf_counter()
        try:
            raw = market_factory().futures(symbol).quote(source=provider)
            if raw is None or getattr(raw, "empty", True):
                raise ValueError("Dữ liệu quote rỗng.")
            row = raw.iloc[-1]
            values = {}
            for column, value in row.items():
                key = str(column[-1] if isinstance(column, tuple) else column).lower()
                if key not in values or pd.isna(values[key]): values[key] = value
            def number(*keys):
                for key in keys:
                    try:
                        value = float(values.get(key, 0) or 0)
                        if value > 0: return value
                    except (TypeError, ValueError): pass
                return None
            bid = number("bid_price_1", "bid_price")
            ask = number("ask_price_1", "ask_price")
            price = number("match_price", "close_price", "last_price")
            if price is None and bid and ask: price = (bid + ask) / 2
            if price is None: raise ValueError("Quote không có giá khớp/bid-ask hợp lệ.")
            provider_time_raw = str(values.get("sending_time") or values.get("time") or "")
            market_time, market_age_seconds = None, None
            try:
                if provider_time_raw.isdigit():
                    unit = "ms" if len(provider_time_raw) >= 13 else "s"
                    market_stamp = pd.to_datetime(int(provider_time_raw), unit=unit, utc=True)
                else:
                    trading_date = str(values.get("trading_date") or date.today().isoformat())
                    market_stamp = pd.Timestamp(f"{trading_date} {provider_time_raw}", tz="Asia/Ho_Chi_Minh")
                market_time = market_stamp.isoformat()
                market_age_seconds = max(0.0, (pd.Timestamp.now(tz="UTC") - market_stamp.tz_convert("UTC")).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
            return {
                "status":"OK","symbol":symbol,"price":price,"bid":bid,"ask":ask,
                "reference_price":number("reference_price","ref_price"),
                "volume":number("accumulated_volume","volume_accumulated","match_vol"),
                "provider":provider,"source_label":f"{provider} qua VNStock",
                "provider_time":provider_time_raw,"market_time":market_time,
                "market_age_seconds":None if market_age_seconds is None else round(market_age_seconds,1),
                "received_at":datetime.now(timezone.utc).isoformat(),
                "request_latency_ms":round((time.perf_counter()-started)*1000),"errors":errors,
            }
        except BaseException as exc:
            errors[provider] = f"{type(exc).__name__}: {exc}"
    return {"status":"ERROR","symbol":symbol,"price":None,"provider":None,
            "received_at":datetime.now(timezone.utc).isoformat(),"errors":errors}


def _safe_symbol(symbol: str) -> str:
    value = str(symbol or FUTURES_SYMBOL).upper().strip()
    if not re.fullmatch(r"[A-Z0-9]{4,16}", value):
        raise ValueError("Mã hợp đồng phái sinh không hợp lệ.")
    return value


def _contract_info(symbol: str) -> dict:
    """Decode current KRX index-futures symbols returned by VCI."""
    code = _safe_symbol(symbol)
    if not code.startswith("41"):
        underlying = "VN100" if code.startswith("VN100") else "VN30" if code.startswith("VN30") else "FUTURES"
        return {"symbol":code,"exchange_symbol":code,"underlying":underlying,
                "expiry":"Hợp đồng gần nhất","label":f"{code} · Hợp đồng gần nhất"}
    product = {"I1": "VN30", "I2": "VN100"}.get(code[2:4], "FUTURES") if len(code) >= 6 else "FUTURES"
    year_code, month_code = (code[4], code[5]) if len(code) >= 6 else ("", "")
    year = 2020 + ord(year_code) - ord("A") if "A" <= year_code <= "Z" else None
    month = int(month_code) if month_code.isdigit() and month_code != "0" else {"A":10,"B":11,"C":12}.get(month_code)
    expiry = f"{month:02d}/{year}" if month and year else "Chưa xác định"
    return {"symbol": code, "exchange_symbol": code, "underlying": product, "expiry": expiry,
            "label": f"{product} · {expiry} · {code}"}


def load_futures_contracts(reference_factory: Callable | None = None) -> tuple[list[dict], dict]:
    """Load all currently listed futures contracts, preferring VCI."""
    if reference_factory is None:
        from vnstock.ui import Reference
        reference_factory = Reference
    errors = {}
    for provider in FUTURES_PROVIDER_PRIORITY:
        try:
            raw = reference_factory().futures().list(source=provider)
            values = raw.astype(str).tolist() if hasattr(raw, "astype") else list(raw or [])
            decoded = [_contract_info(value) for value in dict.fromkeys(values) if str(value).strip()]
            # Some provider responses repeat the same listed contract through
            # aliases. Use the exchange code as the canonical identity before
            # assigning the friendly front-month alias.
            contracts, seen_exchange_symbols = [], set()
            for item in decoded:
                canonical = str(item.get("exchange_symbol") or item["symbol"]).upper()
                if canonical in seen_exchange_symbols:
                    continue
                seen_exchange_symbols.add(canonical)
                contracts.append(item)
            if contracts:
                # Keep friendly front-month aliases and the legacy VN30F1M PAPER ledger.
                front_seen = set()
                for item in contracts:
                    underlying = item["underlying"]
                    if underlying in {"VN30", "VN100"} and underlying not in front_seen:
                        front_seen.add(underlying)
                        item["symbol"] = f"{underlying}F1M"
                        item["label"] = f"{underlying}F1M · {item['expiry']}"
                return contracts, {"provider":provider,"source_label":f"{provider} qua VNStock","count":len(contracts),"errors":errors}
            errors[provider] = "Danh sách rỗng."
        except BaseException as exc:
            errors[provider] = f"{type(exc).__name__}: {exc}"
    return [_contract_info(FUTURES_SYMBOL)], {"provider":"FALLBACK","source_label":"Danh sách dự phòng","count":1,"errors":errors}


def _cache_path(cache_dir: Path, timeframe: str, symbol: str = FUTURES_SYMBOL) -> Path:
    return Path(cache_dir) / f"{_safe_symbol(symbol).lower()}_{timeframe.lower()}.csv"


def _read_cache(path: Path) -> pd.DataFrame:
    try:
        return normalize_ohlcv(pd.read_csv(path))
    except (OSError, ValueError, TypeError, pd.errors.ParserError):
        return normalize_ohlcv(None)


def _write_cache(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_csv(path, frame)


def load_futures_timeframe(
    timeframe: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
    market_factory: Callable | None = None,
    symbol: str = FUTURES_SYMBOL,
    cache_only: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Load one VN30F1M timeframe, retaining a safe local fallback."""
    if timeframe not in FUTURES_INTERVALS:
        raise ValueError(f"Unsupported VN30F1M timeframe: {timeframe}")
    symbol = _safe_symbol(symbol)
    path = _cache_path(cache_dir, timeframe, symbol)
    cached = _read_cache(path)
    error = None
    provider = None
    history_provider = None
    provider_errors: dict[str, str] = {}
    fresh = normalize_ohlcv(None)
    if cache_only:
        return cached, {
            "timeframe": timeframe, "symbol": symbol,
            "source": "CACHE" if not cached.empty else "UNAVAILABLE",
            "source_label": "Dữ liệu lưu · đang cập nhật nền",
            "provider": None, "history_provider": None, "provider_errors": {},
            "rows": len(cached),
            "latest": None if cached.empty else pd.Timestamp(cached.iloc[-1]["time"]).isoformat(),
            "error": None, "refresh": False,
        }
    if market_factory is None:
        try:
            from vnstock.ui import Market
            market_factory = Market
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
    if market_factory is not None:
        end = date.today()
        start = end - timedelta(days=520 if timeframe == "1D" else 120)
        provider_frames: dict[str, pd.DataFrame] = {}
        for candidate in FUTURES_PROVIDER_PRIORITY:
            try:
                raw = (
                    market_factory()
                    .futures(symbol)
                    .ohlcv(
                        start=start.isoformat(),
                        end=end.isoformat(),
                        interval=FUTURES_INTERVALS[timeframe],
                        count=FUTURES_COUNTS[timeframe],
                        source=candidate,
                    )
                )
                candidate_frame = normalize_ohlcv(raw)
                if not candidate_frame.empty:
                    provider_frames[candidate] = candidate_frame
                    if provider is None:
                        provider = candidate
                    # VCI is authoritative for the newest mark. Keep loading KBS
                    # only when VCI history is too shallow for long indicators.
                    if candidate == "VCI" and len(candidate_frame) >= 220:
                        break
                    if candidate == "KBS":
                        history_provider = "KBS"
                        break
                else:
                    provider_errors[candidate] = "Nhà cung cấp trả về dữ liệu rỗng."
            except BaseException as exc:  # vnstock may raise SystemExit on provider failures
                provider_errors[candidate] = f"{type(exc).__name__}: {exc}"
        if provider_frames:
            # Put VCI last so an overlapping timestamp keeps VCI's market mark.
            ordered = [provider_frames[key] for key in ("KBS", "VCI") if key in provider_frames]
            fresh = normalize_ohlcv(pd.concat(ordered, ignore_index=True))
            fresh = fresh.drop_duplicates(subset=["time"], keep="last").sort_values("time").reset_index(drop=True)
            _write_cache(path, fresh)
        if provider_errors and provider is None:
            error = " | ".join(f"{key}: {value}" for key, value in provider_errors.items())
    frame = fresh if not fresh.empty else cached
    source = "ONLINE" if not fresh.empty else "CACHE" if not cached.empty else "UNAVAILABLE"
    return frame, {
        "timeframe": timeframe,
        "symbol": symbol,
        "source": source,
        "provider": provider,
        "history_provider": history_provider,
        "source_label": (
            "VCI (giá) · KBS (lịch sử) qua VNStock"
            if provider == "VCI" and history_provider == "KBS"
            else f"{provider} qua VNStock" if provider else source
        ),
        "provider_errors": provider_errors,
        "rows": len(frame),
        "latest": None if frame.empty else pd.Timestamp(frame.iloc[-1]["time"]).isoformat(),
        "error": error,
        "refresh": bool(refresh),
    }


def load_futures_bundle(cache_dir: Path, *, refresh: bool = False, market_factory=None,
                        symbol: str = FUTURES_SYMBOL, cache_only: bool = False) -> tuple[dict, dict]:
    frames, diagnostics = {}, {}
    for timeframe in FUTURES_INTERVALS:
        frame, meta = load_futures_timeframe(
            timeframe, cache_dir, refresh=refresh, market_factory=market_factory, symbol=symbol, cache_only=cache_only
        )
        frames[timeframe], diagnostics[timeframe] = frame, meta
    return frames, diagnostics
