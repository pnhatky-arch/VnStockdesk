import copy
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd

from src.valuation import (VERSION, assess_valuation, attach_valuation, fetch_valuation,
                           normalize_ratios, safe_symbol, valuation_columns, load_valuation, atomic_json)
from src.valuation_provider import DistinctPeriodPager
from src.valuation_ui import LANGS, TEXT, vt
from src.ai_assistant import compact_context, local_answer

NOW = "2026-08-26T03:00:00Z"


def snapshot(symbol="ACB", pe=7, pb=1, sector="8350"):
    periods = [("2025-Q3", "2025-09-30"), ("2025-Q4", "2025-12-31"),
               ("2026-Q1", "2026-03-31"), ("2026-Q2", "2026-06-30")]
    rows = [{"period": p, "period_end": d, "pe": 12, "pb": 2, "eps": 3_000,
             "bvps": 15_000, "roe": 4.0, "debt_equity": None, "profit_growth": 10.0} for p, d in periods]
    rows[-1].update(pe=pe, pb=pb)
    return {"symbol": symbol, "version": VERSION, "history_loader_version":2, "history": rows, "source": "KBS", "sector": sector, "fetched_at": NOW}


class ValuationTests(unittest.TestCase):
    def test_pager_skips_repeat_without_relabelling_and_stops_at_limit(self):
        def page(period):
            return {"Head":[{"YearPeriod":2026,"TermName":period}], "Content":{"value":period}}
        fetch = Mock(side_effect=[page("Quý 2"), page("Quý 2"), page("Quý 1"), page("Quý 1")])
        pager = DistinctPeriodPager(max_pages=4)
        first = pager.fetch(fetch, page=1, page_size=4)
        second = pager.fetch(fetch, page=2, page_size=4)
        end = pager.fetch(fetch, page=3, page_size=4)
        self.assertEqual(first["Content"]["value"], "Quý 2")
        self.assertEqual(second["Content"]["value"], "Quý 1")
        self.assertEqual(end, {})
        self.assertEqual([c.kwargs["page"] for c in fetch.call_args_list], [1,2,3,4])
        self.assertTrue(all(c.kwargs["page_size"] == 1 for c in fetch.call_args_list))

    def test_pager_rejects_mixed_heads(self):
        with self.assertRaises(ValueError):
            DistinctPeriodPager().fetch(lambda **kw: {"Head":[{},{}]})

    def test_missing_warnings_name_only_absent_metrics(self):
        result = assess_valuation(snapshot(), now=NOW)
        self.assertIn("MISSING_DEBT_EQUITY", result["warnings"])
        self.assertNotIn("MISSING_ROE", result["warnings"])
        self.assertNotIn("MISSING_GROWTH", result["warnings"])
        self.assertNotIn("PARTIAL_FUNDAMENTALS", result["warnings"])

    def test_auto_peers_load_three_unique_members_and_reuse_cache(self):
        with TemporaryDirectory() as tmp:
            atomic_json(Path(tmp)/"sectors.json", {"fetched_at":NOW,"symbols":{"ACB":"8350","BID":"8350","CTG":"8350","VCB":"8350","FPT":"9530"}})
            provider = Mock(side_effect=lambda s: snapshot(s,12,2))
            result = load_valuation("ACB", cache_dir=tmp, now=NOW, provider=provider)
            self.assertEqual(result["peer_fetch_attempted"], ["BID","CTG","VCB"])
            self.assertNotIn("FEW_PEERS", result["warnings"])
            self.assertEqual(provider.call_count, 4)
            load_valuation("ACB", cache_dir=tmp, now=NOW, provider=provider)
            self.assertEqual(provider.call_count, 4)

    def test_auto_peers_bounds_failed_attempts_and_keeps_threshold(self):
        with TemporaryDirectory() as tmp:
            atomic_json(Path(tmp)/"sectors.json", {"fetched_at":NOW,"symbols":{"ACB":"8350",**{f"X{i}":"8350" for i in range(10)}}})
            provider = Mock(side_effect=lambda s: snapshot(s) if s=="ACB" else {"symbol":s,"history":[]})
            result = load_valuation("ACB", cache_dir=tmp, now=NOW, provider=provider)
            self.assertEqual(len(result["peer_fetch_attempted"]), 5)
            self.assertIn("FEW_PEERS", result["warnings"])

    def test_matrix_aliases_units_and_ambiguous_period(self):
        frame = pd.DataFrame({
            "item_id": ["pe_ratio", "trailing_eps", "book_value_per_share_bvps", "debt_to_equity", "profit_after_tax"],
            "item": ["", "", "", "", "Tăng trưởng lợi nhuận sau thuế"],
            "unit": ["Lần", "VNĐ", "VNĐ", "%", "%"],
            "2026-Q2": [8, 2000, 10000, 150, -10], "2026-Q2_1": [99]*5,
            "2026-Q1": [None, -100, 0, 120, 5],
        })
        result = normalize_ratios(frame)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[-1]["pe"], 8)
        self.assertEqual(result[-1]["debt_equity"], 1.5)
        self.assertEqual(result[-1]["profit_growth"], -10)
        self.assertIsNone(result[0]["pe"])
        self.assertEqual(result[0]["eps"], -100)
        self.assertEqual(result[0]["bvps"], 0)

    def test_legacy_rows_sort_and_nonfinite(self):
        frame = pd.DataFrame({"year": [2026, 2025], "quarter": [2, 4], "priceToEarning": [8, float("inf")], "priceToBook": [1.2, 1.5]})
        rows = normalize_ratios(frame)
        self.assertEqual(rows[-1]["period"], "2026-Q2")
        self.assertIsNone(rows[0]["pe"])
        self.assertIsNone(rows[-1]["roe"])

    def test_peers_exclude_self_other_sectors_sources_periods_and_duplicates(self):
        target = snapshot()
        peers = [snapshot(s, 12, 2) for s in ("VCB", "BID", "CTG")]
        other = snapshot("FPT", 100, 20, sector="9999")
        stale = snapshot("OLD", 100, 20); stale["fetched_at"] = "2025-01-01"
        source = snapshot("SSI", 100, 20); source["source"] = "VCI"
        period = snapshot("XYZ", 100, 20); period["history"].pop()
        result = assess_valuation(target, peers + [target, peers[0], other, stale, source, period], now=NOW)
        comparison = next(c for c in result["comparisons"] if c["metric"] == "PE" and c["basis"] == "PEERS")
        self.assertEqual(comparison["count"], 3)
        self.assertEqual(comparison["median"], 12)
        self.assertEqual(result["status"], "LOWER_RELATIVE")
        self.assertEqual(comparison["symbols"], ["BID", "CTG", "VCB"])

    def test_negative_or_zero_denominator_cannot_be_cheap(self):
        for field in ("pe", "pb", "eps", "bvps"):
            for value in (0, -1):
                data = snapshot(); data["history"][-1][field] = value
                self.assertEqual(assess_valuation(data, now=NOW)["status"], "CAUTION")

    def test_stale_future_or_failed_data_do_not_contribute(self):
        for transform in (lambda d: d.update(fetched_at="2020-01-01"),
                          lambda d: d.update(fetch_error="FETCH_FAILED"),
                          lambda d: d["history"][-1].update(period_end="2027-01-01"),
                          lambda d: d.update(history=d["history"][:1])):
            data = snapshot(); transform(data)
            self.assertEqual(assess_valuation(data, now=NOW)["status"], "UNAVAILABLE")

    def test_no_benchmark_is_not_fair_value(self):
        data = snapshot(); data["history"] = data["history"][-1:]
        result = assess_valuation(data, now=NOW)
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertIn("FEW_PEERS", result["warnings"])
        self.assertIn("SHORT_HISTORY", result["warnings"])

    def test_ambiguous_provider_periods_cannot_support_conclusion(self):
        data = snapshot(); data["provider_warnings"] = ["AMBIGUOUS_PERIODS"]
        self.assertEqual(assess_valuation(data, now=NOW)["status"], "UNAVAILABLE")

    def test_weak_financial_health_overrides_optimistic_context(self):
        for field, value in (("roe", -1), ("profit_growth", -20)):
            data = snapshot(); data["history"][-1][field] = value
            v = assess_valuation(data, now=NOW)
            result = attach_valuation({"consensus_score":50, "data_quality":{"data_quality":"GOOD"}}, v)
            self.assertEqual(result["valuation_conclusion"], "RISK_REVIEW")

    def test_cache_daily_refresh_failure_retains_old_timestamp_and_backoff(self):
        with TemporaryDirectory() as tmp:
            provider = Mock(return_value=snapshot())
            first = fetch_valuation("ACB", cache_dir=tmp, now=NOW, provider=provider)
            fetch_valuation("ACB", cache_dir=tmp, now=NOW, provider=provider)
            self.assertEqual(provider.call_count, 1)
            provider.side_effect = RuntimeError("secret must not leak")
            failed = fetch_valuation("ACB", cache_dir=tmp, now="2026-08-27T04:00:00Z", provider=provider)
            self.assertEqual(failed["fetched_at"], first["fetched_at"])
            self.assertEqual(failed["history"], first["history"])
            self.assertNotIn("secret", json.dumps(failed))
            fetch_valuation("ACB", cache_dir=tmp, now="2026-08-27T04:01:00Z", provider=provider)
            self.assertEqual(provider.call_count, 2)
            fetch_valuation("ACB", refresh=True, cache_dir=tmp, now="2026-08-27T04:02:00Z", provider=provider)
            self.assertEqual(provider.call_count, 3)

    def test_old_fallback_never_replaces_new_report(self):
        with TemporaryDirectory() as tmp:
            fetch_valuation("ACB", cache_dir=tmp, now=NOW, provider=lambda s: snapshot())
            old = snapshot(); old["history"] = old["history"][:1]
            result = fetch_valuation("ACB", refresh=True, cache_dir=tmp, now=NOW, provider=lambda s: old)
            self.assertEqual(result["history"][-1]["period"], "2026-Q2")
            self.assertEqual(result["fetch_error"], "FETCH_FAILED")

    def test_provider_timeout_does_not_crash_analysis(self):
        with TemporaryDirectory() as tmp, patch("src.valuation.subprocess.run", side_effect=subprocess.TimeoutExpired("provider", 75)):
            result = fetch_valuation("ACB", cache_dir=tmp, now=NOW)
            self.assertEqual(result["fetch_error"], "FETCH_FAILED")
            self.assertEqual(assess_valuation(result, now=NOW)["status"], "UNAVAILABLE")

    def test_safe_symbol(self):
        for value in ("../ACB", "", "VN30F1M", "/tmp/X"):
            with self.assertRaises(ValueError): safe_symbol(value)

    def test_corrupt_cache_records_fail_closed(self):
        data = snapshot(); data["history"].append({"period": "not-a-date"})
        self.assertEqual(assess_valuation(data, now=NOW)["status"], "UNAVAILABLE")

    def test_scanner_adds_valuation_without_changing_technical_score(self):
        import scan
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = tuple(root / f"{name}.{ext}" for name, ext in (("scan","csv"),("errors","csv"),("meta","json"),("checkpoint","csv")))
            base = {"symbol":"ACB", "final_signal":"WATCH", "consensus_score":12,
                    **{f"{tf}_signal":"WATCH" for tf in ("1d","1w","1m","1y")}}
            info = {"rows":150, "start":"2025-01-01", "end":"2026-08-26", "age_days":0,
                    "data_quality":"GOOD", "recent_nonzero_volume_ratio":1, "median_turnover_20d_vnd":1e9}
            with patch.object(scan, "output_paths", return_value=paths), \
                 patch.object(scan, "get_market_universe", return_value=["ACB"]), \
                 patch.object(scan, "get_history", return_value=pd.DataFrame()), \
                 patch.object(scan, "cache_diagnostics", return_value=info), \
                 patch.object(scan, "analyze_symbol", return_value=base), \
                 patch.object(scan, "flatten_analysis", side_effect=lambda r:dict(r)), \
                 patch.object(scan, "fetch_company_news", return_value=(pd.DataFrame(),None)), \
                 patch.object(scan, "fetch_valuation", return_value=snapshot()), \
                 patch.object(scan, "CACHE_DIR", root):
                scan.main(scope="VN30", resume=False)
            result = pd.read_csv(paths[0])
            self.assertEqual(result.iloc[0]["consensus_score"], 12)
            self.assertEqual(result.iloc[0]["valuation_pe"], 7)
            self.assertEqual(result.iloc[0]["valuation_source"], "KBS")

    def test_technical_decision_and_orders_are_unchanged(self):
        original = {"symbol":"ACB", "consensus_score":-30, "confidence":75, "system_action":"SELL",
                    "data_quality":{"data_quality":"GOOD"}, "strategy_plan":{"stop_loss":10}}
        backup = copy.deepcopy(original)
        valuation = assess_valuation(snapshot(), now=NOW)
        result = attach_valuation(original, valuation)
        self.assertEqual(original, backup)
        for k, value in original.items(): self.assertEqual(result[k], value)
        self.assertEqual(result["valuation_conclusion"], "VALUE_TREND_CONFLICT")
        self.assertFalse(result["valuation"]["trade_enabled"])
        self.assertEqual(valuation_columns(result)["valuation_pe"], 7)

    def test_ai_context_includes_limits_not_entire_history(self):
        result = attach_valuation({"consensus_score":30, "data_quality":{"data_quality":"GOOD"}}, assess_valuation(snapshot(), now=NOW))
        context = compact_context("ACB", result, {}, {})
        self.assertNotIn("history", context["valuation"])
        self.assertEqual(context["valuation"]["metrics"]["pe"], 7)
        self.assertIn("2026-Q2", local_answer("P/E và P/B?", context))
        self.assertIn("Aktienbewertung", local_answer("Bewertung?", context, language="de"))

    def test_five_languages_complete(self):
        for key, translations in TEXT.items():
            self.assertEqual(len(translations), 5, key)
            for lang in LANGS: self.assertTrue(vt(lang, key).strip())


if __name__ == "__main__": unittest.main()
