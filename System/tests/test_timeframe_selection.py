import ast
import unittest
from pathlib import Path
import pandas as pd
from src.timeframes import resample_ohlcv, TIMEFRAME_ORDER
from src.futures_engine import analyze_futures_chart_frame, FRAME_WEIGHTS
from src.portfolio_timeframes import portfolio_frame_evidence


def prices():
    return pd.DataFrame({"time":pd.to_datetime(["2024-02-29", "2024-12-30", "2026-01-05", "2026-08-26"]),
                         "open":[10,12,20,23], "high":[13,15,25,28],
                         "low":[9,11,18,21], "close":[12,14,23,26], "volume":[100,200,300,400]})


class TimeframeSelectionTests(unittest.TestCase):
    def test_year_uses_real_ohlcv_and_no_empty_year(self):
        source = prices()
        result = resample_ohlcv(source, "1Y")
        self.assertEqual(list(result.time.dt.year), [2024,2026])
        self.assertEqual(result.iloc[0][["open","high","low","close","volume"]].tolist(), [10,15,9,14,300])
        self.assertEqual(result.iloc[1][["open","high","low","close","volume"]].tolist(), [20,28,18,26,700])
        self.assertEqual(result.time.max(), source.time.max())
        self.assertEqual(list(result.source_bars), [2,2])

    def test_order_and_duplicate_dont_double_volume(self):
        source = prices()
        shuffled = pd.concat([source.iloc[::-1],source.iloc[[0]]],ignore_index=True)
        pd.testing.assert_frame_equal(resample_ohlcv(source,"1Y"),resample_ohlcv(shuffled,"1Y"))

    def test_month_week_year_never_return_daily_window(self):
        source = prices()
        for tf in ("1W","1M","1Y"):
            view = analyze_futures_chart_frame({"1D":source},tf)
            self.assertEqual(view["timeframe"],tf)
            self.assertEqual(view["bars"],len(resample_ohlcv(source,tf)))
            self.assertEqual(view["status"],"INSUFFICIENT_DATA")
            self.assertTrue(view["data"].ma20.isna().all())
            self.assertNotIn("support",view)

    def test_yearly_portfolio_missing_history_not_synthetic_signal(self):
        result = {"timeframes":{"1Y":{"status":"OK","bars":8,"signal":"BUY","signal_score":50}}}
        view = portfolio_frame_evidence(result,"1Y")
        self.assertEqual(view["Trạng thái khung"],"INSUFFICIENT_HISTORY")
        self.assertIsNone(view["Signal khung"])
        self.assertIsNone(view["Score khung"])
        future = portfolio_frame_evidence({},"1Y",futures_frames={"1D":prices()})
        self.assertEqual(future["Số nến khung"],2)
        self.assertIsNone(future["Signal khung"])

    def test_quarter_removed_and_bot_strategy_unchanged(self):
        self.assertEqual(TIMEFRAME_ORDER,["1D","1W","1M","1Y"])
        self.assertEqual(FRAME_WEIGHTS,{"1D":.35,"1H":.40,"15M":.25})
        for callback in (lambda:resample_ohlcv(prices(),"1Q"),
                         lambda:analyze_futures_chart_frame({"1D":prices()},"1Q"),
                         lambda:portfolio_frame_evidence({},"1Q")):
            with self.assertRaises(ValueError): callback()

    def test_selection_does_not_mutate_multiframe_report(self):
        result = {"final_signal":"BUY","consensus_score":42,"timeframes":{"1M":{"status":"OK","bars":40,"signal":"SELL","signal_score":-40}}}
        view = portfolio_frame_evidence(result,"1M")
        self.assertEqual(view["Signal khung"],"SELL")
        self.assertEqual(result["final_signal"],"BUY")

    def test_bot_start_never_receives_chart_or_portfolio_frame(self):
        source=(Path(__file__).resolve().parents[1]/"app.py").read_text()
        tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="start_bot":
                self.assertEqual(ast.unparse(node.args[1]),"int(interval)")
                self.assertNotIn("timeframe",ast.unparse(node))
        for key in ("stock_chart_timeframe","live_futures_chart_timeframe","portfolio_analysis_timeframe","futures_portfolio_analysis_timeframe"):
            self.assertIn(key,source)
