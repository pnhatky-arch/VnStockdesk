from __future__ import annotations

import json

import pandas as pd

from .paths import PRIVATE_DIR


WATCHLIST_PATH = PRIVATE_DIR / "user_watchlist.json"


def load_watchlist() -> pd.DataFrame:
    columns = ["symbol", "exchange", "added_at"]
    if not WATCHLIST_PATH.exists():
        return pd.DataFrame(columns=columns)
    try:
        payload = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        rows = payload.get("symbols", []) if isinstance(payload, dict) else []
        out = pd.DataFrame(rows)
        for column in columns:
            if column not in out.columns:
                out[column] = None
        out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
        out["exchange"] = out["exchange"].fillna("HOSE").astype(str).str.upper()
        return out[columns].drop_duplicates("symbol", keep="last").sort_values("symbol").reset_index(drop=True)
    except (OSError, ValueError, json.JSONDecodeError):
        return pd.DataFrame(columns=columns)


def save_watchlist(watchlist: pd.DataFrame) -> None:
    clean = watchlist.copy()
    if clean.empty:
        rows = []
    else:
        clean["symbol"] = clean["symbol"].astype(str).str.upper().str.strip()
        clean = clean.drop_duplicates("symbol", keep="last").sort_values("symbol")
        rows = clean[["symbol", "exchange", "added_at"]].to_dict("records")
    temp = WATCHLIST_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps({"symbols": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(WATCHLIST_PATH)


def add_favorite(symbol: str, exchange: str) -> pd.DataFrame:
    watchlist = load_watchlist()
    symbol = symbol.upper().strip()
    watchlist = watchlist[watchlist["symbol"] != symbol]
    row = pd.DataFrame([{
        "symbol": symbol,
        "exchange": exchange.upper().strip() or "HOSE",
        "added_at": pd.Timestamp.now().isoformat(),
    }])
    watchlist = pd.concat([watchlist, row], ignore_index=True)
    save_watchlist(watchlist)
    return load_watchlist()


def remove_favorite(symbol: str) -> pd.DataFrame:
    watchlist = load_watchlist()
    watchlist = watchlist[watchlist["symbol"] != symbol.upper().strip()]
    save_watchlist(watchlist)
    return load_watchlist()


def is_favorite(symbol: str) -> bool:
    return symbol.upper().strip() in set(load_watchlist()["symbol"])
