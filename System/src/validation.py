from __future__ import annotations

import pandas as pd

from .analyzer import analyze_symbol


def walk_forward_validation(df: pd.DataFrame, horizon: int = 20, step: int = 20,
                            min_history: int = 260, threshold: float = 25.0) -> dict:
    """Kiểm định định hướng không nhìn trước; không mô phỏng khớp lệnh hay chi phí."""
    if horizon < 1 or step < 1: raise ValueError("horizon và step phải dương")
    records = []
    for end in range(min_history, len(df) - horizon, step):
        history = df.iloc[:end].copy()
        current = float(df.iloc[end - 1]["close"])
        future = float(df.iloc[end + horizon - 1]["close"])
        analysis = analyze_symbol("VALIDATION", history, reference_date=history.iloc[-1]["time"])
        score = float(analysis["consensus_score"])
        qualified = analysis["confidence"] >= 68 and analysis["timeframe_alignment"] >= 70 and analysis["decision_grade"] in {"A", "B"}
        prediction = (1 if score >= threshold else -1 if score <= -threshold else 0) if qualified else 0
        forward_return = (future / current - 1) * 100
        actual = 1 if forward_return > 0 else -1 if forward_return < 0 else 0
        records.append({"time": df.iloc[end - 1]["time"], "score": round(score, 1),
                        "confidence": analysis["confidence"], "alignment": analysis["timeframe_alignment"],
                        "grade": analysis["decision_grade"],
                        "prediction": prediction, "forward_return_pct": round(forward_return, 2),
                        "directional_edge_pct": round(forward_return * prediction, 2) if prediction else 0.0,
                        "correct": prediction != 0 and prediction == actual})
    table = pd.DataFrame(records)
    if table.empty:
        return {"status": "INSUFFICIENT_HISTORY", "observations": 0, "signals": 0,
                "hit_rate": None, "coverage": 0.0, "avg_forward_return": None, "records": table}
    signals = table[table["prediction"] != 0]
    return {
        "status": "OK", "observations": len(table), "signals": len(signals),
        "hit_rate": None if signals.empty else round(float(signals["correct"].mean() * 100), 1),
        "coverage": round(float(len(signals) / len(table) * 100), 1),
        "avg_forward_return": None if signals.empty else round(float(signals["directional_edge_pct"].mean()), 2),
        "bullish_signals": int((signals.prediction == 1).sum()),
        "bearish_signals": int((signals.prediction == -1).sum()),
        "bullish_avg_return": None if not (signals.prediction == 1).any() else round(float(signals.loc[signals.prediction == 1, "forward_return_pct"].mean()), 2),
        "bearish_avg_return": None if not (signals.prediction == -1).any() else round(float(signals.loc[signals.prediction == -1, "forward_return_pct"].mean()), 2),
        "records": table,
    }
