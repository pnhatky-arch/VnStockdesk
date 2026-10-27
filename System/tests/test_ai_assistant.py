from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.ai_assistant import compact_context, local_answer, online_answer


def context():
    result = {
        "system_action": "THEO_DÕI_MUA", "decision_summary": "Đang chờ xác nhận.",
        "consensus_score": 35.0, "confidence": 78, "decision_grade": "B",
        "market_regime": "XU HƯỚNG TĂNG", "timeframe_alignment": 75,
        "conflict_level": "TRUNG BÌNH", "risk_flags": ["Khối lượng chưa xác nhận"],
        "strategy_plan": {"strategy": "CHỜ_BREAKOUT", "status": "WAIT_TRIGGER", "stop_loss": 20, "target_1": 25},
        "data_quality": {"data_quality": "GOOD"},
        "timeframes": {"1D": {"signal": "WATCH_BUY", "signal_score": 30, "confidence": 75}},
    }
    return compact_context("ACB", result, {"time": "2026-08-21", "close": 22.5},
                           {"event": "LPS", "phase": "MARKUP", "bias": "BULLISH", "support": 21, "resistance": 23})


class AIAssistantTests(unittest.TestCase):
    def test_compact_context_excludes_arbitrary_large_fields(self):
        value = context()
        self.assertEqual(value["symbol"], "ACB")
        self.assertNotIn("raw_ohlcv", json.dumps(value))
        self.assertEqual(value["timeframes"]["1D"]["signal"], "WATCH_BUY")

    def test_local_answer_routes_question_intent(self):
        value = context()
        self.assertIn("Wyckoff", local_answer("Wyckoff đang ở phase nào?", value))
        self.assertIn("Đồng thuận đa khung", local_answer("Có xung đột đa khung không?", value))
        self.assertIn("Rủi ro", local_answer("Rủi ro và stop loss?", value))
        self.assertIn("Phân tích nhanh", local_answer("Có nên mua không?", value))

    def test_online_requires_key_and_never_sends_without_it(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                online_answer("test", context())


if __name__ == "__main__":
    unittest.main()
