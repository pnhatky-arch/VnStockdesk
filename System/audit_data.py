from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data import cache_diagnostics, normalize_ohlcv
from src.paths import RAW_DIR, PROCESSED_DIR


def main() -> dict:
    rows = []
    for path in sorted(RAW_DIR.glob("*.csv")):
        try:
            raw = pd.read_csv(path)
            original_rows = len(raw)
            original_bad = 0
            if {"open", "high", "low", "close", "volume"}.issubset(raw.columns):
                original_bad = int((
                    (raw["high"] < raw[["open", "close"]].max(axis=1))
                    | (raw["low"] > raw[["open", "close"]].min(axis=1))
                    | (raw[["open", "high", "low", "close"]] <= 0).any(axis=1)
                    | (raw["volume"] < 0)
                ).sum())
            clean = normalize_ohlcv(raw)
            info = cache_diagnostics(clean)
            rows.append({"symbol": path.stem, "original_rows": original_rows,
                         "clean_rows": len(clean), "repaired_ohlc_rows": original_bad, **info})
        except Exception as exc:
            rows.append({"symbol": path.stem, "data_quality": "REJECT", "error": str(exc)})

    audit = pd.DataFrame(rows).sort_values(["data_quality", "symbol"])
    out_csv = PROCESSED_DIR / "data_quality_audit.csv"
    audit.to_csv(out_csv, index=False)
    counts = audit["data_quality"].value_counts(dropna=False).to_dict()
    summary = {
        "generated_at": pd.Timestamp.now().isoformat(), "files": len(audit),
        "quality_counts": counts,
        "repaired_ohlc_rows": int(audit.get("repaired_ohlc_rows", pd.Series(dtype=float)).fillna(0).sum()),
        "stale_over_7_days": int((audit.get("age_days", pd.Series(dtype=float)) > 7).sum()),
        "under_120_bars": int((audit.get("clean_rows", pd.Series(dtype=float)) < 120).sum()),
    }
    (PROCESSED_DIR / "data_quality_audit_meta.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"output: {out_csv}")
    return summary


if __name__ == "__main__":
    main()
