from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import normalize_ohlcv, cache_diagnostics
from src.news import normalize_news, score_news
from src.universe import _extract_symbols, _filter_equity_listing
from src.analyzer import analyze_symbol, flatten_analysis
from src.timeframes import resample_ohlcv, TIMEFRAME_CONFIG
from src.paper_broker import PaperBroker
from src.trading_config import TradingConfig
from src.trading_engine import position_size
from src.broker_adapter import LockedLiveBroker
from src.validation import walk_forward_validation


def make_sample(rows=6500):
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2001-01-02", periods=rows)

    ret = rng.normal(0.0003, 0.015, rows)
    close = 20 * np.exp(np.cumsum(ret))
    open_ = close * (1 + rng.normal(0, 0.004, rows))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.008, 0.004, rows)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.008, 0.004, rows)))
    volume = rng.integers(100_000, 8_000_000, rows)

    return pd.DataFrame({
        "time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def main():
    listing = pd.DataFrame({
        "symbol": ["AAA", "BBB", "CCC", "CW01", "OLD"],
        "exchange": ["HSX", "HNX", "UPCOM", "HSX", "DELISTED"],
        "type": ["STOCK", "STOCK", "STOCK", "CW", "STOCK"],
    })
    market = _filter_equity_listing(listing, "ALL")
    assert market.set_index("symbol")["exchange"].to_dict() == {
        "AAA": "HOSE", "BBB": "HNX", "CCC": "UPCOM"
    }
    assert _filter_equity_listing(listing, "HOSE")["symbol"].tolist() == ["AAA"]

    assert _extract_symbols(
        pd.Series(["FPT", "VCB", "HPG"])
    ) == ["FPT", "VCB", "HPG"]

    assert _extract_symbols(
        pd.DataFrame({
            "symbol": ["FPT", "VCB", "HPG"]
        })
    ) == ["FPT", "VCB", "HPG"]

    df = normalize_ohlcv(
        make_sample()
    )
    malformed = pd.DataFrame({"time": ["2026-01-01"], "open": [10], "high": [9],
                              "low": [11], "close": [12], "volume": [100]})
    repaired = normalize_ohlcv(malformed)
    assert repaired.iloc[0]["high"] == 12 and repaired.iloc[0]["low"] == 9

    assert TIMEFRAME_CONFIG["1D"]["period"] == "1 ngày"
    assert TIMEFRAME_CONFIG["1W"]["period"] == "1 tuần"
    assert TIMEFRAME_CONFIG["1M"]["period"] == "1 tháng"
    assert "1Q" not in TIMEFRAME_CONFIG
    assert TIMEFRAME_CONFIG["1Y"]["period"] == "1 năm"
    assert len(resample_ohlcv(df, "1D")) == len(df)
    try:
        resample_ohlcv(df, "1Q")
        raise AssertionError("Removed timeframe must be rejected")
    except ValueError:
        pass
    assert set(pd.to_datetime(resample_ohlcv(df, "1Y")["period_end"]).dt.month) == {12}
    assert resample_ohlcv(df, "1Y")["time"].max() <= df["time"].max()

    result = analyze_symbol(
        "TEST",
        df,
    )

    assert -100 <= result["consensus_score"] <= 100
    assert 0 <= result["confidence"] <= 100
    assert 0 <= result["timeframe_alignment"] <= 100
    assert result["decision_grade"] in {"A", "B", "C", "D"}
    assert result["market_regime"] in {"XU HƯỚNG TĂNG", "XU HƯỚNG GIẢM", "ĐI NGANG / CHUYỂN PHA"}
    assert result["conflict_level"] in {"THẤP", "TRUNG BÌNH", "CAO"}
    assert 0 <= result["evidence_coverage"] <= 100
    assert 0 <= result["evidence_quality"] <= 100
    assert isinstance(result["decision_drivers"], list)
    assert result["system_action"] in {
        "MUA_CÓ_XÁC_NHẬN", "THEO_DÕI_MUA", "NẮM_GIỮ",
        "CHỜ_XÁC_NHẬN", "GIẢM_TỶ_TRỌNG", "BÁN_CÓ_XÁC_NHẬN",
    }
    assert -100 <= result["strategic_score"] <= 100
    assert -100 <= result["tactical_score"] <= 100
    assert isinstance(result["risk_flags"], list)
    for warning in result["risk_flags"]:
        if warning.startswith("Xung đột đa khung"):
            assert "nghiêng tăng:" in warning
            assert "nghiêng giảm:" in warning

    raw_news = pd.DataFrame({
        "title": ["TEST lợi nhuận tăng và vượt kế hoạch", "TEST bị xử phạt vi phạm"],
        "publish_time": [pd.Timestamp.now(), pd.Timestamp.now() - pd.Timedelta(days=2)],
        "url": ["/positive", "/negative"],
        "head": ["Kết quả kinh doanh tích cực", "Rủi ro pháp lý"],
    })
    normalized_news = normalize_news(raw_news, "KBS", "TEST")
    news_context = score_news(normalized_news)
    assert len(normalized_news) == 2
    assert -10 <= news_context["score"] <= 10
    assert news_context["count"] == 2
    assert {item["event_type"] for item in news_context["items"]} >= {
        "KẾT QUẢ KINH DOANH", "PHÁP LÝ/QUẢN TRỊ"
    }
    plan = result["strategy_plan"]
    assert plan["status"] in {
        "READY", "WAIT_TRIGGER", "MANAGE_POSITION",
        "PROTECT_CAPITAL", "NO_TRADE", "NO_PLAN",
    }
    assert "strategy" in plan and "note" in plan

    assert set(result["timeframes"]) == {
        "1D", "1W", "1M", "1Y"
    }

    flat = flatten_analysis(result)
    for field in ("decision_grade", "market_regime", "conflict_level", "decision_drivers", "engine_version"):
        assert field in flat

    for tf in ("1d", "1w", "1m", "1y"):
        assert f"{tf}_signal" in flat
        assert f"{tf}_wyckoff_phase" in flat
        assert f"{tf}_ma_regime" in flat
        assert f"{tf}_rsi14" in flat
        assert f"{tf}_signal_score" in flat
        assert f"{tf}_confidence" in flat
        assert f"{tf}_atr_pct" in flat

    for tf_result in result["timeframes"].values():
        if tf_result.get("status") == "OK":
            assert {
                "ma", "wyckoff", "rsi", "momentum", "volume", "risk"
            }.issubset(tf_result["component_scores"])

    info = cache_diagnostics(df)
    assert info["rows"] == len(df)
    assert info["age_days"] >= 0
    assert info["max_gap_days"] <= 4
    assert info["data_quality"] in {"GOOD", "WATCH", "REJECT"}
    assert info["median_turnover_20d_vnd"] >= 0

    validation = walk_forward_validation(df.tail(900).reset_index(drop=True), horizon=20, step=100, min_history=260)
    assert validation["status"] == "OK"
    assert 0 <= validation["coverage"] <= 100
    assert validation["hit_rate"] is None or 0 <= validation["hit_rate"] <= 100

    with TemporaryDirectory() as tmp:
        cfg = TradingConfig(initial_cash_vnd=100_000_000, lot_size=100)
        broker = PaperBroker(Path(tmp) / "portfolio.json", cfg)
        assert broker.normalize_quantity(249) == 200
        qty = position_size(100_000_000, 100_000_000, 50, 47, cfg)
        assert qty > 0 and qty % 100 == 0
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        buy_time = datetime(2026, 9, 7, 10, 0, tzinfo=tz)
        sell_time = datetime(2026, 9, 9, 13, 0, tzinfo=tz)
        buy = broker.buy("FPT", 200, 50, 47, 58, "TEST", now=buy_time)
        assert buy["status"] == "FILLED" and broker.state["positions"]["FPT"]["quantity"] == 200
        sell = broker.sell("FPT", 100, 55, "TEST", now=sell_time)
        assert sell["side"] == "SELL" and broker.state["positions"]["FPT"]["quantity"] == 100
        try:
            LockedLiveBroker().submit_order("FPT", "BUY", 100, 50)
            raise AssertionError("Live broker must remain locked")
        except RuntimeError as exc:
            assert "LIVE đang khóa" in str(exc)

    print("[PASS] Universe parser")
    print("[PASS] OHLCV normalization")
    print("[PASS] 1D/1W/1M/1Y resample")
    print("[PASS] Chu kỳ nến: ngày/tuần/tháng/năm")
    print("[PASS] Wyckoff + MA + RSI analysis")
    print("[PASS] Scanner flatten output")
    print("[PASS] Signal score + confidence + risk metrics")
    print("[PASS] Automated multi-timeframe decision engine")
    print("[PASS] Automated strategy + entry/stop/target plan")
    print("[PASS] Paper broker + risk sizing + locked live gateway")
    print("[PASS] Walk-forward signal validation")
    print("[PASS] Offline pipeline")


if __name__ == "__main__":
    main()
