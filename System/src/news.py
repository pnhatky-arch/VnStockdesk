from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.parse import urljoin

import numpy as np
import pandas as pd
from .local_io import atomic_csv, atomic_json

from .paths import NEWS_DIR


POSITIVE_TERMS = {
    "tăng trưởng": 2, "lợi nhuận tăng": 3, "lãi tăng": 3, "vượt kế hoạch": 3,
    "kỷ lục": 2, "trúng thầu": 2, "ký hợp đồng": 2, "được cấp phép": 2,
    "mua lại": 1, "cổ tức": 1, "nâng hạng": 2, "khuyến nghị mua": 2,
    "mở rộng": 1, "top": 1, "tích cực": 1, "phục hồi": 1,
}

NEGATIVE_TERMS = {
    "lỗ": -3, "lợi nhuận giảm": -3, "sụt giảm": -2, "giảm mạnh": -2,
    "bị phạt": -3, "xử phạt": -3, "điều tra": -4, "khởi tố": -5,
    "bắt tạm giam": -5, "vi phạm": -3, "đình chỉ": -4, "hủy niêm yết": -5,
    "cảnh báo": -2, "chậm thanh toán": -4, "vỡ nợ": -5, "nợ quá hạn": -4,
    "bán tháo": -3, "hạ hạng": -2, "pha loãng": -2, "rủi ro": -1,
}

EVENT_TERMS = {
    "KẾT QUẢ KINH DOANH": ("lợi nhuận", "doanh thu", "kinh doanh", "báo cáo tài chính"),
    "PHÁP LÝ/QUẢN TRỊ": ("khởi tố", "điều tra", "xử phạt", "vi phạm", "miễn nhiệm", "bổ nhiệm"),
    "VỐN/CỔ TỨC": ("cổ tức", "phát hành", "mua lại", "tăng vốn", "pha loãng"),
    "HỢP ĐỒNG/DỰ ÁN": ("trúng thầu", "hợp đồng", "dự án", "được cấp phép"),
    "GIAO DỊCH CỔ ĐÔNG": ("cổ đông", "nội bộ", "đăng ký mua", "đăng ký bán"),
}


def _first_present(df: pd.DataFrame, names: tuple[str, ...], default=None):
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([default] * len(df), index=df.index)


def _classify(text: str) -> tuple[float, str, list[str]]:
    normalized = str(text or "").lower()
    hits: list[str] = []
    raw = 0.0
    for term, value in {**POSITIVE_TERMS, **NEGATIVE_TERMS}.items():
        if term in normalized:
            raw += value
            hits.append(term)
    event = "TIN CHUNG"
    for label, terms in EVENT_TERMS.items():
        if any(term in normalized for term in terms):
            event = label
            break
    return float(np.clip(raw, -5, 5)), event, hits[:4]


def normalize_news(raw: pd.DataFrame | None, source: str, symbol: str) -> pd.DataFrame:
    columns = ["symbol", "published", "title", "summary", "url", "source"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=columns)
    df = raw.copy()
    out = pd.DataFrame(index=df.index)
    out["symbol"] = symbol.upper()
    out["published"] = pd.to_datetime(
        _first_present(df, ("publish_time", "public_date", "published", "date")),
        errors="coerce",
    )
    out["title"] = _first_present(df, ("title", "news_title", "friendly_title"), "").fillna("").astype(str)
    out["summary"] = _first_present(
        df, ("head", "news_short_content", "news_sub_title", "news_full_content"), ""
    ).fillna("").astype(str)
    urls = _first_present(df, ("url", "news_source_link"), "").fillna("").astype(str)
    if source.upper() == "KBS":
        urls = urls.map(lambda value: urljoin("https://kbbuddywts.kbsec.com.vn", value) if value else "")
    out["url"] = urls
    out["source"] = source.upper()
    return out.dropna(subset=["published"]).drop_duplicates(["title", "published"])


def _cache_paths(symbol: str):
    safe_symbol = symbol.upper().replace("/", "_")
    return NEWS_DIR / f"{safe_symbol}.csv", NEWS_DIR / f"{safe_symbol}.meta.json"


def _read_cached_news(symbol: str) -> tuple[pd.DataFrame, dict]:
    csv_path, meta_path = _cache_paths(symbol)
    if not csv_path.exists():
        return normalize_news(None, "", symbol), {}
    try:
        cached = pd.read_csv(csv_path)
        cached["published"] = pd.to_datetime(cached["published"], errors="coerce")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return cached.dropna(subset=["published"]), meta
    except (OSError, ValueError, json.JSONDecodeError):
        return normalize_news(None, "", symbol), {}


def _write_news_cache(symbol: str, news: pd.DataFrame, source: str) -> None:
    csv_path, meta_path = _cache_paths(symbol)
    atomic_csv(csv_path, news)
    atomic_json(meta_path, {
        "symbol": symbol.upper(), "source": source,
        "fetched_at": pd.Timestamp.now().isoformat(), "count": len(news),
    })


def fetch_company_news(symbol: str, limit: int = 30, refresh: bool = False) -> tuple[pd.DataFrame, str | None]:
    """Lấy tin mới ít nhất mỗi ngày; lỗi mạng dùng cache cũ và không làm hỏng dashboard."""
    cached, meta = _read_cached_news(symbol)
    fetched_at = pd.to_datetime(meta.get("fetched_at"), errors="coerce")
    today = pd.Timestamp.now().date()
    if not refresh and pd.notna(fetched_at) and fetched_at.date() == today:
        return cached.head(limit).reset_index(drop=True), None

    errors: list[str] = []
    # KBS thường phản hồi nhanh hơn; VCI là nguồn dự phòng giàu dữ liệu hơn.
    for source in ("KBS", "VCI"):
        try:
            from vnstock.api.company import Company

            raw = Company(source=source, symbol=symbol.upper()).news()
            news = normalize_news(raw, source, symbol)
            if not news.empty:
                _write_news_cache(symbol, news, source)
                return news.sort_values("published", ascending=False).head(limit).reset_index(drop=True), None
        except Exception as exc:  # nguồn ngoài có thể tạm thời lỗi/chặn giới hạn
            errors.append(f"{source}: {exc}")
    if not cached.empty:
        return cached.head(limit).reset_index(drop=True), "Không tải được tin mới; đang dùng bản lưu gần nhất. " + " | ".join(errors)
    return normalize_news(None, "", symbol), " | ".join(errors) or "Không có tin gần đây."


def score_news(news: pd.DataFrame, lookback_days: int = 30, now: datetime | None = None) -> dict:
    """Điểm tác động tiêu đề có trọng số thời gian, giới hạn trong [-10, 10]."""
    if news is None or news.empty:
        return {"score": 0.0, "label": "KHÔNG CÓ DỮ LIỆU", "count": 0, "items": []}
    current = pd.Timestamp(now or datetime.now(timezone.utc)).tz_localize(None)
    rows = []
    weighted_sum = weight_sum = 0.0
    for _, row in news.iterrows():
        published = pd.Timestamp(row["published"])
        if published.tzinfo is not None:
            published = published.tz_convert(None)
        age = max(0, (current - published).days)
        if age > lookback_days:
            continue
        raw_score, event, hits = _classify(f"{row.get('title', '')} {row.get('summary', '')}")
        recency = max(0.15, 1 - age / (lookback_days + 1))
        weighted_sum += raw_score * recency
        weight_sum += recency
        rows.append({**row.to_dict(), "age_days": age, "event_type": event, "impact": raw_score, "keywords": ", ".join(hits)})
    score = 0.0 if not weight_sum else float(np.clip(weighted_sum / weight_sum * 2, -10, 10))
    label = "TÍCH CỰC" if score >= 2 else "TIÊU CỰC" if score <= -2 else "TRUNG TÍNH"
    return {"score": round(score, 1), "label": label, "count": len(rows), "items": rows}
