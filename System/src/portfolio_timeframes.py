"""Read-only selected-frame evidence, separate from multi-frame trading plans."""
from .timeframes import TIMEFRAME_ORDER
from .futures_engine import FUTURES_CHART_TIMEFRAMES, analyze_futures_chart_frame


def portfolio_frame_evidence(result: dict, timeframe: str, *, futures_frames=None) -> dict:
    if timeframe == "MULTI":
        return {"Khung chọn":"MULTI", "Trạng thái khung":"MULTI_TIMEFRAME",
                "Signal khung":result.get("final_signal", result.get("action")),
                "Score khung":result.get("consensus_score", result.get("score")), "Số nến khung":None}
    options = TIMEFRAME_ORDER if futures_frames is None else FUTURES_CHART_TIMEFRAMES
    if timeframe not in options:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    frame = (result.get("timeframes", {}).get(timeframe, {}) if futures_frames is None
             else analyze_futures_chart_frame(futures_frames, timeframe))
    # A short annual history must not turn missing MA20/RSI14 into a neutral
    # or bullish assessment. Keep the main multi-frame report explicitly separate.
    valid = frame.get("status") == "OK" and frame.get("bars", 0) >= 20
    return {"Khung chọn":timeframe, "Trạng thái khung":"OK" if valid else "INSUFFICIENT_HISTORY",
            "Signal khung":frame.get("signal", frame.get("direction")) if valid else None,
            "Score khung":frame.get("signal_score", frame.get("score")) if valid else None,
            "Số nến khung":frame.get("bars", 0)}
