from __future__ import annotations
import numpy as np
import pandas as pd


def _levels(df: pd.DataFrame, window: int = 20) -> dict:
    recent = df.tail(min(window, len(df)))
    return {
        "range_high": float(recent["high"].max()),
        "range_low": float(recent["low"].min()),
        "support": float(recent["low"].rolling(5, min_periods=1).min().iloc[-1]),
        "resistance": float(recent["high"].rolling(5, min_periods=1).max().iloc[-1]),
    }


def analyze_wyckoff(df: pd.DataFrame) -> dict:
    if len(df) < 10:
        return {
            "phase": "INSUFFICIENT_HISTORY",
            "event": "NONE",
            "bias": "NEUTRAL",
            "range_high": None,
            "range_low": None,
            "support": None,
            "resistance": None,
        }

    x = df.copy()
    levels = _levels(x, 20)
    latest = x.iloc[-1]
    prev = x.iloc[-2]

    price = float(latest["close"])
    low = float(latest["low"])
    high = float(latest["high"])
    rvol = float(latest.get("rvol", 1.0) or 1.0)

    rh = levels["range_high"]
    rl = levels["range_low"]

    event = "NONE"
    phase = "TRADING_RANGE"
    bias = "NEUTRAL"

    # Use previous 20-bar boundaries to avoid self-referencing latest bar.
    hist = x.iloc[:-1].tail(min(20, len(x)-1))
    if len(hist) >= 5:
        prev_high = float(hist["high"].max())
        prev_low = float(hist["low"].min())

        if low < prev_low and price > prev_low:
            event, phase, bias = "SPRING", "ACCUMULATION", "BULLISH"
        elif price > prev_high and float(prev["close"]) <= prev_high and rvol >= 1.15:
            event, phase, bias = "SOS", "MARKUP", "BULLISH"
        elif high > prev_high and price < prev_high:
            event, phase, bias = "UT", "DISTRIBUTION", "BEARISH"
        elif price < prev_low and float(prev["close"]) >= prev_low and rvol >= 1.15:
            event, phase, bias = "SOW", "MARKDOWN", "BEARISH"
        else:
            pos = (price - prev_low) / max(prev_high - prev_low, 1e-9)
            if pos > 0.70:
                phase, bias = "UPPER_RANGE", "BULLISH"
            elif pos < 0.30:
                phase, bias = "LOWER_RANGE", "BEARISH"

    # LPS approximation only after bullish structural context.
    m20 = latest.get("ma20")
    m50 = latest.get("ma50")
    if (
        event == "NONE"
        and pd.notna(m20)
        and pd.notna(m50)
        and price > m20 > m50
        and low <= float(m20) * 1.01
        and rvol <= 1.2
    ):
        event, phase, bias = "LPS", "MARKUP", "BULLISH"

    return {
        "phase": phase,
        "event": event,
        "bias": bias,
        **levels,
    }
