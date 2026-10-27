from __future__ import annotations

import pandas as pd

# Load/discover VNSTOCK_API_KEY before importing vnstock.
from .bootstrap import KEY_STATUS


MARKET_SCOPES = {
    "VN30": "VN30",
    "VN100": "VN100",
    "FAVORITES": "Yêu thích",
    "HOSE": "HOSE",
    "HNX": "HNX",
    "UPCOM": "UPCOM",
    "ALL": "Toàn thị trường",
}

EXCHANGE_ALIASES = {"HSX": "HOSE", "HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM"}


def _clean(values) -> list[str]:
    out, seen = [], set()
    for value in values:
        s = str(value).upper().strip()
        if (
            2 <= len(s) <= 5
            and s.replace("_", "").isalnum()
            and s not in {"NAN", "NONE"}
            and s not in seen
        ):
            seen.add(s)
            out.append(s)
    return out


def _extract_symbols(obj) -> list[str]:
    """Accept DataFrame, Series, Index, list/tuple/set returned by Vnstock."""
    if obj is None:
        return []

    if isinstance(obj, pd.Series):
        # Vnstock Reference.index.members() can return a Series.
        vals = obj.dropna().tolist()
        syms = _clean(vals)
        if syms:
            return syms

    if isinstance(obj, pd.Index):
        return _clean(obj.dropna().tolist())

    if isinstance(obj, (list, tuple, set)):
        return _clean(obj)

    if isinstance(obj, pd.DataFrame):
        if obj.empty:
            return []

        candidates = [
            "symbol", "ticker", "code", "stock_code",
            "organ_code", "ticker_symbol"
        ]
        lower_map = {str(c).lower().strip(): c for c in obj.columns}

        for name in candidates:
            if name in lower_map:
                syms = _clean(obj[lower_map[name]].dropna().tolist())
                if syms:
                    return syms

        # Sometimes ticker is stored in index.
        if not isinstance(obj.index, pd.RangeIndex):
            syms = _clean(obj.index.tolist())
            if syms:
                return syms

        # Last resort: inspect columns.
        for c in obj.columns:
            vals = obj[c].dropna().astype(str).str.upper().str.strip()
            if len(vals) == 0:
                continue
            ratio = vals.str.match(r"^[A-Z][A-Z0-9]{1,4}$").mean()
            if ratio >= 0.5:
                syms = _clean(vals.tolist())
                if syms:
                    return syms

    return []


def _reference_class():
    errors = []
    try:
        from vnstock import Reference
        return Reference, "vnstock.Reference"
    except Exception as exc:
        errors.append(f"vnstock.Reference: {type(exc).__name__}: {exc}")

    try:
        from vnstock_data import Reference
        return Reference, "vnstock_data.Reference"
    except Exception as exc:
        errors.append(f"vnstock_data.Reference: {type(exc).__name__}: {exc}")

    raise RuntimeError("Không import được Reference.\n" + "\n".join(errors))


def get_index_universe(group: str, min_expected: int | None = None) -> list[str]:
    group = group.upper()
    expected = min_expected if min_expected is not None else (25 if group == "VN30" else 80)
    Reference, source = _reference_class()
    ref = Reference()
    diagnostics = [f"Reference source: {source}"]

    calls = [
        (f"ref.index.members('{group}')", lambda: ref.index.members(group)),
        (f"ref.equity.list_by_group('{group}')", lambda: ref.equity.list_by_group(group)),
    ]

    for name, call in calls:
        try:
            raw = call()
            symbols = _extract_symbols(raw)
            diagnostics.append(
                f"{name}: type={type(raw).__name__}, symbols={len(symbols)}"
            )
            if len(symbols) >= expected:
                return symbols
        except Exception as exc:
            diagnostics.append(f"{name}: {type(exc).__name__}: {exc}")

    # Compatibility fallback for older free vnstock.
    try:
        from vnstock import Listing
        listing = Listing(source="VCI")
        if hasattr(listing, "symbols_by_group"):
            raw = listing.symbols_by_group(group)
            symbols = _extract_symbols(raw)
            diagnostics.append(
                f"Listing.symbols_by_group: type={type(raw).__name__}, symbols={len(symbols)}"
            )
            if len(symbols) >= expected:
                return symbols
    except Exception as exc:
        diagnostics.append(f"Listing fallback: {type(exc).__name__}: {exc}")

    raise RuntimeError(
        f"NO DATA: không lấy được {group} universe.\n"
        + "\n".join(diagnostics)
        + "\nHệ thống dừng, không gán tín hiệu giả."
    )


def get_vn100_universe(min_expected: int = 80) -> list[str]:
    return get_index_universe("VN100", min_expected)


def get_vn30_universe(min_expected: int = 25) -> list[str]:
    return get_index_universe("VN30", min_expected)


def _filter_equity_listing(raw: pd.DataFrame, scope: str = "ALL") -> pd.DataFrame:
    """Chỉ giữ cổ phiếu đang giao dịch trên HOSE/HNX/UPCOM."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["symbol", "exchange", "organ_name"])
    x = raw.copy()
    x.columns = [str(c).lower().strip() for c in x.columns]
    if not {"symbol", "exchange"}.issubset(x.columns):
        return pd.DataFrame(columns=["symbol", "exchange", "organ_name"])
    if "type" in x.columns:
        x = x[x["type"].astype(str).str.upper().eq("STOCK")]
    x["exchange"] = x["exchange"].astype(str).str.upper().map(EXCHANGE_ALIASES)
    x = x[x["exchange"].isin({"HOSE", "HNX", "UPCOM"})]
    scope = scope.upper()
    if scope in {"HOSE", "HNX", "UPCOM"}:
        x = x[x["exchange"].eq(scope)]
    x["symbol"] = x["symbol"].astype(str).str.upper().str.strip()
    x = x[x["symbol"].isin(_clean(x["symbol"]))]
    keep = [c for c in ["symbol", "exchange", "organ_name"] if c in x.columns]
    return x[keep].drop_duplicates("symbol").sort_values(["exchange", "symbol"]).reset_index(drop=True)


def get_market_listing(scope: str = "ALL") -> pd.DataFrame:
    scope = scope.upper()
    if scope == "FAVORITES":
        from .watchlist import load_watchlist
        return load_watchlist()[["symbol", "exchange"]]
    if scope in {"VN30", "VN100"}:
        return pd.DataFrame({"symbol": get_index_universe(scope), "exchange": scope})
    if scope not in MARKET_SCOPES:
        raise ValueError(f"Phạm vi không hợp lệ: {scope}")
    diagnostics = []
    try:
        from vnstock import Listing
        for source in ("VCI", "KBS"):
            try:
                raw = Listing(source=source).symbols_by_exchange()
                listing = _filter_equity_listing(raw, scope)
                diagnostics.append(f"{source}: {len(listing)} cổ phiếu")
                if not listing.empty:
                    return listing
            except Exception as exc:
                diagnostics.append(f"{source}: {type(exc).__name__}: {exc}")
    except Exception as exc:
        diagnostics.append(f"Listing import: {type(exc).__name__}: {exc}")
    raise RuntimeError("NO DATA: không lấy được danh sách toàn thị trường.\n" + "\n".join(diagnostics))


def get_market_universe(scope: str = "VN100") -> list[str]:
    return get_market_listing(scope)["symbol"].tolist()
