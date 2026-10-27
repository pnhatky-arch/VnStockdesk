from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


SYSTEM_INSTRUCTIONS = """Bạn là AI Analyst của hệ thống Thị trường Chứng khoán Việt Nam.
Chỉ sử dụng dữ liệu phân tích được cung cấp trong CONTEXT cho các nhận định về mã cổ phiếu.
Phân biệt rõ dữ kiện, diễn giải và điều chưa biết. Không bịa giá, tin tức hay chỉ báo.
Trả lời đúng ngôn ngữ được yêu cầu, súc tích, có cấu trúc và nêu rủi ro quan trọng.
Không cam kết lợi nhuận, không nói chắc chắn mua/bán và không thay thế tư vấn đầu tư.
Định giá là bối cảnh riêng: phải nêu kỳ báo cáo, nguồn, dữ liệu thiếu/cũ và cảnh báo.
P/E, P/B là ảnh chụp theo kỳ, không được gọi là giá trị trực tiếp; không coi thấp là lệnh mua.
Khi người dùng hỏi hành động, giải thích quyết định hệ thống, điều kiện kích hoạt,
mức vô hiệu/cắt lỗ nếu context có, và nhắc người dùng tự chịu trách nhiệm quyết định."""


def compact_context(symbol: str, result: dict[str, Any], latest: dict[str, Any],
                    wyckoff: dict[str, Any], news: dict[str, Any] | None = None) -> dict[str, Any]:
    """Giới hạn context vào dữ liệu cần cho trả lời, tránh gửi toàn bộ lịch sử OHLCV."""
    frames = {}
    for timeframe, frame in result.get("timeframes", {}).items():
        frames[timeframe] = {
            key: frame.get(key) for key in (
                "signal", "signal_score", "confidence", "ma_regime", "rsi14",
                "rvol", "wyckoff_event", "wyckoff_phase", "wyckoff_bias", "atr_pct",
                "macd", "macd_signal", "macd_hist", "adx14", "plus_di14", "minus_di14", "obv_bias",
            )
        }
    return {
        "symbol": symbol,
        "latest": {key: latest.get(key) for key in ("time", "open", "high", "low", "close", "volume")},
        "decision": {
            key: result.get(key) for key in (
                "system_action", "decision_summary", "consensus_score", "confidence",
                "decision_grade", "market_regime", "timeframe_alignment", "conflict_level",
                "strategic_score", "tactical_score", "risk_flags", "decision_drivers",
            )
        },
        "data_quality": result.get("data_quality", {}),
        "strategy_plan": result.get("strategy_plan", {}),
        "wyckoff": {key: wyckoff.get(key) for key in (
            "phase", "event", "bias", "support", "resistance", "range_low", "range_high",
        )},
        "timeframes": frames,
        "news_context": news or {"status": "not_loaded"},
        "valuation": {key: result.get("valuation", {}).get(key) for key in (
            "status", "source", "fetched_at", "period", "sector", "metrics", "comparisons", "warnings", "basis", "trade_enabled",
        )},
        "valuation_conclusion": result.get("valuation_conclusion"),
    }


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def local_answer(question: str, context: dict[str, Any], language: str = "vi") -> str:
    """Trợ lý phân tích xác định, luôn chạy được và không gọi mạng."""
    q = question.casefold().strip()
    symbol = context.get("symbol", "—")
    decision = context.get("decision", {})
    plan = context.get("strategy_plan", {})
    wy = context.get("wyckoff", {})
    frames = context.get("timeframes", {})
    quality = context.get("data_quality", {})
    action = str(decision.get("system_action", "CHỜ_XÁC_NHẬN")).replace("_", " ")
    risks = decision.get("risk_flags") or []

    if any(word in q for word in ("p/e", "p/b", "định giá", "valuation", "roe", "bvps", "eps", "估值", "оценка", "bewertung")):
        from .valuation_ui import vt
        v = context.get("valuation", {})
        metrics = v.get("metrics") or {}
        status = v.get("status") or "UNAVAILABLE"
        warnings = " • ".join(vt(language, w) for w in (v.get("warnings") or []))
        return (
            f"**{vt(language, 'title')} {symbol}: {vt(language, status)}**\n\n"
            f"- P/E: {_fmt(metrics.get('pe'), 2)} · P/B: {_fmt(metrics.get('pb'), 2)}\n"
            f"- ROE (%): {_fmt(metrics.get('roe'), 2)}\n"
            f"- {vt(language, 'source')}: {v.get('source') or '—'} · {vt(language, 'period')}: {v.get('period') or '—'}\n"
            f"- {vt(language, context.get('valuation_conclusion') or 'INCOMPLETE')}\n\n"
            f"{warnings}\n\n{vt(language, 'snapshot')}"
        )

    if any(word in q for word in ("wyckoff", "spring", "sos", "lps", "upthrust", "sow")):
        return (
            f"**Wyckoff của {symbol}**\n\n"
            f"- Event: `{wy.get('event', 'NONE')}` · Phase: `{wy.get('phase', '—')}` · Bias: `{wy.get('bias', '—')}`\n"
            f"- Hỗ trợ: **{_fmt(wy.get('support'), 2)}** · Kháng cự: **{_fmt(wy.get('resistance'), 2)}**\n"
            "- Đây là nhận diện quy tắc xấp xỉ; cần xác nhận bằng score, MA, RSI, RVOL và khung cao hơn."
        )

    if any(word in q for word in ("đa khung", "khung thời gian", "xung đột", "1d", "1w", "1m", "1y")):
        rows = [
            f"- `{tf}`: {frame.get('signal', '—')} · score {_fmt(frame.get('signal_score'))} · "
            f"tin cậy {_fmt(frame.get('confidence'), 0)}%"
            for tf, frame in frames.items()
        ]
        return (
            f"**Đồng thuận đa khung {symbol}: {_fmt(decision.get('timeframe_alignment'), 0)}%**\n\n"
            + "\n".join(rows)
            + f"\n\nMức xung đột: **{decision.get('conflict_level', '—')}**. Ưu tiên khung 1W–1M cho xu hướng và 1D cho kích hoạt."
        )

    if any(word in q for word in ("rủi ro", "cắt lỗ", "stop", "an toàn", "vô hiệu")):
        risk_text = "\n".join(f"- {item}" for item in risks) if risks else "- Chưa có cờ rủi ro nổi bật."
        stop = plan.get("stop_loss") or plan.get("protective_stop") or plan.get("bearish_invalidation")
        return (
            f"**Rủi ro hiện tại của {symbol}**\n\n{risk_text}\n"
            f"- Chất lượng dữ liệu: `{quality.get('data_quality', '—')}`\n"
            f"- Mức bảo vệ/vô hiệu tham khảo: **{_fmt(stop, 2)}**\n\n"
            "Không mở vị thế nếu dữ liệu bị WATCH/REJECT hoặc mức rủi ro không phù hợp với kế hoạch vốn."
        )

    if any(word in q for word in ("chiến lược", "kế hoạch", "điểm vào", "mục tiêu", "target")):
        return (
            f"**Kế hoạch hệ thống cho {symbol}**\n\n"
            f"- Chiến lược: `{plan.get('strategy', 'NO_TRADE')}` · Trạng thái: `{plan.get('status', 'NO_PLAN')}`\n"
            f"- Vùng vào: **{_fmt(plan.get('entry_low'), 2)} – {_fmt(plan.get('entry_high'), 2)}**\n"
            f"- Trigger: **{_fmt(plan.get('trigger') or plan.get('bullish_trigger'), 2)}**\n"
            f"- Cắt lỗ: **{_fmt(plan.get('stop_loss') or plan.get('protective_stop'), 2)}**\n"
            f"- Mục tiêu: **{_fmt(plan.get('target_1') or plan.get('reference_target'), 2)} / {_fmt(plan.get('target_2'), 2)}**\n\n"
            f"{plan.get('note', 'Chỉ hành động khi điều kiện được xác nhận.')}"
        )

    if any(word in q for word in ("mua", "bán", "nên", "quyết định", "tín hiệu", "tổng quan")):
        risk_line = " • ".join(risks[:2]) if risks else "Không có cờ rủi ro nổi bật"
        return (
            f"**Phân tích nhanh {symbol}**\n\n"
            f"- Quyết định hệ thống: **{action}**\n"
            f"- Điểm tổng hợp: **{_fmt(decision.get('consensus_score'))}** · Tin cậy: **{_fmt(decision.get('confidence'), 0)}%** · Hạng `{decision.get('decision_grade', '—')}`\n"
            f"- Chế độ: `{decision.get('market_regime', '—')}` · Đồng thuận: {_fmt(decision.get('timeframe_alignment'), 0)}%\n"
            f"- Rủi ro: {risk_line}\n\n"
            f"{decision.get('decision_summary', '')} Đây là phân tích định lượng, không phải khuyến nghị đầu tư."
        )

    return (
        f"Mình đang có ngữ cảnh phân tích của **{symbol}**. Bạn có thể hỏi về:\n\n"
        "- quyết định mua/bán và độ tin cậy;\n"
        "- Wyckoff Event/Phase/Bias;\n"
        "- xung đột 1D–1Y;\n"
        "- vùng vào, trigger, stop và mục tiêu;\n"
        "- chất lượng dữ liệu và các rủi ro.\n\n"
        "Nếu câu hỏi cần dữ liệu ngoài context hiện tại, hãy bật AI Online hoặc cung cấp thêm dữ liệu."
    )


def online_answer(question: str, context: dict[str, Any], language: str = "vi",
                  api_key: str | None = None, model: str | None = None,
                  timeout: int = 45) -> str:
    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not key:
        raise ValueError("Chưa cấu hình OPENAI_API_KEY.")
    payload = {
        "model": model or os.getenv("OPENAI_MODEL", "gpt-5.4"),
        "instructions": SYSTEM_INSTRUCTIONS + f"\nNgôn ngữ trả lời: {language}.",
        "input": "CONTEXT:\n" + json.dumps(context, ensure_ascii=False, default=str) + "\n\nQUESTION:\n" + question,
        "max_output_tokens": 900,
        "store": False,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Không kết nối được OpenAI API: {exc}") from exc
    text = data.get("output_text")
    if text:
        return str(text).strip()
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    if not parts:
        raise RuntimeError("OpenAI API không trả về nội dung văn bản.")
    return "\n".join(parts).strip()
