from __future__ import annotations
import numpy as np
import pandas as pd
from .data import cache_diagnostics

from .timeframes import resample_ohlcv, TIMEFRAME_ORDER, TIMEFRAME_CONFIG
from .indicators import add_indicators, ma_regime, rsi_state
from .wyckoff import analyze_wyckoff

TIMEFRAMES = TIMEFRAME_ORDER


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _timeframe_score(latest: pd.Series, wy: dict, ma: str, rsi_s: str) -> tuple[float, int, list[str], dict]:
    """Điểm liên tục giúp tín hiệu ổn định hơn các luật đúng/sai đơn lẻ."""
    evidence = 0
    reasons: list[str] = []
    components = {"ma": 0.0, "wyckoff": 0.0, "rsi": 0.0, "momentum": 0.0,
                  "macd": 0.0, "trend_strength": 0.0, "money_flow": 0.0,
                  "volume": 0.0, "risk": 0.0}

    ma_points = {
        "STRONG_BULLISH": 32, "BULLISH": 24, "RECOVERY": 12,
        "MIXED": 0, "PULLBACK": -8, "BEARISH": -24,
        "STRONG_BEARISH": -32,
    }.get(ma, 0)
    if ma != "INSUFFICIENT_HISTORY":
        components["ma"] = float(ma_points)
        evidence += 1
        reasons.append(f"MA {ma.replace('_', ' ').lower()}")

    event_points = {"SPRING": 28, "SOS": 30, "LPS": 22, "UT": -28, "SOW": -30}
    if wy.get("event") in event_points:
        components["wyckoff"] = float(event_points[wy["event"]])
        reasons.append(f"Wyckoff {wy['event']}")
    else:
        components["wyckoff"] = float({"BULLISH": 12, "BEARISH": -12}.get(wy.get("bias"), 0))
    evidence += 1

    rsi_value = latest.get("rsi14")
    if pd.notna(rsi_value):
        rsi_value = float(rsi_value)
        # Momentum tốt nhất quanh 55-65; quá nóng/quá bán bị giảm điểm.
        components["rsi"] = _clamp((rsi_value - 50) * 0.8, -16, 16)
        if rsi_value >= 75:
            components["risk"] -= 10
            reasons.append("RSI quá nóng")
        elif rsi_value <= 25:
            components["risk"] += 4 if wy.get("bias") == "BULLISH" else -6
            reasons.append("RSI quá bán")
        evidence += 1

    roc20 = latest.get("roc20")
    if pd.notna(roc20):
        components["momentum"] = _clamp(float(roc20) * 0.7, -12, 12)
        evidence += 1

    macd_hist = latest.get("macd_hist")
    macd_value = latest.get("macd")
    macd_signal = latest.get("macd_signal")
    if pd.notna(macd_hist) and pd.notna(macd_value) and pd.notna(macd_signal):
        close_value = max(abs(float(latest.get("close", 0) or 0)), 1e-9)
        # Chuẩn hoá histogram theo giá để không thiên lệch về cổ phiếu thị giá cao.
        components["macd"] = _clamp(float(macd_hist) / close_value * 500.0, -10, 10)
        evidence += 1

    adx = latest.get("adx14")
    plus_di = latest.get("plus_di14")
    minus_di = latest.get("minus_di14")
    if pd.notna(adx) and pd.notna(plus_di) and pd.notna(minus_di):
        adx_strength = _clamp((float(adx) - 18.0) * 0.45, 0, 8)
        components["trend_strength"] = adx_strength if float(plus_di) > float(minus_di) else -adx_strength
        if float(adx) < 18:
            reasons.append("ADX thấp: xu hướng chưa rõ")
        evidence += 1

    obv = latest.get("obv")
    obv_ema = latest.get("obv_ema20")
    if pd.notna(obv) and pd.notna(obv_ema):
        components["money_flow"] = 5.0 if float(obv) > float(obv_ema) else -5.0
        evidence += 1

    rvol = latest.get("rvol")
    if pd.notna(rvol):
        rvol = float(rvol)
        subtotal = sum(components.values())
        direction = 1 if subtotal > 0 else -1 if subtotal < 0 else 0
        if rvol >= 1.2:
            components["volume"] = direction * min(8.0, (rvol - 1.0) * 8)
            reasons.append(f"RVOL {rvol:.1f}x xác nhận")
        evidence += 1

    score = sum(components.values())
    rounded_components = {key: round(value, 1) for key, value in components.items()}
    # Confidence của từng khung không còn chỉ đo "có đủ cột dữ liệu". Nó kết
    # hợp độ phủ bằng chứng (60%) và độ rõ của chính tín hiệu (40%).
    coverage = min(100.0, evidence * 20.0)
    strength = min(100.0, abs(score) / 60.0 * 100.0)
    frame_confidence = round(coverage * 0.60 + strength * 0.40)
    return round(_clamp(score), 1), frame_confidence, reasons[:3], rounded_components


def _portfolio_diagnostics(tfs: dict, consensus: float, quality: dict) -> dict:
    weights = {"1D": 1.0, "1W": 1.5, "1M": 1.5, "1Y": 0.75}
    valid = [(tf, r, weights[tf]) for tf, r in tfs.items() if r.get("status") == "OK"]
    coverage = 0.0 if not weights else sum(w for _, _, w in valid) / sum(weights.values()) * 100
    evidence = 0.0 if not valid else np.average([r.get("confidence", 0) for _, r, _ in valid], weights=[w for _, _, w in valid])
    active = [(float(r.get("signal_score", 0) or 0), w) for _, r, w in valid if abs(float(r.get("signal_score", 0) or 0)) >= 8]
    dominant = 1 if consensus > 0 else -1 if consensus < 0 else 0
    active_weight = sum(w for _, w in active)
    aligned_weight = sum(w for score, w in active if np.sign(score) == dominant)
    alignment = 0 if not active_weight or dominant == 0 else round(aligned_weight / active_weight * 100)
    conflict = "CAO" if alignment < 60 and active_weight else "TRUNG BÌNH" if alignment < 80 and active_weight else "THẤP"
    strength = min(100.0, abs(consensus) / 55.0 * 100.0)
    confidence = round(coverage * .25 + evidence * .25 + alignment * .30 + strength * .20)
    quality_state = quality.get("data_quality", "REJECT")
    if quality_state == "WATCH": confidence = min(confidence, 55)
    elif quality_state == "REJECT": confidence = min(confidence, 25)

    aggregate = {name: 0.0 for name in ("ma", "wyckoff", "rsi", "momentum", "macd",
                                                 "trend_strength", "money_flow", "volume", "risk")}
    weight_total = sum(w for _, _, w in valid) or 1.0
    for _, frame, weight in valid:
        for name, value in frame.get("component_scores", {}).items():
            aggregate[name] += float(value) * weight / weight_total
    labels = {"ma": "Xu hướng MA", "wyckoff": "Cấu trúc Wyckoff", "rsi": "RSI",
              "momentum": "Động lượng ROC", "macd": "MACD", "trend_strength": "ADX/DMI",
              "money_flow": "Dòng tiền OBV", "volume": "Khối lượng RVOL", "risk": "Điều chỉnh rủi ro"}
    ranked = sorted(aggregate.items(), key=lambda item: abs(item[1]), reverse=True)
    drivers = [{"name": labels[name], "score": round(score, 1),
                "direction": "TĂNG" if score > 0 else "GIẢM" if score < 0 else "TRUNG TÍNH"}
               for name, score in ranked if abs(score) >= 1][:4]
    return {"confidence": confidence, "alignment": alignment, "coverage": round(coverage),
            "evidence_quality": round(evidence), "conflict_level": conflict, "drivers": drivers,
            "component_totals": {name: round(value, 1) for name, value in aggregate.items()}}


def _multi_timeframe_decision(tfs: dict, consensus: float, confidence: int, alignment: int) -> dict:
    """Kết hợp trigger ngắn hạn với xu hướng trung-dài hạn và các cờ rủi ro."""
    strategic_weights = {"1W": 0.40 / 0.75, "1M": 0.35 / 0.75}
    strategic_num = strategic_den = 0.0
    for tf, weight in strategic_weights.items():
        result = tfs.get(tf, {})
        if result.get("status") == "OK":
            strategic_num += result.get("signal_score", 0) * weight
            strategic_den += weight
    strategic = 0.0 if strategic_den == 0 else strategic_num / strategic_den
    tactical = float(tfs.get("1D", {}).get("signal_score", 0) or 0)

    risk_flags: list[str] = []
    day = tfs.get("1D", {})
    # Bỏ qua nhiễu quanh mốc 0. Chỉ gọi là xung đột khi đồng thời
    # có khung nghiêng tăng và khung nghiêng giảm đủ rõ (|score| >= 8).
    bullish_frames: list[str] = []
    bearish_frames: list[str] = []
    for tf in TIMEFRAMES:
        frame = tfs.get(tf, {})
        if frame.get("status") != "OK":
            continue
        score = float(frame.get("signal_score", 0) or 0)
        if score >= 8:
            bullish_frames.append(f"{tf} {frame.get('signal', 'N/A')} ({score:+.1f})")
        elif score <= -8:
            bearish_frames.append(f"{tf} {frame.get('signal', 'N/A')} ({score:+.1f})")
    if bullish_frames and bearish_frames:
        risk_flags.append(
            "Xung đột đa khung — nghiêng tăng: "
            + ", ".join(bullish_frames)
            + "; nghiêng giảm: "
            + ", ".join(bearish_frames)
            + ". Ưu tiên chờ các khung 1W–1M đồng thuận với 1D trước khi hành động."
        )
    if (day.get("rsi14") or 0) >= 75:
        risk_flags.append("RSI ngày quá nóng")
    if (day.get("atr_pct") or 0) >= 5:
        risk_flags.append("Biến động ngày cao")
    if consensus > 20 and (day.get("rvol") or 0) < 0.7:
        risk_flags.append("Khối lượng chưa xác nhận")
    if tfs.get("1Y", {}).get("status") != "OK":
        risk_flags.append("Khung năm thiếu lịch sử")

    if consensus >= 55 and strategic >= 35 and tactical >= 20 and confidence >= 70:
        action = "MUA_CÓ_XÁC_NHẬN"
        summary = "Xu hướng trung hạn và trigger ngày cùng xác nhận chiều tăng."
    elif consensus >= 25 and strategic >= 15:
        action = "THEO_DÕI_MUA"
        summary = "Bối cảnh nghiêng tăng nhưng chưa đủ đồng thuận để xác nhận mua mạnh."
    elif consensus >= 8:
        action = "NẮM_GIỮ"
        summary = "Xu hướng còn tích cực nhẹ; ưu tiên quản lý vị thế hiện có."
    elif consensus <= -55 and strategic <= -35:
        action = "BÁN_CÓ_XÁC_NHẬN"
        summary = "Các khung quan trọng đồng thuận giảm; ưu tiên bảo vệ vốn."
    elif consensus <= -25:
        action = "GIẢM_TỶ_TRỌNG"
        summary = "Cấu trúc tổng hợp suy yếu; nên hạ mức rủi ro."
    else:
        action = "CHỜ_XÁC_NHẬN"
        summary = "Tín hiệu chưa đủ rõ hoặc đang xung đột giữa các khung."

    decision = {
        "system_action": action,
        "decision_summary": summary,
        "strategic_score": round(strategic, 1),
        "tactical_score": round(tactical, 1),
        "risk_flags": risk_flags,
    }
    decision["strategy_plan"] = _build_strategy_plan(tfs, decision)
    return decision


def _build_strategy_plan(tfs: dict, decision: dict) -> dict:
    """Sinh kế hoạch tham khảo từ cấu trúc 1D; không tạo hoặc gửi lệnh."""
    day = tfs.get("1D", {})
    action = decision["system_action"]
    close = day.get("close")
    atr = day.get("atr14")
    support = day.get("support")
    resistance = day.get("resistance")
    if day.get("status") != "OK" or close is None or atr is None or atr <= 0:
        return {
            "status": "NO_PLAN",
            "strategy": "KHÔNG_GIAO_DỊCH",
            "note": "Không đủ giá, ATR hoặc cấu trúc hỗ trợ/kháng cự để lập kế hoạch.",
        }

    close, atr = float(close), float(atr)
    support = None if support is None else float(support)
    resistance = None if resistance is None else float(resistance)
    trigger = resistance * 1.005 if resistance else close + atr
    invalidation = support - 0.5 * atr if support else close - 2 * atr

    if action in {"MUA_CÓ_XÁC_NHẬN", "THEO_DÕI_MUA"}:
        entry_low = max(0.01, close - 0.5 * atr)
        entry_high = close + 0.25 * atr
        entry_mid = (entry_low + entry_high) / 2
        stop = min(invalidation, entry_low - atr)
        risk = max(entry_mid - stop, 0.01)
        target1 = max(resistance or 0, entry_mid + 2 * risk)
        target2 = entry_mid + 3 * risk
        strategy = "MUA_KHI_BREAKOUT" if action == "MUA_CÓ_XÁC_NHẬN" else "CHỜ_BREAKOUT_HOẶC_PULLBACK"
        return {
            "status": "READY" if action == "MUA_CÓ_XÁC_NHẬN" else "WAIT_TRIGGER",
            "strategy": strategy,
            "entry_low": round(entry_low, 2),
            "entry_high": round(entry_high, 2),
            "trigger": round(trigger, 2),
            "stop_loss": round(stop, 2),
            "target_1": round(target1, 2),
            "target_2": round(target2, 2),
            "reward_risk_1": round((target1 - entry_mid) / risk, 2),
            "position_formula": "Số CP = (Vốn × % rủi ro/lệnh) ÷ (Giá vào − Cắt lỗ)",
            "note": "Chỉ kích hoạt khi giá/khối lượng xác nhận; không mua đuổi ngoài vùng vào.",
        }

    if action == "NẮM_GIỮ":
        return {
            "status": "MANAGE_POSITION",
            "strategy": "NẮM_GIỮ_VÀ_DỜI_CẮT_LỖ",
            "protective_stop": round(invalidation, 2),
            "reference_target": None if resistance is None else round(resistance, 2),
            "note": "Không phải điểm mua mới; theo dõi hỗ trợ và giảm rủi ro nếu cấu trúc bị phá.",
        }

    if action in {"GIẢM_TỶ_TRỌNG", "BÁN_CÓ_XÁC_NHẬN"}:
        return {
            "status": "PROTECT_CAPITAL",
            "strategy": "THOÁT_VỊ_THẾ" if "BÁN" in action else "GIẢM_TỶ_TRỌNG",
            "support_reference": None if support is None else round(support, 2),
            "recovery_level": None if resistance is None else round(resistance, 2),
            "note": "Không mở vị thế mua mới; ưu tiên tuân thủ kế hoạch bảo vệ vốn.",
        }

    return {
        "status": "NO_TRADE",
        "strategy": "CHỜ_TÍN_HIỆU_RÕ_RÀNG",
        "bullish_trigger": round(trigger, 2),
        "bearish_invalidation": round(invalidation, 2),
        "note": "Chưa có lợi thế đủ rõ; không giao dịch là một lựa chọn hợp lệ.",
    }


def _signal_from_score(score: float, confidence: int) -> str:
    if confidence < 40:
        return "WATCH"
    if score >= 58:
        return "BUY"
    if score >= 25:
        return "WATCH_BUY"
    if score <= -58:
        return "SELL"
    if score <= -25:
        return "REDUCE"
    if score >= 8:
        return "HOLD"
    if score <= -8:
        return "AVOID"
    return "WATCH"


def _signal(wy: dict, ma: str, rsi_s: str) -> str:
    bull_w = wy["bias"] == "BULLISH" or wy["event"] in {"SPRING", "SOS", "LPS"}
    bear_w = wy["bias"] == "BEARISH" or wy["event"] in {"UT", "SOW"}

    bull_ma = ma in {"STRONG_BULLISH", "BULLISH", "RECOVERY"}
    bear_ma = ma in {"STRONG_BEARISH", "BEARISH"}

    bull_rsi = rsi_s in {"POSITIVE", "STRONG"}
    bear_rsi = rsi_s in {"WEAK", "OVERSOLD"}

    if bull_w and bull_ma and bull_rsi:
        return "BUY"
    if bear_w and bear_ma and bear_rsi:
        return "SELL"
    if bull_w and bull_ma:
        return "WATCH_BUY"
    if bear_w and bear_ma:
        return "REDUCE"
    if ma in {"STRONG_BULLISH", "BULLISH"}:
        return "HOLD"
    if ma in {"STRONG_BEARISH", "BEARISH"}:
        return "AVOID"
    return "WATCH"


def analyze_timeframe(df: pd.DataFrame, timeframe: str) -> dict:
    tf = resample_ohlcv(df, timeframe)
    if len(tf) < 5:
        return {
            "timeframe": timeframe,
            "bar_period": TIMEFRAME_CONFIG[timeframe]["period"],
            "bars": len(tf),
            "status": "INSUFFICIENT_HISTORY",
        }

    x = add_indicators(tf)
    latest = x.iloc[-1]
    wy = analyze_wyckoff(x)

    ma = ma_regime(latest)
    rsi_value = latest["rsi14"]
    rs = rsi_state(rsi_value)
    score, confidence, reasons, components = _timeframe_score(latest, wy, ma, rs)
    sig = _signal_from_score(score, confidence)

    return {
        "timeframe": timeframe,
        "bar_period": TIMEFRAME_CONFIG[timeframe]["period"],
        "bars": len(x),
        "status": "OK",
        "close": round(float(latest["close"]), 2),
        "ma20": None if pd.isna(latest["ma20"]) else round(float(latest["ma20"]), 2),
        "ma50": None if pd.isna(latest["ma50"]) else round(float(latest["ma50"]), 2),
        "ma100": None if pd.isna(latest["ma100"]) else round(float(latest["ma100"]), 2),
        "ma200": None if pd.isna(latest["ma200"]) else round(float(latest["ma200"]), 2),
        "ma_regime": ma,
        "rsi14": None if pd.isna(rsi_value) else round(float(rsi_value), 2),
        "rsi_state": rs,
        "rvol": None if pd.isna(latest["rvol"]) else round(float(latest["rvol"]), 2),
        "atr14": None if pd.isna(latest["atr14"]) else round(float(latest["atr14"]), 2),
        "atr_pct": None if pd.isna(latest["atr_pct"]) else round(float(latest["atr_pct"]), 2),
        "roc20": None if pd.isna(latest["roc20"]) else round(float(latest["roc20"]), 2),
        "volatility20": None if pd.isna(latest["volatility20"]) else round(float(latest["volatility20"]), 2),
        "macd": None if pd.isna(latest["macd"]) else round(float(latest["macd"]), 3),
        "macd_signal": None if pd.isna(latest["macd_signal"]) else round(float(latest["macd_signal"]), 3),
        "macd_hist": None if pd.isna(latest["macd_hist"]) else round(float(latest["macd_hist"]), 3),
        "adx14": None if pd.isna(latest["adx14"]) else round(float(latest["adx14"]), 2),
        "plus_di14": None if pd.isna(latest["plus_di14"]) else round(float(latest["plus_di14"]), 2),
        "minus_di14": None if pd.isna(latest["minus_di14"]) else round(float(latest["minus_di14"]), 2),
        "obv_bias": "POSITIVE" if pd.notna(latest["obv"]) and pd.notna(latest["obv_ema20"]) and latest["obv"] > latest["obv_ema20"] else "NEGATIVE" if pd.notna(latest["obv"]) and pd.notna(latest["obv_ema20"]) else "INSUFFICIENT_HISTORY",
        "wyckoff_phase": wy["phase"],
        "wyckoff_event": wy["event"],
        "wyckoff_bias": wy["bias"],
        "support": None if wy["support"] is None else round(float(wy["support"]), 2),
        "resistance": None if wy["resistance"] is None else round(float(wy["resistance"]), 2),
        "signal": sig,
        "signal_score": score,
        "confidence": confidence,
        "reasons": reasons,
        "component_scores": components,
    }


def analyze_symbol(symbol: str, df: pd.DataFrame, reference_date=None) -> dict:
    tfs = {tf: analyze_timeframe(df, tf) for tf in TIMEFRAMES}

    # Trung hạn có trọng số cao hơn; điểm liên tục tránh mất thông tin khi làm phẳng.
    weights = {"1D": 1.0, "1W": 1.5, "1M": 1.5, "1Y": 0.75}
    num = den = 0.0
    for tf, r in tfs.items():
        if r.get("status") == "OK":
            w = weights[tf]
            num += r.get("signal_score", 0) * w
            den += 100 * w

    consensus = 0.0 if den == 0 else num / den * 100
    quality = cache_diagnostics(df, reference_date=reference_date)
    diagnostics = _portfolio_diagnostics(tfs, consensus, quality)
    confidence = diagnostics["confidence"]
    alignment = diagnostics["alignment"]
    decision = _multi_timeframe_decision(tfs, consensus, confidence, alignment)

    if consensus >= 55:
        final_signal = "STRONG_BUY"
    elif consensus >= 25:
        final_signal = "BUY"
    elif consensus <= -55:
        final_signal = "STRONG_SELL"
    elif consensus <= -25:
        final_signal = "SELL"
    else:
        final_signal = "WATCH"

    quality_warnings = []
    if quality["data_quality"] == "REJECT":
        quality_warnings.append("Dữ liệu quá ít hoặc quá cũ; không đủ điều kiện phát tín hiệu giao dịch.")
    elif quality["data_quality"] == "WATCH":
        quality_warnings.append("Dữ liệu/thanh khoản cần thận trọng; tín hiệu chỉ dùng để theo dõi.")
    if quality["data_quality"] != "GOOD":
        final_signal = "WATCH"
        decision["system_action"] = "CHỜ_XÁC_NHẬN"
        decision["decision_summary"] = quality_warnings[0]
        decision["risk_flags"] = quality_warnings + decision.get("risk_flags", [])
        decision["strategy_plan"] = {
            "status": "NO_TRADE", "strategy": "CHỜ_DỮ_LIỆU_VÀ_THANH_KHOẢN",
            "note": quality_warnings[0],
        }

    if confidence >= 80 and alignment >= 80 and abs(consensus) >= 35 and not decision.get("risk_flags"):
        grade = "A"
    elif confidence >= 68 and alignment >= 70 and abs(consensus) >= 25:
        grade = "B"
    elif confidence >= 50:
        grade = "C"
    else:
        grade = "D"
    if quality["data_quality"] == "WATCH" and grade in {"A", "B"}: grade = "C"
    if quality["data_quality"] == "REJECT": grade = "D"

    strategic = float(decision.get("strategic_score", 0) or 0)
    market_regime = "XU HƯỚNG TĂNG" if strategic >= 20 else "XU HƯỚNG GIẢM" if strategic <= -20 else "ĐI NGANG / CHUYỂN PHA"

    return {
        "symbol": symbol,
        "final_signal": final_signal,
        "consensus_score": round(consensus, 1),
        "confidence": confidence,
        "timeframe_alignment": alignment,
        "data_quality": quality,
        "decision_grade": grade,
        "market_regime": market_regime,
        "evidence_coverage": diagnostics["coverage"],
        "evidence_quality": diagnostics["evidence_quality"],
        "conflict_level": diagnostics["conflict_level"],
        "decision_drivers": diagnostics["drivers"],
        "component_totals": diagnostics["component_totals"],
        "engine_version": "PRO_DECISION_4TF_MACD_ADX_OBV",
        **decision,
        "timeframes": tfs,
    }


def flatten_analysis(result: dict) -> dict:
    plan = result.get("strategy_plan", {})
    row = {
        "symbol": result["symbol"],
        "final_signal": result["final_signal"],
        "consensus_score": result["consensus_score"],
        "confidence": result.get("confidence"),
        "timeframe_alignment": result.get("timeframe_alignment"),
        "decision_grade": result.get("decision_grade"),
        "market_regime": result.get("market_regime"),
        "evidence_coverage": result.get("evidence_coverage"),
        "evidence_quality": result.get("evidence_quality"),
        "conflict_level": result.get("conflict_level"),
        "decision_drivers": " | ".join(f"{item['name']} {item['score']:+.1f}" for item in result.get("decision_drivers", [])),
        "engine_version": result.get("engine_version"),
        "system_action": result.get("system_action"),
        "strategic_score": result.get("strategic_score"),
        "tactical_score": result.get("tactical_score"),
        "risk_flags": " | ".join(result.get("risk_flags", [])),
        "strategy": plan.get("strategy"),
        "strategy_status": plan.get("status"),
        "entry_low": plan.get("entry_low"),
        "entry_high": plan.get("entry_high"),
        "trigger": plan.get("trigger") or plan.get("bullish_trigger"),
        "stop_loss": plan.get("stop_loss") or plan.get("protective_stop"),
        "target_1": plan.get("target_1") or plan.get("reference_target"),
        "target_2": plan.get("target_2"),
        "reward_risk_1": plan.get("reward_risk_1"),
        "data_quality": result.get("data_quality", {}).get("data_quality"),
        "recent_nonzero_volume_ratio": result.get("data_quality", {}).get("recent_nonzero_volume_ratio"),
        "median_turnover_20d_vnd": result.get("data_quality", {}).get("median_turnover_20d_vnd"),
    }

    for tf, r in result["timeframes"].items():
        prefix = tf.lower()
        for key in [
            "status", "close", "ma20", "ma50", "ma100", "ma200",
            "ma_regime", "rsi14", "rsi_state", "rvol",
            "wyckoff_phase", "wyckoff_event", "wyckoff_bias",
            "support", "resistance", "signal", "signal_score", "confidence",
            "atr14", "atr_pct", "roc20", "volatility20", "macd", "macd_signal",
            "macd_hist", "adx14", "plus_di14", "minus_di14", "obv_bias"
        ]:
            row[f"{prefix}_{key}"] = r.get(key)
    return row
