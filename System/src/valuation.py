"""Auditable, non-executing equity valuation context (no trading imports).

Ratios are provider report snapshots, NOT live recomputations. Comparisons only
use matching sources/periods for peers and past periods for own history.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import pandas as pd

from .paths import DATA_DIR, PROJECT_ROOT

CACHE_DIR = DATA_DIR / "valuation"
VERSION = 2
METRICS = ("pe", "pb", "roe", "debt_equity", "profit_growth", "eps", "bvps")
ALIASES = {
    "pe": ("pe", "pe_ratio", "P/E", "price_to_earnings", "price_to_earning", "priceToEarning"),
    "pb": ("pb", "pb_ratio", "P/B", "price_to_book", "priceToBook"),
    "roe": ("roe", "ROE (%)", "return_on_equity"),
    "debt_equity": ("debt_equity", "debt_to_equity", "Debt/Equity", "debtPerEquity"),
    "profit_growth": ("net_profit_growth", "profit_growth", "profit_growth_yoy"),
    "eps": ("eps", "trailing_eps", "earnings_per_share"),
    "bvps": ("bvps", "book_value_per_share", "book_value_per_share_bvps"),
}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def safe_symbol(symbol):
    symbol = str(symbol).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", symbol):
        raise ValueError("Invalid equity symbol")
    return symbol


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def period_end(value):
    value = str(value).replace("-Năm", "").strip()
    match = re.fullmatch(r"(20\d{2})[- ]?Q([1-4])", value, re.I)
    if match:
        return pd.Period(f"{match[1]}Q{match[2]}", freq="Q").end_time.normalize()
    match = re.fullmatch(r"Q([1-4])[- /](20\d{2})", value, re.I)
    if match:
        return pd.Period(f"{match[2]}Q{match[1]}", freq="Q").end_time.normalize()
    if re.fullmatch(r"20\d{2}", value):
        return pd.Timestamp(f"{value}-12-31")
    return None


def normalize_ratios(raw: pd.DataFrame) -> list[dict]:
    """Accept current item/period matrix and legacy row-oriented schemas.

    No fillna(0): missing, zero and negative values have different meanings.
    Values are retained in the provider's units; only verified aliases map.
    """
    if raw is None or raw.empty:
        return []
    raw = raw.copy()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [next((str(p) for p in reversed(c) if str(p)), "") for c in raw.columns]
    periods = [c for c in raw.columns if period_end(c) is not None]
    if periods and any(c in raw.columns for c in ("item_id", "item_en", "item")):
        records = []
        for p in periods:
            row = {"period": str(p)}
            for metric, aliases in ALIASES.items():
                match_keys = {_key(a) for a in aliases}
                matches = raw.apply(lambda r: any(_key(r.get(c)) in match_keys for c in ("item_id", "item_en", "item")), axis=1)
                vals = [number(v) for v in raw.loc[matches, p]]
                row[metric] = next((v for v in vals if v is not None), None)
                if metric == "debt_equity" and matches.any() and str(raw.loc[matches].iloc[0].get("unit")) == "%" and row[metric] is not None:
                    row[metric] /= 100
            # KBS growth rows can have misleading English item IDs. Require
            # the explicit Vietnamese growth label AND percentage unit.
            growth = raw.apply(lambda r: str(r.get("item", "")).lower().startswith("tăng trưởng lợi nhuận sau thuế") and r.get("unit") == "%", axis=1)
            if growth.any():
                row["profit_growth"] = number(raw.loc[growth, p].iloc[0])
            records.append(row)
    else:
        records = []
        for _, raw_row in raw.iterrows():
            r = {_key(k): v for k, v in raw_row.items()}
            p = r.get("period", r.get("reportperiod"))
            if period_end(p) is None:
                y, q = number(r.get("year", r.get("yearreport"))), number(r.get("quarter", r.get("lengthreport")))
                p = f"{int(y)}-Q{int(q)}" if y and q in (1, 2, 3, 4) else str(int(y)) if y else None
            row = {"period": p}
            for metric, aliases in ALIASES.items():
                row[metric] = next((number(r[_key(a)]) for a in aliases if _key(a) in r and number(r[_key(a)]) is not None), None)
            records.append(row)
    unique = {}
    for r in records:
        end = period_end(r["period"])
        if end is not None and any(r.get(k) is not None for k in METRICS):
            r["period_end"] = end.date().isoformat()
            unique[r["period_end"]] = r
    return sorted(unique.values(), key=lambda r: r["period_end"])[-8:]


def _now(now=None):
    t = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _age(value, now):
    try:
        return (now - _now(value)).total_seconds() if value else math.inf
    except (ValueError, TypeError):
        return math.inf


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".valuation-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _provider(symbol):
    """Hard timeout isolates provider delays and SystemExit from the dashboard."""
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = str(CACHE_DIR / "runtime")
    process = subprocess.run(
        [sys.executable, "-m", "src.valuation_provider", symbol], cwd=PROJECT_ROOT,
        capture_output=True, text=True, timeout=75, env=env,
    )
    # Ignore vendor banners; do not persist stderr/credentials in error messages.
    for line in reversed(process.stdout.splitlines()):
        if line.startswith("VALUATION_JSON="):
            return json.loads(line.partition("=")[2])
    raise RuntimeError("Provider unavailable")


def fetch_valuation(symbol, refresh=False, *, cache_dir=None, now=None, provider=None):
    symbol = safe_symbol(symbol)
    root = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    path = root / f"{symbol}.json"
    now = _now(now)
    cached = read_json(path)
    if cached.get("version") != VERSION or cached.get("symbol") != symbol:
        cached = {}
    age = _age(cached.get("fetched_at"), now)
    retry_age = _age(cached.get("attempted_at"), now)
    history_current = cached.get("history_loader_version") == 2
    if not refresh and ((history_current and 0 <= age < 86400 and not cached.get("fetch_error")) or 0 <= retry_age < 900 and (history_current or cached.get("fetch_error"))):
        return cached
    try:
        incoming = (provider or _provider)(symbol)
        rows = incoming.get("history", [])
        if incoming.get("symbol") != symbol or not rows:
            raise ValueError("No financial data")
        # A fallback source must not silently replace a newer existing report.
        if cached.get("history") and max(r["period_end"] for r in rows) < max(r["period_end"] for r in cached["history"]):
            raise ValueError("Older report returned")
        result = {**incoming, "version": VERSION, "fetched_at": now.isoformat(), "attempted_at": now.isoformat(), "fetch_error": None}
    except (Exception, SystemExit):
        result = {**cached, "version": VERSION, "symbol": symbol,
                  "attempted_at": now.isoformat(), "fetch_error": "FETCH_FAILED"}
    try:
        atomic_json(path, result)
    except OSError:
        result = {**result, "cache_error": True}
    return result


def assess_valuation(snapshot, peers=(), *, now=None):
    now = _now(now)
    peers = list(peers)
    warnings = list(snapshot.get("provider_warnings", []))
    def valid_rows(data):
        valid = []
        rows = data.get("history") or []
        if not isinstance(rows, list):
            return valid
        for row in rows:
            if not isinstance(row, dict):
                continue
            end = period_end(row.get("period"))
            if end is not None and end.date().isoformat() == row.get("period_end"):
                valid.append({**row, **{k: number(row.get(k)) for k in METRICS}})
        return sorted(valid, key=lambda r: r["period_end"])

    history = valid_rows(snapshot)
    if len(history) != len(snapshot.get("history") or []):
        warnings.append("AMBIGUOUS_PERIODS")
    current = history[-1] if history else {}
    age_days = _age(current.get("period_end"), now) / 86400
    cache_age = _age(snapshot.get("fetched_at"), now) / 86400
    if not history: warnings.append("NO_DATA")
    elif age_days < 0: warnings.append("FUTURE_REPORT")
    elif age_days > 200: warnings.append("STALE_REPORT")
    if snapshot.get("fetch_error"): warnings.append("FETCH_FAILED")
    if cache_age > 2 or cache_age < 0: warnings.append("STALE_CACHE")
    if snapshot.get("cache_error"): warnings.append("CACHE_WRITE_FAILED")
    usable = bool(history) and 0 <= age_days <= 200 and 0 <= cache_age <= 2 and not snapshot.get("fetch_error") and "AMBIGUOUS_PERIODS" not in warnings
    pe, pb = number(current.get("pe")), number(current.get("pb"))
    eps, bvps = number(current.get("eps")), number(current.get("bvps"))
    if pe is not None and pe <= 0 or eps is not None and eps <= 0: warnings.append("NONPOSITIVE_EARNINGS")
    if pb is not None and pb <= 0 or bvps is not None and bvps <= 0: warnings.append("NONPOSITIVE_EQUITY")
    if pe is None or pb is None: warnings.append("MISSING_RATIOS")
    roe, growth = number(current.get("roe")), number(current.get("profit_growth"))
    if roe is not None and roe <= 0: warnings.append("WEAK_ROE")
    if growth is not None and growth < 0: warnings.append("PROFIT_DECLINE")
    for metric, warning in (("roe", "MISSING_ROE"), ("profit_growth", "MISSING_GROWTH"), ("debt_equity", "MISSING_DEBT_EQUITY")):
        if current.get(metric) is None:
            warnings.append(warning)
    # No universal debt threshold: banks and industrial companies differ.
    sector = snapshot.get("sector")
    comparisons, votes = [], []
    for metric in ("pe", "pb"):
        value = number(current.get(metric))
        invalid = "NONPOSITIVE_EARNINGS" if metric == "pe" else "NONPOSITIVE_EQUITY"
        historical = [r[metric] for r in history[:-1] if number(r.get(metric)) is not None and r[metric] > 0
                      and (number(r.get("eps" if metric == "pe" else "bvps")) is None or r["eps" if metric == "pe" else "bvps"] > 0)
                      and len(str(r.get("period"))) == len(str(current.get("period")))]
        matched = {}
        for peer in peers:
            if not sector or peer.get("symbol") == snapshot.get("symbol") or peer.get("sector") != sector or peer.get("source") != snapshot.get("source"):
                continue
            if peer.get("fetch_error") or peer.get("provider_warnings") or peer.get("version") != VERSION or not 0 <= _age(peer.get("fetched_at"), now) <= 2 * 86400:
                continue
            rows = valid_rows(peer)
            if len(rows) != len(peer.get("history") or []):
                continue
            row = max(rows, key=lambda r: r["period_end"]) if rows else {}
            v = number(row.get(metric))
            denominator = number(row.get("eps" if metric == "pe" else "bvps"))
            if row.get("period") == current.get("period") and v is not None and v > 0 and (denominator is None or denominator > 0):
                matched[peer["symbol"]] = v
        for basis, values in (("HISTORY", historical), ("PEERS", list(matched.values()))):
            benchmark = median(values) if len(values) >= 3 else None
            deviation = (value / benchmark - 1) * 100 if value is not None and value > 0 and benchmark and invalid not in warnings else None
            comparisons.append({"metric": metric.upper(), "basis": basis, "value": value,
                                "median": benchmark, "count": len(values), "deviation_pct": deviation,
                                "symbols": sorted(matched) if basis == "PEERS" else []})
            if usable and deviation is not None:
                votes.append(1 if deviation <= -20 else -1 if deviation >= 20 else 0)
    if not sector: warnings.append("NO_SECTOR")
    if not any(c["basis"] == "PEERS" and c["median"] is not None for c in comparisons): warnings.append("FEW_PEERS")
    if not any(c["basis"] == "HISTORY" and c["median"] is not None for c in comparisons): warnings.append("SHORT_HISTORY")
    if not usable: status = "UNAVAILABLE"
    elif any(w in warnings for w in ("NONPOSITIVE_EARNINGS", "NONPOSITIVE_EQUITY")): status = "CAUTION"
    elif not votes or pe is None or pb is None: status = "INSUFFICIENT"
    elif 1 in votes and -1 in votes: status = "MIXED"
    elif sum(votes) > 0: status = "LOWER_RELATIVE"
    elif sum(votes) < 0: status = "HIGHER_RELATIVE"
    else: status = "NEAR_REFERENCE"
    return {"symbol": snapshot.get("symbol"), "status": status, "source": snapshot.get("source"),
            "fetched_at": snapshot.get("fetched_at"), "period": current.get("period"),
            "report_age_days": round(age_days) if math.isfinite(age_days) else None,
            "sector": sector, "metrics": {k: current.get(k) for k in METRICS},
            "history": history, "comparisons": comparisons, "warnings": warnings,
            "basis": "PROVIDER_REPORT_SNAPSHOT", "trade_enabled": False}


def load_valuation(symbol, refresh=False, *, cache_dir=None, now=None, provider=None, auto_peers=True):
    symbol = safe_symbol(symbol)
    root = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    snapshot = fetch_valuation(symbol, refresh, cache_dir=root, now=now, provider=provider)
    peers = [read_json(p) for p in root.glob("*.json") if p.stem != "sectors"]
    assessment = assess_valuation(snapshot, peers, now=now)
    # A small deterministic sector sample, not a whole-market fetch. Only
    # missing compatible samples are loaded; never recursively load their peers.
    attempted = []
    sector_data = read_json(root / "sectors.json")
    current_time = _now(now)
    if auto_peers and assessment["status"] != "UNAVAILABLE" and "FEW_PEERS" in assessment["warnings"] and 0 <= _age(sector_data.get("fetched_at"), current_time) < 7 * 86400:
        members = sector_data.get("symbols", {})
        candidates = sorted(s for s, sector in members.items() if sector == snapshot.get("sector") and s != symbol and re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", s))
        # Try cached candidates first, but don't let a recent failed fetch or
        # incompatible report consume the bounded network allowance on every rerun.
        existing = {p.get("symbol"): p for p in peers}
        start = time.monotonic()
        for candidate in candidates:
            old = existing.get(candidate, {})
            if old.get("history_loader_version") == 2 and 0 <= _age(old.get("fetched_at"), current_time) < 86400 and not old.get("fetch_error"):
                continue
            if old.get("fetch_error") and 0 <= _age(old.get("attempted_at"), current_time) < 900:
                continue
            if len(attempted) >= 5 or time.monotonic() - start >= 90:
                break
            peer = fetch_valuation(candidate, cache_dir=root, now=now, provider=provider)
            peers = [p for p in peers if p.get("symbol") != candidate] + [peer]
            attempted.append(candidate)
            assessment = assess_valuation(snapshot, peers, now=now)
            if "FEW_PEERS" not in assessment["warnings"]:
                break
    return {**assessment, "peer_fetch_attempted": attempted}


def attach_valuation(result, valuation):
    """Add context, never overwrite scores, confidence, strategy or bot actions."""
    status = valuation.get("status")
    score = number(result.get("consensus_score")) or 0
    quality = result.get("data_quality", {}).get("data_quality")
    if status == "UNAVAILABLE":
        conclusion = "INCOMPLETE"
    elif status in ("CAUTION", "HIGHER_RELATIVE") or quality != "GOOD" or any(w in valuation.get("warnings", []) for w in ("WEAK_ROE", "PROFIT_DECLINE")):
        conclusion = "RISK_REVIEW"
    elif status == "INSUFFICIENT":
        conclusion = "INCOMPLETE"
    elif status == "LOWER_RELATIVE" and score <= -25:
        conclusion = "VALUE_TREND_CONFLICT"
    elif status == "LOWER_RELATIVE" and score >= 25:
        conclusion = "WATCH_CONFIRMATION"
    else:
        conclusion = "WAIT_CONFIRMATION"
    return {**result, "valuation": valuation, "valuation_conclusion": conclusion}


def valuation_columns(result):
    v = result.get("valuation", {})
    return {"valuation_status": v.get("status"), "valuation_conclusion": result.get("valuation_conclusion"),
            "valuation_period": v.get("period"), "valuation_source": v.get("source"),
            "valuation_fetched_at": v.get("fetched_at"), "valuation_sector": v.get("sector"),
            "valuation_warnings": " | ".join(v.get("warnings", [])),
            **{f"valuation_{k}": v.get("metrics", {}).get(k) for k in METRICS}}
