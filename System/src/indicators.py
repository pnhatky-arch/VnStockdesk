from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)

    avg_up = up.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    avg_down = down.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    rs = avg_up / avg_down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)

    both_zero = (avg_up == 0) & (avg_down == 0)
    out = out.mask(both_zero, 50.0)
    out = out.mask((avg_down == 0) & (avg_up > 0), 100.0)

    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    for n in (20, 50, 100, 200):
        x[f"ma{n}"] = (
            x["close"]
            .rolling(n, min_periods=n)
            .mean()
        )

        x[f"ma{n}_slope"] = (
            x[f"ma{n}"]
            .pct_change(
                periods=3,
                fill_method=None,
            )
            * 100
        )

    x["rsi14"] = rsi(x["close"], 14)

    x["vol_ma20"] = (
        x["volume"]
        .rolling(20, min_periods=5)
        .mean()
    )

    x["rvol"] = (
        x["volume"]
        / x["vol_ma20"].replace(0, np.nan)
    )

    # ATR và biến động được chuẩn hoá theo giá để có thể so sánh giữa các mã.
    prev_close = x["close"].shift(1)
    true_range = pd.concat(
        [
            x["high"] - x["low"],
            (x["high"] - prev_close).abs(),
            (x["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    x["atr14"] = true_range.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()
    x["atr_pct"] = x["atr14"] / x["close"].replace(0, np.nan) * 100
    x["roc20"] = x["close"].pct_change(20, fill_method=None) * 100
    x["volatility20"] = (
        x["close"].pct_change(fill_method=None).rolling(20, min_periods=10).std()
        * np.sqrt(252)
        * 100
    )

    # MACD (12, 26, 9): đo động lượng theo chênh lệch hai EMA. Tự tính từ
    # OHLCV để engine không phụ thuộc plugin hay dịch vụ bên ngoài.
    ema12 = x["close"].ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = x["close"].ewm(span=26, adjust=False, min_periods=26).mean()
    x["macd"] = ema12 - ema26
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    x["macd_hist"] = x["macd"] - x["macd_signal"]

    # ADX/DMI dùng Wilder smoothing để phân biệt thị trường có xu hướng và
    # đi ngang. ADX chỉ đo độ mạnh; hướng được lấy từ +DI và -DI.
    up_move = x["high"].diff()
    down_move = -x["low"].diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    plus_smoothed = plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    minus_smoothed = minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    atr_safe = x["atr14"].replace(0, np.nan)
    x["plus_di14"] = 100 * plus_smoothed / atr_safe
    x["minus_di14"] = 100 * minus_smoothed / atr_safe
    di_sum = (x["plus_di14"] + x["minus_di14"]).replace(0, np.nan)
    dx = 100 * (x["plus_di14"] - x["minus_di14"]).abs() / di_sum
    x["adx14"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    # OBV xác nhận dòng tiền theo hướng đóng cửa. So sánh với EMA20 tránh
    # dùng trị tuyệt đối OBV vốn không thể so sánh trực tiếp giữa các mã.
    direction = np.sign(x["close"].diff()).fillna(0.0)
    x["obv"] = (direction * x["volume"].fillna(0.0)).cumsum()
    x["obv_ema20"] = x["obv"].ewm(span=20, adjust=False, min_periods=10).mean()

    return x


def ma_regime(row: pd.Series) -> str:
    p = row.get("close", np.nan)
    m20 = row.get("ma20", np.nan)
    m50 = row.get("ma50", np.nan)
    m100 = row.get("ma100", np.nan)
    m200 = row.get("ma200", np.nan)

    known = [v for v in (m20, m50, m100, m200) if pd.notna(v)]

    if (
        pd.notna(m20)
        and pd.notna(m50)
        and pd.notna(m100)
        and pd.notna(m200)
    ):
        if p > m20 > m50 > m100 > m200:
            return "STRONG_BULLISH"
        if p < m20 < m50 < m100 < m200:
            return "STRONG_BEARISH"

    if pd.notna(m20) and pd.notna(m50):
        if p > m20 > m50:
            return "BULLISH"
        if p < m20 < m50:
            return "BEARISH"
        if p > m20 and m20 < m50:
            return "RECOVERY"
        if p < m20 and m20 > m50:
            return "PULLBACK"

    if len(known) == 0:
        return "INSUFFICIENT_HISTORY"

    return "MIXED"


def rsi_state(value) -> str:
    if value is None or pd.isna(value):
        return "INSUFFICIENT_HISTORY"

    value = float(value)

    if value < 30:
        return "OVERSOLD"
    if value < 40:
        return "WEAK"
    if value < 50:
        return "RECOVERING"
    if value < 60:
        return "POSITIVE"
    if value < 70:
        return "STRONG"
    if value < 80:
        return "OVERHEATED"
    return "EXTREME"
