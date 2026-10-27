"""VN-Index analysis with auditable technical, breadth and scenario layers."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import time

import numpy as np
import pandas as pd

from .analyzer import analyze_timeframe
from .data import HISTORY_START, HISTORY_COUNT, normalize_ohlcv
from .local_io import atomic_csv
from .paths import RAW_DIR


INDEX_CACHE_DIR = RAW_DIR / "index"
INDEX_SYMBOLS = ("VNINDEX", "VN30", "VN100")


def _normalise_index(raw) -> pd.DataFrame:
    frame = pd.DataFrame() if raw is None else pd.DataFrame(raw).copy()
    frame.columns = [str(column).lower().strip() for column in frame.columns]
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    return normalize_ohlcv(frame)


def _fetch_index_ohlcv(symbol: str = "VNINDEX") -> tuple[pd.DataFrame, str]:
    errors = []
    for module_name in ("vnstock.ui", "vnstock_data"):
        for source in ("kbs", "vci"):
            try:
                module = __import__(module_name, fromlist=["Market"])
                accessor = module.Market().index(symbol)
                try:
                    raw = accessor.ohlcv(start=HISTORY_START, end=date.today().isoformat(),
                                         interval="1D", count=HISTORY_COUNT, source=source)
                except TypeError:
                    raw = accessor.ohlcv(start=HISTORY_START, end=date.today().isoformat(), interval="1D")
                frame = _normalise_index(raw)
                if len(frame) >= 60:
                    return frame, f"{module_name}:{source.upper()}"
                errors.append(f"{module_name}:{source}: chỉ có {len(frame)} nến")
            except Exception as exc:
                errors.append(f"{module_name}:{source}: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"Không tải được dữ liệu {symbol}. " + " | ".join(errors))


def load_index_history(symbol: str = "VNINDEX", refresh: bool = False) -> tuple[pd.DataFrame, str]:
    symbol = str(symbol).upper().strip()
    INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = INDEX_CACHE_DIR / f"{symbol.lower()}_1d.csv"
    if path.exists() and not refresh:
        cached = _normalise_index(pd.read_csv(path))
        if len(cached) >= 60:
            age = (pd.Timestamp.now().normalize() - cached["time"].max().normalize()).days
            if age <= 4:
                return cached, "cache"
    try:
        frame, source = _fetch_index_ohlcv(symbol)
        atomic_csv(path, frame)
        return frame, source
    except Exception:
        if path.exists():
            cached = _normalise_index(pd.read_csv(path))
            if not cached.empty:
                return cached, "cache_stale"
        raise


def load_hose_breadth(processed_dir: Path, symbol: str = "VNINDEX") -> pd.DataFrame:
    """Use only completed scanner evidence; never invent missing constituents."""
    symbol = str(symbol).upper().strip()
    candidates = {
        "VN30": ("vn30_scan.csv", "vn100_scan.csv", "market_scan_hose.csv"),
        "VN100": ("vn100_scan.csv", "market_scan_hose.csv", "market_scan_all.csv"),
        "VNINDEX": ("market_scan_hose.csv", "market_scan_all.csv", "vn100_scan.csv"),
    }.get(symbol, ("market_scan_hose.csv", "market_scan_all.csv"))
    for name in candidates:
        path = processed_dir / name
        if path.exists():
            try:
                frame = pd.read_csv(path)
                if "consensus_score" in frame.columns and not frame.empty:
                    return frame
            except (OSError, ValueError, pd.errors.ParserError):
                continue
    return pd.DataFrame()


def _breadth_summary(scan: pd.DataFrame) -> dict:
    if scan is None or scan.empty or "consensus_score" not in scan.columns:
        return {"status": "UNAVAILABLE", "sample": 0, "score": 0.0,
                "bullish_pct": None, "bearish_pct": None, "neutral_pct": None}
    scores = pd.to_numeric(scan["consensus_score"], errors="coerce").dropna()
    if scores.empty:
        return {"status": "UNAVAILABLE", "sample": 0, "score": 0.0,
                "bullish_pct": None, "bearish_pct": None, "neutral_pct": None}
    bullish = float((scores >= 25).mean() * 100)
    bearish = float((scores <= -25).mean() * 100)
    return {"status": "OK", "sample": int(len(scores)), "score": round(float(scores.mean()), 1),
            "bullish_pct": round(bullish, 1), "bearish_pct": round(bearish, 1),
            "neutral_pct": round(100.0 - bullish - bearish, 1)}


def _scenario_weights(combined_score: float) -> dict:
    tilt = float(np.clip(combined_score / 32.0, -2.2, 2.2))
    raw = np.array([np.exp(tilt), 1.35 / (1.0 + abs(tilt)), np.exp(-tilt)], dtype=float)
    values = raw / raw.sum() * 100.0
    rounded = [round(float(value), 1) for value in values]
    rounded[1] = round(100.0 - rounded[0] - rounded[2], 1)
    return {"bull": rounded[0], "range": rounded[1], "bear": rounded[2]}


def analyze_vnindex(history: pd.DataFrame, constituent_scan: pd.DataFrame | None = None,
                    horizon_sessions: int = 20, symbol: str = "VNINDEX") -> dict:
    symbol = str(symbol).upper().strip()
    frame = _normalise_index(history)
    horizon = int(np.clip(horizon_sessions, 5, 60))
    if len(frame) < max(80, horizon * 3):
        return {"status": "INSUFFICIENT_HISTORY", "rows": len(frame), "horizon_sessions": horizon}

    timeframes = {tf: analyze_timeframe(frame, tf) for tf in ("1D", "1W", "1M", "1Y")}
    weights = {"1D": 1.0, "1W": 1.5, "1M": 1.5, "1Y": 0.75}
    valid = [(timeframes[tf], weight) for tf, weight in weights.items()
             if timeframes[tf].get("status") == "OK"]
    index_score = (sum(float(item.get("signal_score", 0)) * weight for item, weight in valid)
                   / (sum(weight for _, weight in valid) or 1.0))
    breadth = _breadth_summary(constituent_scan)
    breadth_weight = 0.35 if breadth["status"] == "OK" and breadth["sample"] >= 20 else 0.0
    combined = index_score * (1.0 - breadth_weight) + float(breadth["score"]) * breadth_weight

    close = float(frame.iloc[-1]["close"])
    changes = frame["close"].shift(-horizon) / frame["close"] - 1.0
    completed = changes.iloc[:-horizon].replace([np.inf, -np.inf], np.nan).dropna()
    quantiles = completed.quantile([.05, .25, .50, .75, .95]) if len(completed) >= 40 else pd.Series(dtype=float)
    q05, q25 = float(quantiles.get(.05, -.05)), float(quantiles.get(.25, -.02))
    q50, q75, q95 = (float(quantiles.get(.50, 0.0)), float(quantiles.get(.75, .02)),
                     float(quantiles.get(.95, .05)))
    day = timeframes["1D"]
    support, resistance = day.get("support"), day.get("resistance")
    bull_target = max(float(resistance or close), close * (1.0 + max(q75, .005)))
    bull_extended = max(bull_target, close * (1.0 + max(q95, .01)))
    bear_target = min(float(support or close), close * (1.0 + min(q25, -.005)))
    extreme_downside = min(bear_target, close * (1.0 + min(q05, -.02)))
    scenario_weights = _scenario_weights(combined)
    conclusion = "BULLISH_BIAS" if combined >= 25 else "BEARISH_BIAS" if combined <= -25 else "RANGE_OR_TRANSITION"
    return {
        "status": "OK", "symbol": symbol, "as_of": frame.iloc[-1]["time"],
        "close": round(close, 2), "horizon_sessions": horizon,
        "index_score": round(index_score, 1), "breadth": breadth,
        "combined_score": round(combined, 1), "conclusion": conclusion,
        "scenario_weights": scenario_weights,
        "levels": {"bull_trigger": None if resistance is None else round(float(resistance), 2),
                   "bull_target": round(bull_target, 2), "bull_extended": round(bull_extended, 2),
                   "range_mid": round(close * (1.0 + q50), 2),
                   "bear_trigger": None if support is None else round(float(support), 2),
                   "bear_target": round(bear_target, 2), "extreme_downside": round(extreme_downside, 2)},
        "historical_distribution_pct": {"p05": round(q05 * 100, 2), "p25": round(q25 * 100, 2),
            "median": round(q50 * 100, 2), "p75": round(q75 * 100, 2), "p95": round(q95 * 100, 2),
            "observations": int(len(completed))},
        "timeframes": timeframes,
        "warnings": (["BREADTH_UNAVAILABLE"] if breadth["status"] != "OK" else [])
                    + (["SMALL_BREADTH_SAMPLE"] if 0 < breadth["sample"] < 20 else []),
        "method": "Technical 65% + equal-count scanner breadth 35% when sample >=20; targets use completed historical forward-return quantiles. Scenario weights are heuristic, not calibrated probabilities.",
    }


def _quote_values(raw) -> dict:
    """Flatten provider quote shapes without assuming one VNStock version."""
    frame = pd.DataFrame(raw)
    if frame.empty:
        return {}
    row = frame.iloc[-1]
    values = {}
    for column, value in row.items():
        key = str(column[-1] if isinstance(column, tuple) else column).lower().strip()
        if key not in values or pd.isna(values[key]):
            values[key] = value
    return values


def load_index_quote(symbol: str = "VNINDEX") -> dict:
    """Fetch the provider's current index snapshot and compare with prior close."""
    symbol = str(symbol).upper().strip()
    errors = {}
    for module_name in ("vnstock.ui", "vnstock_data"):
        for source in ("kbs", "vci"):
            started = time.perf_counter()
            try:
                module = __import__(module_name, fromlist=["Market"])
                end = date.today()
                raw = module.Market().index(symbol).ohlcv(
                    start=(end - timedelta(days=10)).isoformat(), end=end.isoformat(),
                    interval="1D", count=10, source=source,
                )
                frame = _normalise_index(raw)
                if frame.empty:
                    raise ValueError("Snapshot chỉ số rỗng.")
                latest = frame.iloc[-1]
                price = float(latest["close"])
                reference = float(frame.iloc[-2]["close"]) if len(frame) >= 2 else None
                cache_path = INDEX_CACHE_DIR / f"{symbol.lower()}_1d.csv"
                if reference is None and cache_path.exists():
                    cached = _normalise_index(pd.read_csv(cache_path))
                    earlier = cached[pd.to_datetime(cached["time"]).dt.date < pd.Timestamp(latest["time"]).date()]
                    if not earlier.empty:
                        reference = float(earlier.iloc[-1]["close"])
                change = None if reference is None else price - reference
                change_pct = None if not reference else change / reference * 100
                return {
                    "status": "OK", "symbol": symbol, "price": price, "reference_price": reference,
                    "change": change, "change_pct": change_pct,
                    "market_time": pd.Timestamp(latest["time"]).isoformat(),
                    "provider": f"{module_name}:{source.upper()}",
                    "source_label": f"{source.upper()} qua VNStock · market snapshot",
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "request_latency_ms": round((time.perf_counter() - started) * 1000), "errors": errors,
                }
            except BaseException as exc:
                errors[f"{module_name}:{source}"] = f"{type(exc).__name__}: {exc}"
    return {"status": "ERROR", "symbol": symbol, "price": None,
            "received_at": datetime.now(timezone.utc).isoformat(), "errors": errors}
