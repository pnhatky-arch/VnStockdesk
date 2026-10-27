from __future__ import annotations

import argparse, json
from pathlib import Path

import pandas as pd

from scan import output_paths
from src.analyzer import analyze_symbol, flatten_analysis
from src.data import cache_diagnostics, normalize_ohlcv
from src.paths import RAW_DIR


PRESERVE_PREFIXES = ("news_",)
PRESERVE_COLUMNS = {"market_scope", "exchange", "organ_name"}


def main(scope: str = "ALL") -> None:
    scope = scope.upper()
    out_path, error_path, meta_path, _ = output_paths(scope)
    old = pd.read_csv(out_path) if out_path.exists() else pd.DataFrame()
    old_by_symbol = old.set_index("symbol").to_dict("index") if not old.empty else {}
    symbols = set(old_by_symbol)
    if error_path.exists():
        errors_old = pd.read_csv(error_path)
        if "symbol" in errors_old: symbols.update(errors_old["symbol"].dropna().astype(str))
    if scope == "ALL": symbols.update(path.stem for path in RAW_DIR.glob("*.csv"))

    rows, errors = [], []
    for index, symbol in enumerate(sorted(symbols), 1):
        path = RAW_DIR / f"{symbol}.csv"
        try:
            if not path.exists(): raise RuntimeError("không có cache OHLCV")
            df = normalize_ohlcv(pd.read_csv(path))
            info = cache_diagnostics(df)
            if info["rows"] < 120:
                raise RuntimeError(f"quá ít phiên giao dịch ({info['rows']} nến; cần tối thiểu 120)")
            row = flatten_analysis(analyze_symbol(symbol, df))
            row.update({"data_start": info["start"], "data_end": info["end"], "data_rows": info["rows"],
                        "data_age_days": info["age_days"], "data_quality": info["data_quality"],
                        "recent_nonzero_volume_ratio": info["recent_nonzero_volume_ratio"],
                        "median_turnover_20d_vnd": info["median_turnover_20d_vnd"]})
            previous = old_by_symbol.get(symbol, {})
            for key, value in previous.items():
                if key.startswith(PRESERVE_PREFIXES) or key in PRESERVE_COLUMNS:
                    row[key] = value
            row.setdefault("market_scope", scope)
            rows.append(row)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
        if index % 200 == 0: print(f"[RESCORE] {index}/{len(symbols)}")

    result = pd.DataFrame(rows).sort_values(["consensus_score", "symbol"], ascending=[False, True])
    tmp = out_path.with_suffix(".tmp"); result.to_csv(tmp, index=False); tmp.replace(out_path)
    pd.DataFrame(errors, columns=["symbol", "error"]).to_csv(error_path, index=False)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.update({"rescored_at": pd.Timestamp.now().isoformat(), "engine_version": "PRO_DECISION_V3",
                 "universe": len(symbols), "analyzed": len(result), "errors": len(errors),
                 "quality_counts": result["data_quality"].value_counts().to_dict()})
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chấm lại scan bằng cache OHLCV hiện có")
    parser.add_argument("--scope", choices=["VN30", "VN100", "ALL"], default="ALL")
    args = parser.parse_args(); main(args.scope)
