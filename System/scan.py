from __future__ import annotations
import argparse
import json
import time
import pandas as pd

from src.universe import get_market_universe, MARKET_SCOPES
from src.data import get_history, cache_diagnostics
from src.analyzer import analyze_symbol, flatten_analysis
from src.news import fetch_company_news, score_news
from src.paths import PROCESSED_DIR
from src.valuation import CACHE_DIR, fetch_valuation, read_json, assess_valuation, attach_valuation, valuation_columns

def output_paths(scope: str):
    key = scope.lower()
    prefix = f"{key}_scan" if key in {"vn30", "vn100"} else f"market_scan_{key}"
    return (
        PROCESSED_DIR / f"{prefix}.csv",
        PROCESSED_DIR / f"{prefix}_errors.csv",
        PROCESSED_DIR / f"{prefix}_meta.json",
        PROCESSED_DIR / f".{prefix}_checkpoint.csv",
    )


def main(limit: int | None = None, refresh: bool = False, scope: str = "VN100", resume: bool = True):
    started = time.time()
    scope = scope.upper()
    if scope not in MARKET_SCOPES:
        raise ValueError(f"Phạm vi không hợp lệ: {scope}")
    out_path, error_path, meta_path, checkpoint_path = output_paths(scope)
    universe = get_market_universe(scope)
    if limit:
        universe = universe[:limit]
    print(f"[UNIVERSE] {MARKET_SCOPES[scope]}: {len(universe)} symbols")

    rows = []
    errors = []
    completed = set()
    if resume and checkpoint_path.exists() and not refresh:
        try:
            checkpoint = pd.read_csv(checkpoint_path)
            rows = checkpoint.to_dict("records")
            completed = set(checkpoint["symbol"].astype(str))
            print(f"[RESUME] {len(completed)} symbols từ checkpoint")
        except Exception:
            rows, completed = [], set()

    for i, symbol in enumerate(universe, 1):
        if symbol in completed:
            continue
        try:
            df = get_history(symbol, refresh=refresh)
            info = cache_diagnostics(df)
            result = analyze_symbol(symbol, df)
            if info['rows'] < 120:
                raise RuntimeError(
                    f'{symbol}: quá ít phiên giao dịch ({info["rows"]} nến; cần tối thiểu 120)'
                )
            row = flatten_analysis(result)
            # Toàn thị trường có thể >1.700 mã: tải tin cho các mã có tín hiệu rõ,
            # còn trang chi tiết luôn tải tin khi người dùng mở mã.
            should_fetch_news = scope in {"VN30", "VN100", "FAVORITES"} or abs(float(result["consensus_score"])) >= 25
            company_news, news_error = fetch_company_news(symbol, refresh=False) if should_fetch_news else (pd.DataFrame(), None)
            news_context = score_news(company_news, lookback_days=30)
            news_score = float(news_context["score"])
            row.update({
                "data_start": info["start"],
                "data_end": info["end"],
                "data_rows": info["rows"],
                "data_age_days": info["age_days"],
                "data_quality": info["data_quality"],
                "recent_nonzero_volume_ratio": info["recent_nonzero_volume_ratio"],
                "median_turnover_20d_vnd": info["median_turnover_20d_vnd"],
                "news_score": news_score,
                "news_sentiment": news_context["label"],
                "news_count_30d": news_context["count"],
                "news_adjusted_score": round(max(-100, min(100, result["consensus_score"] + news_score)), 1),
                "news_updated_at": pd.Timestamp.now().isoformat(),
                "news_status": news_error or ("OK" if should_fetch_news else "SKIPPED_NEUTRAL"),
                "market_scope": scope,
            })
            rows.append(row)
        except Exception as exc:
            errors.append({
                "symbol": symbol,
                "error": str(exc),
            })

        if i % 10 == 0 or i == len(universe):
            print(f"[SCAN] {i}/{len(universe)}")
            if rows:
                pd.DataFrame(rows).to_csv(checkpoint_path, index=False)

    if not rows:
        raise RuntimeError(
            "NO DATA: không có mã nào phân tích thành công. "
            "Không phát tín hiệu thị trường."
        )

    # Separate pass: all symbols get financial context, and peer comparisons
    # use the completed cache (not whichever stocks happened to scan first).
    snapshots = {}
    for i, row in enumerate(rows, 1):
        snapshots[row["symbol"]] = fetch_valuation(row["symbol"], refresh=False)
        if i % 5 == 0 or i == len(rows):
            print(f"[VALUATION] {i}/{len(rows)}", flush=True)
    peers = [read_json(p) for p in CACHE_DIR.glob("*.json") if p.stem != "sectors"]
    for row in rows:
        context = assess_valuation(snapshots[row["symbol"]], peers)
        combined = attach_valuation({**row, "data_quality": {"data_quality": row.get("data_quality")}}, context)
        row.update(valuation_columns(combined))

    out = pd.DataFrame(rows).sort_values(
        ["consensus_score", "symbol"],
        ascending=[False, True]
    )
    # Ghi atomically để dashboard không đọc trúng file đang ghi dở.
    tmp_out = out_path.with_suffix(".tmp")
    out.to_csv(tmp_out, index=False)
    tmp_out.replace(out_path)

    error_df = pd.DataFrame(errors, columns=["symbol", "error"])
    error_df.to_csv(error_path, index=False)
    duration = round(time.time() - started, 1)
    meta_path.write_text(
        json.dumps({
            "generated_at": pd.Timestamp.now().isoformat(),
            "universe": len(universe),
            "analyzed": len(out),
            "errors": len(errors),
            "duration_seconds": duration,
            "refresh": refresh,
            "news_daily_update": True,
            "valuation_daily_update": True,
            "valuation_usable": sum(row.get("valuation_status") not in {"UNAVAILABLE", "INSUFFICIENT"} for row in rows),
            "scope": scope,
            "scope_label": MARKET_SCOPES[scope],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    print()
    print("=" * 80)
    print(f"{MARKET_SCOPES[scope].upper()} SCAN COMPLETE")
    print("=" * 80)
    print(f"universe: {len(universe)}")
    print(f"analyzed: {len(out)}")
    print(f"errors: {len(errors)}")
    print(f"output: {out_path}")
    print(f"duration: {duration}s")
    print()
    print(out[
        ["symbol", "final_signal", "consensus_score",
         "1d_signal", "1w_signal", "1m_signal", "1y_signal"]
    ].head(20).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quét và chấm điểm thị trường chứng khoán Việt Nam")
    parser.add_argument("--scope", choices=list(MARKET_SCOPES), default="VN100", help="VN30, VN100, FAVORITES, HOSE, HNX, UPCOM hoặc ALL")
    parser.add_argument("--limit", type=int, help="Giới hạn số mã để kiểm thử")
    parser.add_argument("--refresh", action="store_true", help="Buộc tải lại toàn bộ lịch sử")
    parser.add_argument("--no-resume", action="store_true", help="Không tiếp tục từ checkpoint")
    args = parser.parse_args()
    main(limit=args.limit, refresh=args.refresh, scope=args.scope, resume=not args.no_resume)
