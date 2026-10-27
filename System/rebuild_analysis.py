"""Recompute saved scans from local OHLCV only. No quotes, broker or orders.

Previous derived files are backed up before atomic replacement. Raw prices,
accounts, positions, orders and bot processes are never changed.
"""
from datetime import datetime
from pathlib import Path
import json
import shutil
import pandas as pd

from src.paths import PROCESSED_DIR, RAW_DIR
from src.data import normalize_ohlcv
from src.analyzer import analyze_symbol, flatten_analysis
from src.valuation import CACHE_DIR, read_json, assess_valuation, attach_valuation, valuation_columns


def main():
    files = sorted({*PROCESSED_DIR.glob("*scan.csv"),
                    *(p for p in PROCESSED_DIR.glob("market_scan_*.csv") if not p.name.endswith("_errors.csv"))})
    frames = {p:pd.read_csv(p) for p in files}
    symbols = sorted({str(s) for frame in frames.values() for s in frame["symbol"]})
    analyses, errors = {}, {}
    peers = [read_json(p) for p in CACHE_DIR.glob("*.json") if p.stem != "sectors"]
    for i, symbol in enumerate(symbols, 1):
        try:
            history = normalize_ohlcv(pd.read_csv(RAW_DIR / f"{symbol}.csv"))
            result = analyze_symbol(symbol, history)
            snapshot = read_json(CACHE_DIR / f"{symbol}.json")
            result = attach_valuation(result, assess_valuation(snapshot, peers))
            analyses[symbol] = {**flatten_analysis(result), **valuation_columns(result)}
        except Exception as exc:
            errors[symbol] = f"{type(exc).__name__}: {exc}"
        if i % 50 == 0 or i == len(symbols):
            print(f"[4TF] {i}/{len(symbols)} · errors={len(errors)}", flush=True)
    backup = PROCESSED_DIR / "backups" / datetime.now().strftime("before_4tf_%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    for path, frame in frames.items():
        shutil.copy2(path, backup / path.name)
        rows = []
        for old in frame.to_dict("records"):
            symbol = str(old["symbol"])
            # Never mix a failed rebuild with old five-timeframe signals.
            if symbol not in analyses:
                rows.append({"symbol":symbol,"engine_version":"PRO_DECISION_4TF", "final_signal":"WATCH",
                             "system_action":"CHỜ_XÁC_NHẬN", "consensus_score":0, "confidence":0,
                             "data_quality":"REJECT", "reanalysis_error":errors.get(symbol)})
                continue
            row = {k:v for k,v in old.items() if not k.startswith("1q_")}
            row.update(analyses[symbol])
            news = pd.to_numeric(row.get("news_score",0), errors="coerce")
            row["news_adjusted_score"] = max(-100, min(100, row["consensus_score"] + (0 if pd.isna(news) else news)))
            row["reanalysis_error"] = None
            rows.append(row)
        output = pd.DataFrame(rows).sort_values(["consensus_score","symbol"],ascending=[False,True])
        temp = path.with_suffix(".4tf.tmp")
        output.to_csv(temp,index=False); temp.replace(path)
        meta_path = path.with_name(path.stem + "_meta.json")
        meta = read_json(meta_path)
        if meta_path.exists(): shutil.copy2(meta_path, backup/meta_path.name)
        meta.update(engine_version="PRO_DECISION_4TF",timeframes=["1D","1W","1M","1Y"],
                    reanalyzed_at=datetime.now().isoformat(), reanalysis_mode="LOCAL_OHLCV_ONLY")
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    report={"symbols":len(symbols),"analyzed":len(analyses),"errors":errors,"backup":str(backup),"files":[str(p) for p in files]}
    (PROCESSED_DIR/"reanalysis_4tf_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__ == "__main__": main()
