from __future__ import annotations
import pandas as pd


TIMEFRAME_CONFIG = {
    "1D": {"rule": None, "period": "1 ngày", "description": "Mỗi cây nến đại diện cho 1 ngày giao dịch"},
    "1W": {"rule": "W-FRI", "period": "1 tuần", "description": "Mỗi cây nến đại diện cho 1 tuần"},
    "1M": {"rule": "ME", "period": "1 tháng", "description": "Mỗi cây nến đại diện cho 1 tháng"},
    "1Y": {"rule": "YE", "period": "1 năm", "description": "Mỗi cây nến đại diện cho 1 năm"},
}

TIMEFRAME_ORDER = list(TIMEFRAME_CONFIG)
RULES = {key: value["rule"] for key, value in TIMEFRAME_CONFIG.items()}


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    x = df.copy()
    x["time"] = pd.to_datetime(x["time"])
    x = x.sort_values("time", kind="stable").drop_duplicates("time", keep="last")
    if timeframe == "1D":
        return x.reset_index(drop=True)
    rule = TIMEFRAME_CONFIG[timeframe]["rule"]
    x["source_time"] = x["time"]
    x = x.set_index("time")

    out = (
        x.resample(rule)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            source_time=("source_time", "last"),
            source_bars=("close", "count"),
        )
        .dropna()
        .reset_index()
    )
    # Calendar end is metadata only. Never timestamp an unfinished yearly bar
    # in the future, or fabricate rows for periods absent from source data.
    out = out.rename(columns={"time": "period_end", "source_time": "time"})
    return out
