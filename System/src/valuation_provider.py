"""Bounded subprocess adapter for the installed vnstock Finance API."""
from __future__ import annotations

import json
import sys

from .valuation import CACHE_DIR, _age, _now, atomic_json, normalize_ratios, read_json, safe_symbol


class DistinctPeriodPager:
    """Skip repeated report pages without relabelling any financial values."""
    def __init__(self, max_pages=12):
        self.next_page = 1
        self.max_pages = max_pages
        self.seen = set()

    def fetch(self, fetch_page, *args, **kwargs):
        while self.next_page <= self.max_pages:
            kwargs.update(page=self.next_page, page_size=1)
            self.next_page += 1
            raw = fetch_page(*args, **kwargs)
            heads = raw.get("Head", []) if isinstance(raw, dict) else []
            if not heads:
                return {}
            # Single-period requests must never pair multiple headings with
            # one Value1 column. Fail closed if the upstream schema changes.
            if len(heads) != 1:
                raise ValueError("Ambiguous single-period response")
            head = heads[0]
            key = (str(head.get("YearPeriod", "")), str(head.get("TermName", "")))
            if not all(key):
                raise ValueError("Missing report period")
            if key not in self.seen:
                self.seen.add(key)
                return raw
        return {}


def sector_map():
    path = CACHE_DIR / "sectors.json"
    cached = read_json(path)
    if 0 <= _age(cached.get("fetched_at"), _now()) < 7 * 86400:
        return cached.get("symbols", {})
    if 0 <= _age(cached.get("attempted_at"), _now()) < 900:
        return {}
    try:
        from vnstock.explorer.vci.listing import Listing
        frame = Listing().symbols_by_industries(lang="en")
        frame = frame[frame["icb_level"] == 3]
        symbols = {str(r["symbol"]): str(r["icb_code"]) for _, r in frame.iterrows() if r.get("icb_code")}
        atomic_json(path, {"fetched_at": _now().isoformat(), "symbols": symbols})
        return symbols
    except Exception:
        try:
            atomic_json(path, {"attempted_at": _now().isoformat(), "symbols": {}})
        except OSError:
            pass
        return {}


def fetch_snapshot(symbol):
    # Bootstrap credentials without exposing them to logs or the JSON payload.
    from .bootstrap import KEY_STATUS  # noqa: F401
    symbol = safe_symbol(symbol)
    candidates = []
    for source in ("KBS", "VCI"):
        try:
            if source == "KBS":
                from vnstock.explorer.kbs.financial import Finance
                pager = DistinctPeriodPager()
                class SinglePeriodFinance(Finance):
                    def _fetch_financial_data(self, *args, **kwargs):
                        # Installed KBS reports document mixed values for
                        # page_size>1. Keep public ratio()/quota wrappers and
                        # parser, but fetch one period per page as its other
                        # financial-statement methods already do.
                        return pager.fetch(super()._fetch_financial_data, *args, **kwargs)

                finance = SinglePeriodFinance(symbol=symbol, period="quarter")
                finance.limit = 4  # current + 3 comparisons, within community allowance
                raw = finance.ratio(display_mode="all")
            else:
                from vnstock.explorer.vci.financial import Finance
                raw = Finance(symbol=symbol, period="quarter").ratio(lang="en", dropna=False)
            history = normalize_ratios(raw)
            if not history:
                continue
            warnings = ["AMBIGUOUS_PERIODS"] if any("_" in str(c) and str(c)[:4].isdigit() for c in raw.columns) else []
            candidate = {"symbol": symbol, "source": source, "history": history, "provider_warnings": warnings,
                         "history_loader_version": 2}
            candidates.append(candidate)
            if not warnings and 0 <= _age(history[-1]["period_end"], _now()) <= 200 * 86400:
                break
        except Exception:
            continue
    result = max(candidates, key=lambda c: c["history"][-1]["period_end"]) if candidates else {"symbol": symbol, "history": []}
    result["sector"] = sector_map().get(symbol)
    return result


if __name__ == "__main__":
    print("VALUATION_JSON=" + json.dumps(fetch_snapshot(sys.argv[1]), ensure_ascii=False, allow_nan=False))
