from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd

from .indicators import add_indicators, ma_regime
from .wyckoff import analyze_wyckoff
from .timeframes import resample_ohlcv, TIMEFRAME_ORDER


@dataclass(frozen=True)
class FuturesRiskConfig:
    contract_multiplier_vnd: int = 100_000
    initial_margin_ratio: float = 0.17
    target_margin_utilization: float = 0.30
    risk_per_trade: float = 0.005
    max_daily_loss_pct: float = 0.015
    max_trades_per_day: int = 3
    min_stop_points: float = 2.0
    max_stop_points: float = 4.0
    fee_per_contract_side_vnd: float = 6_000


DEFAULT_FUTURES_RISK = FuturesRiskConfig()
FRAME_WEIGHTS = {"1D": 0.35, "1H": 0.40, "15M": 0.25}
FUTURES_CHART_TIMEFRAMES = ["15M", "1H", *TIMEFRAME_ORDER]


def analyze_futures_chart_frame(frames: dict, timeframe: str) -> dict:
    """Chart/portfolio-only view; does not alter the BOT's intraday strategy."""
    if timeframe not in FUTURES_CHART_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    base = frames.get("1D" if timeframe in TIMEFRAME_ORDER else timeframe, pd.DataFrame())
    if base.empty:
        return {"status":"INSUFFICIENT_DATA", "timeframe":timeframe, "bars":0, "data":base}
    candles = resample_ohlcv(base, timeframe) if timeframe in TIMEFRAME_ORDER else base.copy()
    result = _frame_analysis(candles, timeframe)
    if result.get("status") != "OK":
        result.update(direction="INSUFFICIENT_HISTORY", ma_regime="INSUFFICIENT_HISTORY",
                      wyckoff_phase="INSUFFICIENT_HISTORY", wyckoff_bias="N/A", wyckoff_event="N/A")
    # Even one genuine yearly candle is drawable, but cannot justify a signal.
    result.update(bars=len(candles), data=add_indicators(candles))
    return result


def _clip(value: float, low: float = -100, high: float = 100) -> float:
    return float(max(low, min(high, value)))


def _level(frame: pd.DataFrame, side: str, window: int) -> float | None:
    if frame.empty:
        return None
    sample = frame.iloc[:-1].tail(window) if len(frame) > 1 else frame.tail(window)
    if sample.empty:
        return None
    return float(sample["low"].min() if side == "support" else sample["high"].max())


def fibonacci_analysis(frame: pd.DataFrame, lookback: int = 120) -> dict:
    """Build objective retracement/extension levels from the latest visible swing."""
    if frame is None or len(frame) < 20:
        return {"status": "INSUFFICIENT_DATA", "levels": {}}
    sample = frame.tail(max(20, min(int(lookback), len(frame))))
    swing_low = float(sample["low"].min())
    swing_high = float(sample["high"].max())
    amplitude = swing_high - swing_low
    if not np.isfinite(amplitude) or amplitude <= 0:
        return {"status": "INVALID_RANGE", "levels": {}}
    low_time = pd.Timestamp(sample.loc[sample["low"].idxmin(), "time"])
    high_time = pd.Timestamp(sample.loc[sample["high"].idxmax(), "time"])
    swing_direction = "UPSWING" if low_time < high_time else "DOWNSWING"
    last = sample.iloc[-1]
    close = float(last["close"])
    ma20 = last.get("ma20")
    ma50 = last.get("ma50")
    if pd.notna(ma20) and pd.notna(ma50) and close >= float(ma20) >= float(ma50):
        direction, direction_source = "UPSWING", "MA20_MA50_UPTREND"
    elif pd.notna(ma20) and pd.notna(ma50) and close <= float(ma20) <= float(ma50):
        direction, direction_source = "DOWNSWING", "MA20_MA50_DOWNTREND"
    else:
        direction, direction_source = swing_direction, "SWING_STRUCTURE"
    ratios = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
    if direction == "UPSWING":
        levels = {f"{ratio:.3f}": swing_high - amplitude * ratio for ratio in ratios}
        extensions = {
            "1.272": swing_high + amplitude * .272,
            "1.414": swing_high + amplitude * .414,
            "1.618": swing_high + amplitude * .618,
            "2.000": swing_high + amplitude,
        }
        golden_zone = sorted((levels["0.500"], levels["0.618"]))
    else:
        levels = {f"{ratio:.3f}": swing_low + amplitude * ratio for ratio in ratios}
        extensions = {
            "1.272": swing_low - amplitude * .272,
            "1.414": swing_low - amplitude * .414,
            "1.618": swing_low - amplitude * .618,
            "2.000": swing_low - amplitude,
        }
        golden_zone = sorted((levels["0.500"], levels["0.618"]))
    nearest_ratio, nearest_level = min(levels.items(), key=lambda item: abs(item[1] - close))
    return {
        "status": "OK", "direction": direction, "swing_direction": swing_direction,
        "direction_source": direction_source,
        "swing_low": round(swing_low, 1), "swing_high": round(swing_high, 1),
        "swing_low_time": low_time, "swing_high_time": high_time,
        "levels": {key: round(value, 1) for key, value in levels.items()},
        "extensions": {key: round(value, 1) for key, value in extensions.items()},
        "golden_zone": [round(value, 1) for value in golden_zone],
        "nearest_ratio": nearest_ratio, "nearest_level": round(nearest_level, 1),
    }


def _frame_analysis(frame: pd.DataFrame, timeframe: str) -> dict:
    if frame is None or len(frame) < 30:
        return {"status": "INSUFFICIENT_DATA", "timeframe": timeframe, "score": 0.0}
    x = add_indicators(frame)
    row = x.iloc[-1]
    score, reasons = 0.0, []
    regime = ma_regime(row)
    regime_points = {
        "STRONG_BULLISH": 32, "BULLISH": 24, "RECOVERY": 10,
        "PULLBACK": -8, "BEARISH": -24, "STRONG_BEARISH": -32,
    }.get(regime, 0)
    score += regime_points
    reasons.append(f"MA {regime}")

    wyckoff = analyze_wyckoff(x)
    fibonacci = fibonacci_analysis(x, 120)
    wy_event_points = {"SPRING": 18, "SOS": 22, "LPS": 14, "UT": -18, "SOW": -22}
    if wyckoff.get("event") in wy_event_points:
        score += wy_event_points[wyckoff["event"]]
        reasons.append(f"Wyckoff {wyckoff['event']}")
    else:
        score += {"BULLISH": 8, "BEARISH": -8}.get(wyckoff.get("bias"), 0)
        reasons.append(f"Wyckoff {wyckoff.get('phase','TRADING_RANGE')} · {wyckoff.get('bias','NEUTRAL')}")

    rsi = row.get("rsi14")
    if pd.notna(rsi):
        rsi = float(rsi)
        score += _clip((rsi - 50) * 0.8, -14, 14)
        if rsi >= 76:
            score -= 8; reasons.append("RSI quá nóng")
        elif rsi <= 24:
            score += 8; reasons.append("RSI quá bán")

    support = _level(x, "support", 24)
    resistance = _level(x, "resistance", 24)
    close = float(row["close"])
    if resistance is not None and close > resistance:
        score += 20; reasons.append("Breakout kháng cự")
    elif support is not None and close < support:
        score -= 20; reasons.append("Breakdown hỗ trợ")

    momentum = x["close"].pct_change(5, fill_method=None).iloc[-1]
    if pd.notna(momentum):
        score += _clip(float(momentum) * 250, -16, 16)
    rvol = row.get("rvol")
    if pd.notna(rvol) and float(rvol) >= 1.2:
        score += (6 if score > 0 else -6 if score < 0 else 0)
        reasons.append(f"RVOL {float(rvol):.1f}x")

    if fibonacci.get("status") == "OK":
        fib_direction = fibonacci["direction"]
        golden_low, golden_high = fibonacci["golden_zone"]
        if golden_low <= close <= golden_high:
            score += 5 if fib_direction == "UPSWING" else -5
            reasons.append(f"Fib golden zone {fib_direction}")
        else:
            reasons.append(f"Fib gần {fibonacci['nearest_ratio']}")

    score = round(_clip(score), 1)
    direction = "LONG" if score >= 18 else "SHORT" if score <= -18 else "NEUTRAL"
    return {
        "status": "OK", "timeframe": timeframe, "score": score, "direction": direction,
        "close": close, "ma_regime": regime,
        "rsi14": None if pd.isna(rsi) else round(float(rsi), 1),
        "rvol": None if pd.isna(rvol) else round(float(rvol), 2),
        "atr14": None if pd.isna(row.get("atr14")) else round(float(row["atr14"]), 2),
        "support": None if support is None else round(support, 1),
        "resistance": None if resistance is None else round(resistance, 1),
        "range_low": wyckoff.get("range_low"), "range_high": wyckoff.get("range_high"),
        "wyckoff_event": wyckoff.get("event", "NONE"),
        "wyckoff_phase": wyckoff.get("phase", "TRADING_RANGE"),
        "wyckoff_bias": wyckoff.get("bias", "NEUTRAL"),
        "fibonacci": fibonacci,
        "reasons": reasons[:5], "data": x,
    }


def futures_wyckoff_events(frame: pd.DataFrame, max_bars: int = 240) -> pd.DataFrame:
    """Return non-duplicated historical Wyckoff events for chart markers."""
    if frame is None or len(frame) < 20:
        return pd.DataFrame(columns=["time","price","event","phase","bias"])
    x = add_indicators(frame).tail(max_bars).reset_index(drop=True)
    events, previous = [], None
    for index in range(20, len(x)):
        sample = x.iloc[: index + 1]
        wy = analyze_wyckoff(sample)
        event = wy.get("event", "NONE")
        if event != "NONE" and event != previous:
            bar = sample.iloc[-1]
            bullish = event in {"SPRING","SOS","LPS"}
            events.append({"time":bar["time"],"price":float(bar["low"] if bullish else bar["high"]),
                           "event":event,"phase":wy.get("phase"),"bias":wy.get("bias")})
        previous = event if event != "NONE" else None
    return pd.DataFrame(events)


def position_size(
    equity_vnd: float,
    price: float,
    stop_points: float,
    config: FuturesRiskConfig = DEFAULT_FUTURES_RISK,
) -> dict:
    equity_vnd, price, stop_points = float(equity_vnd), float(price), float(stop_points)
    loss_per_contract = stop_points * config.contract_multiplier_vnd + 2 * config.fee_per_contract_side_vnd
    margin_per_contract = price * config.contract_multiplier_vnd * config.initial_margin_ratio
    by_risk = max(0, math.floor(equity_vnd * config.risk_per_trade / loss_per_contract))
    by_margin = max(0, math.floor(equity_vnd * config.target_margin_utilization / margin_per_contract))
    contracts = min(by_risk, by_margin)
    return {
        "contracts": contracts,
        "by_risk": by_risk,
        "by_margin": by_margin,
        "loss_per_contract_vnd": round(loss_per_contract),
        "margin_per_contract_vnd": round(margin_per_contract),
        "estimated_max_loss_vnd": round(contracts * loss_per_contract),
        "estimated_margin_vnd": round(contracts * margin_per_contract),
    }


def analyze_vn30f1m(
    frames: dict[str, pd.DataFrame],
    *,
    account_equity_vnd: float = 1_000_000_000,
    config: FuturesRiskConfig = DEFAULT_FUTURES_RISK,
    symbol: str = "VN30F1M",
) -> dict:
    analyses = {tf: _frame_analysis(frames.get(tf, pd.DataFrame()), tf) for tf in FRAME_WEIGHTS}
    valid = [(tf, r) for tf, r in analyses.items() if r.get("status") == "OK"]
    if not valid:
        return {"status": "NO_DATA", "symbol": symbol, "frames": analyses, "config": asdict(config)}
    weight_sum = sum(FRAME_WEIGHTS[tf] for tf, _ in valid)
    score = sum(r["score"] * FRAME_WEIGHTS[tf] for tf, r in valid) / weight_sum
    active = [r["direction"] for _, r in valid if r["direction"] != "NEUTRAL"]
    dominant = "LONG" if score >= 0 else "SHORT"
    alignment = round(sum(d == dominant for d in active) / len(active) * 100) if active else 0
    intraday = analyses.get("15M", {})
    hourly = analyses.get("1H", {})
    daily = analyses.get("1D", {})
    price = float(intraday.get("close") or hourly.get("close") or daily.get("close"))
    atr = float(intraday.get("atr14") or hourly.get("atr14") or 3.0)
    stop_points = round(max(config.min_stop_points, min(config.max_stop_points, atr * 0.8)), 1)
    supports = [r.get("support") for _, r in valid if r.get("support") is not None and r["support"] <= price]
    resistances = [r.get("resistance") for _, r in valid if r.get("resistance") is not None and r["resistance"] >= price]
    support = max(supports) if supports else round(price - stop_points, 1)
    resistance = min(resistances) if resistances else round(price + stop_points, 1)

    data_age_hours = None
    latest_times = [pd.Timestamp(frames[tf].iloc[-1]["time"]) for tf, _ in valid if not frames[tf].empty]
    if latest_times:
        newest = max(latest_times)
        now = pd.Timestamp.now(tz=newest.tz) if newest.tzinfo else pd.Timestamp.now()
        data_age_hours = max(0.0, (now - newest).total_seconds() / 3600)
    stale = data_age_hours is None or data_age_hours > 96
    conflict = any(r["direction"] == "LONG" for _, r in valid) and any(r["direction"] == "SHORT" for _, r in valid)

    if stale:
        action, regime = "NO_TRADE", "DATA_STALE"
    elif score >= 30 and alignment >= 67 and intraday.get("direction") != "SHORT":
        action, regime = "LONG", "UPTREND"
    elif score <= -30 and alignment >= 67 and intraday.get("direction") != "LONG":
        action, regime = "SHORT", "DOWNTREND"
    elif abs(score) < 18:
        action, regime = "STAND_ASIDE", "RANGE"
    else:
        action, regime = "WAIT_CONFIRMATION", "TRANSITION"

    if action == "LONG":
        entry_low, entry_high = max(support, price - 0.5 * stop_points), price + 0.2 * stop_points
        trigger, stop = entry_high, entry_low - stop_points
        target1, target2 = entry_high + stop_points, entry_high + 2 * stop_points
    elif action == "SHORT":
        entry_low, entry_high = price - 0.2 * stop_points, min(resistance, price + 0.5 * stop_points)
        trigger, stop = entry_low, entry_high + stop_points
        target1, target2 = entry_low - stop_points, entry_low - 2 * stop_points
    else:
        entry_low, entry_high, trigger, stop, target1, target2 = support, resistance, None, None, None, None

    sizing = position_size(account_equity_vnd, price, stop_points, config)
    confidence = round(min(95, 35 + abs(score) * 0.45 + alignment * 0.25 - (15 if conflict else 0)))
    risk_flags = []
    if stale: risk_flags.append("Dữ liệu quá cũ — khóa giao dịch")
    if conflict: risk_flags.append("Khung 15M/1H/1D đang xung đột")
    if sizing["contracts"] <= 0: risk_flags.append("Quy mô tài khoản không đủ giới hạn rủi ro/ký quỹ")
    return {
        "status": "OK", "symbol": symbol, "price": round(price, 1),
        "score": round(score, 1), "confidence": confidence, "alignment": alignment,
        "action": action, "regime": regime, "support": round(support, 1),
        "resistance": round(resistance, 1), "stop_points": stop_points,
        "plan": {
            "entry_low": round(entry_low, 1), "entry_high": round(entry_high, 1),
            "trigger": None if trigger is None else round(trigger, 1),
            "stop_loss": None if stop is None else round(stop, 1),
            "target_1": None if target1 is None else round(target1, 1),
            "target_2": None if target2 is None else round(target2, 1),
            "rule": "Chỉ kích hoạt khi nến 15M đóng cửa xác nhận; không đuổi giá ngoài vùng vào.",
        },
        "position_size": sizing, "frames": analyses, "risk_flags": risk_flags,
        "data_age_hours": None if data_age_hours is None else round(data_age_hours, 1),
        "config": asdict(config),
    }


def futures_ai_brief(result: dict) -> str:
    if result.get("status") != "OK":
        return f"Không đủ dữ liệu {result.get('symbol','Futures')} để lập kế hoạch; hệ thống khóa giao dịch."
    plan, sizing = result["plan"], result["position_size"]
    action_labels = {"LONG": "ƯU TIÊN LONG", "SHORT": "ƯU TIÊN SHORT", "STAND_ASIDE": "ĐỨNG NGOÀI", "WAIT_CONFIRMATION": "CHỜ XÁC NHẬN", "NO_TRADE": "KHÔNG GIAO DỊCH"}
    lines = [
        f"### AI Futures Desk · {action_labels.get(result['action'], result['action'])}",
        f"Xu hướng `{result['regime']}` · score **{result['score']:+.1f}** · đồng thuận **{result['alignment']}%** · tin cậy **{result['confidence']}%**.",
        f"Hỗ trợ **{result['support']:.1f}** · kháng cự **{result['resistance']:.1f}** · stop chuẩn hóa **{result['stop_points']:.1f} điểm**.",
    ]
    frame_summary = []
    for tf in ("15M","1H","1D"):
        frame = result.get("frames",{}).get(tf,{})
        frame_summary.append(
            f"`{tf}` {frame.get('direction','N/A')} · MA {frame.get('ma_regime','N/A')} · "
            f"RSI {frame.get('rsi14','—')} · Wyckoff {frame.get('wyckoff_event','NONE')}/"
            f"{frame.get('wyckoff_phase','N/A')}/{frame.get('wyckoff_bias','N/A')}"
        )
    lines.append("  \n".join(frame_summary))
    if result["action"] in {"LONG", "SHORT"}:
        lines.append(f"Vùng vào **{plan['entry_low']:.1f}–{plan['entry_high']:.1f}** · trigger **{plan['trigger']:.1f}** · stop **{plan['stop_loss']:.1f}** · TP **{plan['target_1']:.1f}/{plan['target_2']:.1f}**.")
        lines.append(f"Quy mô tối đa theo mô hình: **{sizing['contracts']} HĐ**; lỗ ước tính tối đa **{sizing['estimated_max_loss_vnd']:,.0f} ₫**.")
    else:
        lines.append("Không mở vị thế cho tới khi 15M xác nhận thoát vùng và 1H không phủ định hướng giao dịch.")
    if result.get("risk_flags"):
        lines.append("Rủi ro: " + " • ".join(result["risk_flags"]))
    lines.append("Đây là kế hoạch định lượng, không phải khuyến nghị đầu tư và không tự gửi lệnh thật.")
    return "\n\n".join(lines)
