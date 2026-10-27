from __future__ import annotations

from datetime import date, timedelta
import logging
import os
import sys
import time
import threading

import pandas as pd

# Load/discover VNSTOCK_API_KEY before importing vnstock.
from .bootstrap import KEY_STATUS
from .paths import RAW_DIR
from .local_io import atomic_csv

RAW_DIR.mkdir(parents=True, exist_ok=True)

# Safe rate. User may override in .env:
# VNSTOCK_REQUEST_INTERVAL=1.20 for an account whose higher limit is confirmed.
MIN_REQUEST_INTERVAL = float(
    os.getenv("VNSTOCK_REQUEST_INTERVAL", "3.25")
)

# Cửa sổ lịch sử tương thích giới hạn Community: 8 năm trượt đến hôm nay.
def _rolling_history_start(years: int = 8) -> str:
    today = date.today()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:  # 29/02 -> 28/02
        return today.replace(year=today.year - years, day=28).isoformat()


HISTORY_START = os.getenv(
    "VN100_HISTORY_START",
    _rolling_history_start(8),
)


class _CommunityLimitNoticeFilter(logging.Filter):
    """Ẩn đúng thông báo quảng bá giới hạn đã được hệ thống tuân thủ."""
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "OHLCV data (1D) limited to 8 years" not in message and "Dữ liệu OHLCV (1D) giới hạn tối đa 8 năm" not in message


logging.getLogger("vnai.beam.patching").addFilter(_CommunityLimitNoticeFilter())

# Used only when a provider truncates a long request.
CHUNK_YEARS = int(
    os.getenv(
        "VN100_HISTORY_CHUNK_YEARS",
        "5",
    )
)

# Vnstock mặc định chỉ trả 100 dòng dù khoảng ngày dài. Yêu cầu đủ lớn để lấy
# toàn bộ giới hạn lịch sử của gói hiện tại (Community hiện tối đa khoảng 8 năm).
HISTORY_COUNT = int(os.getenv("VN100_HISTORY_COUNT", "5000"))

_last_request = 0.0
_request_lock = threading.Lock()
_console_encoding_lock = threading.Lock()


def _ensure_utf8_console() -> None:
    """Let vnstock print Vietnamese provider messages on Windows safely.

    The packaged desktop runtime can inherit ``cp1252`` stdout/stderr. vnstock
    emits Vietnamese status text while fetching OHLCV, which otherwise raises
    ``UnicodeEncodeError`` before a request reaches the provider.
    """
    with _console_encoding_lock:
        for stream in (sys.stdout, sys.stderr):
            encoding = str(getattr(stream, "encoding", "") or "").replace("-", "").lower()
            reconfigure = getattr(stream, "reconfigure", None)
            if encoding in {"utf8", "utf_8"} or not callable(reconfigure):
                continue
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (AttributeError, OSError, ValueError):
                # Streamlit can replace standard streams in some launch modes.
                # In that case, provider failures are handled normally below.
                continue


def _rate_limit():
    global _last_request
    # Lock giúp khoảng nghỉ vẫn đúng khi dashboard/scan gọi đồng thời.
    with _request_lock:
        now = time.monotonic()
        wait = MIN_REQUEST_INTERVAL - (now - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def normalize_ohlcv(
    df: pd.DataFrame | None,
) -> pd.DataFrame:
    cols = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if df is None or len(df) == 0:
        return pd.DataFrame(
            columns=cols
        )

    x = df.copy()

    x.columns = [
        str(c).lower().strip()
        for c in x.columns
    ]

    if "time" not in x.columns:
        if "date" in x.columns:
            x = x.rename(
                columns={
                    "date": "time"
                }
            )
        elif "datetime" in x.columns:
            x = x.rename(
                columns={
                    "datetime": "time"
                }
            )

    missing = [
        c
        for c in cols
        if c not in x.columns
    ]

    if missing:
        raise ValueError(
            f"OHLCV thiếu {missing}; "
            f"columns={x.columns.tolist()}"
        )

    x["time"] = pd.to_datetime(
        x["time"],
        errors="coerce",
    )

    for c in cols[1:]:
        x[c] = pd.to_numeric(
            x[c],
            errors="coerce",
        )

    x = x[cols].dropna(subset=cols)
    x = x[(x[["open", "high", "low", "close"]] > 0).all(axis=1) & (x["volume"] >= 0)]
    # Một số nguồn trả high/low không bao trùm open/close ở các mã UPCOM rất
    # kém thanh khoản. Chuẩn hóa biên nến để ATR/Wyckoff không đọc dữ liệu vô lý.
    price_envelope = x[["open", "high", "low", "close"]].copy()
    x["high"] = price_envelope.max(axis=1)
    x["low"] = price_envelope.min(axis=1)

    return (
        x
        .dropna(
            subset=cols
        )
        .sort_values("time")
        .drop_duplicates(
            "time",
            keep="last",
        )
        .reset_index(drop=True)
    )


def _call_ohlcv(
    symbol: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Try free vnstock UI first.
    Sponsor vnstock_data is only a fallback if installed.
    """

    errors = []

    try:
        _ensure_utf8_console()
        from vnstock.ui import Market

        _rate_limit()

        try:
            raw = (
                Market()
                .equity(symbol)
                .ohlcv(
                    start=start,
                    end=end,
                    interval="1D",
                    count=HISTORY_COUNT,
                )
            )
        except TypeError:
            raw = (
                Market()
                .equity(symbol)
                .ohlcv(
                    start=start,
                    end=end,
                    count=HISTORY_COUNT,
                )
            )

        return normalize_ohlcv(
            raw
        )

    except SystemExit as exc:
        errors.append(
            f"vnstock.ui SystemExit: {exc}"
        )

    except Exception as exc:
        errors.append(
            f"vnstock.ui: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        from vnstock_data import Market as FallbackMarket

    except ModuleNotFoundError as exc:
        # vnstock_data is an optional legacy fallback. Do not turn its absent
        # installation into a second, repetitive error on every retry.
        if exc.name != "vnstock_data":
            errors.append(f"vnstock_data: {type(exc).__name__}: {exc}")

    except SystemExit as exc:
        errors.append(
            f"vnstock_data SystemExit: {exc}"
        )

    except Exception as exc:
        errors.append(
            f"vnstock_data: "
            f"{type(exc).__name__}: {exc}"
        )

    else:
        try:

            _rate_limit()

            try:
                raw = (
                    FallbackMarket()
                    .equity(symbol)
                    .ohlcv(
                        start=start,
                        end=end,
                        interval="1D",
                        count=HISTORY_COUNT,
                    )
                )
            except TypeError:
                raw = (
                    FallbackMarket()
                    .equity(symbol)
                    .ohlcv(
                        start=start,
                        end=end,
                        count=HISTORY_COUNT,
                    )
                )

            return normalize_ohlcv(
                raw
            )

        except SystemExit as exc:
            errors.append(
                f"vnstock_data SystemExit: {exc}"
            )

        except Exception as exc:
            errors.append(
                f"vnstock_data: "
                f"{type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        " | ".join(errors)
    )


def _request_with_retry(
    symbol: str,
    start: str,
    end: str,
    retries: int = 3,
) -> pd.DataFrame:
    errors = []

    for attempt in range(
        1,
        retries + 1,
    ):
        try:
            return _call_ohlcv(
                symbol,
                start,
                end,
            )

        except Exception as exc:
            text = str(exc).lower()

            errors.append(
                f"attempt {attempt}: "
                f"{type(exc).__name__}: {exc}"
            )

            if (
                "rate limit" in text
                or "20/20" in text
                or "60/60" in text
                or "429" in text
                or "requests/phút" in text
            ):
                time.sleep(65)
            else:
                time.sleep(
                    min(
                        3 * attempt,
                        10,
                    )
                )

    raise RuntimeError(
        f"{symbol} {start}->{end}: "
        + " | ".join(errors)
    )


def _date_chunks(
    start: str,
    end: str,
    years: int = CHUNK_YEARS,
):
    current = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    while current <= end_ts:
        chunk_end = min(
            current
            + pd.DateOffset(
                years=years
            )
            - pd.Timedelta(days=1),
            end_ts,
        )

        yield (
            current.date().isoformat(),
            chunk_end.date().isoformat(),
        )

        current = (
            chunk_end
            + pd.Timedelta(days=1)
        )


def _needs_long_history_recovery(
    df: pd.DataFrame,
    requested_start: str,
) -> bool:
    """
    Detect common provider truncation.

    If a request asked for history back to 2000 but the returned dataset
    contains only a short recent window, attempt chunked recovery.

    New IPOs can legitimately have short history; chunked recovery is safe:
    older chunks simply return empty.
    """
    if df.empty:
        return True

    span_days = (
        df["time"].max()
        - df["time"].min()
    ).days

    # < ~6 years is too short for the requested long-history analytics
    # and strongly suggests either a recent IPO or provider truncation.
    # We still try chunks so recent IPOs are handled correctly.
    return span_days < 365 * 6


def fetch_history_long(
    symbol: str,
    start: str = HISTORY_START,
    end: str | None = None,
) -> pd.DataFrame:
    if end is None:
        end = date.today().isoformat()

    # First try one request. If provider really supports the full interval,
    # this is the fastest and cheapest path.
    direct = pd.DataFrame()

    try:
        direct = _request_with_retry(
            symbol=symbol,
            start=start,
            end=end,
            retries=2,
        )
    except Exception:
        direct = pd.DataFrame()

    if (
        not direct.empty
        and not _needs_long_history_recovery(
            direct,
            start,
        )
    ):
        return direct

    # Recover full history in chunks.
    frames = []

    for chunk_start, chunk_end in _date_chunks(
        start,
        end,
    ):
        try:
            part = _request_with_retry(
                symbol=symbol,
                start=chunk_start,
                end=chunk_end,
                retries=2,
            )

            if not part.empty:
                frames.append(
                    part
                )

        except Exception:
            # Do not destroy the whole symbol because an old empty period
            # failed. Continue with the remaining chunks.
            continue

    if frames:
        merged = normalize_ohlcv(
            pd.concat(
                frames,
                ignore_index=True,
            )
        )

        if not merged.empty:
            return merged

    if not direct.empty:
        return direct

    raise RuntimeError(
        f"{symbol}: NO DATA"
    )


def cache_path(
    symbol: str,
) -> Path:
    return (
        RAW_DIR
        / f"{symbol.upper()}.csv"
    )


def cache_diagnostics(
    df: pd.DataFrame,
    reference_date=None,
) -> dict:
    if df is None or df.empty:
        return {
            "rows": 0,
            "start": None,
            "end": None,
            "years": 0.0,
            "age_days": None,
            "max_gap_days": None,
        }

    start = pd.to_datetime(
        df["time"].min()
    )
    end = pd.to_datetime(
        df["time"].max()
    )

    years = (
        (end - start).days
        / 365.25
    )
    gaps = pd.to_datetime(df["time"]).sort_values().diff().dt.days.dropna()
    max_gap_days = int(gaps.max()) if not gaps.empty else 0

    recent = df.sort_values("time").tail(20)
    turnover = recent["close"] * recent["volume"] * 1000
    nonzero_ratio = float((recent["volume"] > 0).mean()) if len(recent) else 0.0
    median_turnover = float(turnover.median()) if len(turnover) else 0.0
    reference = pd.Timestamp(reference_date).normalize() if reference_date is not None else pd.Timestamp.now().normalize()
    age_days = max(0, (reference - end.normalize()).days)
    if len(df) < 120 or age_days > 30:
        quality = "REJECT"
    elif age_days > 7 or nonzero_ratio < 0.8 or median_turnover < 100_000_000:
        quality = "WATCH"
    else:
        quality = "GOOD"

    return {
        "rows": len(df),
        "start": start,
        "end": end,
        "years": round(
            years,
            2,
        ),
        "age_days": age_days,
        "max_gap_days": max_gap_days,
        "recent_nonzero_volume_ratio": round(nonzero_ratio, 3),
        "median_turnover_20d_vnd": round(median_turnover),
        "data_quality": quality,
    }


def _cache_is_obviously_short(
    df: pd.DataFrame,
) -> bool:
    """
    Old versions accepted a cache with only ~30 rows.
    That breaks higher timeframes.

    A cache below 250 daily bars OR below ~1 year is automatically rebuilt.
    Longer-but-young IPO histories are kept; their unavailable long MAs are
    reported honestly by the dashboard.
    """
    if df.empty:
        return True

    info = cache_diagnostics(
        df
    )

    return (
        info["rows"] < 250
        or info["years"] < 0.95
        or info["max_gap_days"] > 14
    )


def get_history(
    symbol: str,
    refresh: bool = False,
) -> pd.DataFrame:
    p = cache_path(
        symbol
    )

    if (
        p.exists()
        and not refresh
    ):
        cached = normalize_ohlcv(
            pd.read_csv(p)
        )
        cached = cached[cached["time"] >= pd.Timestamp(HISTORY_START)].reset_index(drop=True)

        if not _cache_is_obviously_short(
            cached
        ):
            # Cache trong vòng 4 ngày lịch (bao phủ cuối tuần/ngày nghỉ) là đủ mới.
            info = cache_diagnostics(cached)
            if info["age_days"] <= 4:
                return cached

            # Chỉ tải phần mới thay vì dựng lại toàn bộ lịch sử.
            start = (pd.Timestamp(info["end"]) - pd.Timedelta(days=7)).date().isoformat()
            try:
                recent = _request_with_retry(
                    symbol=symbol,
                    start=start,
                    end=date.today().isoformat(),
                    retries=2,
                )
                if not recent.empty:
                    merged = normalize_ohlcv(pd.concat([cached, recent], ignore_index=True))
                    merged = merged[merged["time"] >= pd.Timestamp(HISTORY_START)].reset_index(drop=True)
                    atomic_csv(p, merged)
                    return merged
            except Exception:
                # Cache cũ vẫn có giá trị nghiên cứu; scanner sẽ công bố tuổi dữ liệu.
                return cached
            return cached

    df = fetch_history_long(
        symbol=symbol,
    )
    df = df[df["time"] >= pd.Timestamp(HISTORY_START)].reset_index(drop=True)

    atomic_csv(p, df)

    return df


def refresh_history_incremental(symbol: str, lookback_days: int = 14) -> pd.DataFrame:
    """Force a small recent-window refresh and merge it into the 8-year cache."""
    symbol = str(symbol).upper().strip()
    p = cache_path(symbol)
    cached = normalize_ohlcv(pd.read_csv(p)) if p.exists() else normalize_ohlcv(None)
    start = (date.today() - timedelta(days=max(7, int(lookback_days)))).isoformat()
    if not cached.empty:
        start = min(start, (pd.Timestamp(cached["time"].max()) - pd.Timedelta(days=7)).date().isoformat())
    recent = _request_with_retry(symbol=symbol, start=start, end=date.today().isoformat(), retries=2)
    if recent.empty:
        if cached.empty:
            raise RuntimeError(f"{symbol}: nguồn dữ liệu không trả OHLCV mới và chưa có cache.")
        return cached
    merged = normalize_ohlcv(pd.concat([cached, recent], ignore_index=True))
    merged = merged[merged["time"] >= pd.Timestamp(HISTORY_START)].reset_index(drop=True)
    atomic_csv(p, merged)
    return merged


def rebuild_short_cache(
    symbol: str,
) -> pd.DataFrame:
    """
    Force full-history rebuild for one symbol.
    """
    p = cache_path(
        symbol
    )

    if p.exists():
        p.unlink()

    return get_history(
        symbol,
        refresh=True,
    )
