#!/usr/bin/env python3
"""Verify that a public URL exposes VnStockDesk, not a static component."""

from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def fetch(url: str, timeout: float = 12.0) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "VnStockDesk-deployment-check/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(512_000).decode("utf-8", "replace")
    except HTTPError as exc:
        return exc.code, exc.read(64_000).decode("utf-8", "replace")


def verify(base_url: str) -> list[str]:
    base_url = base_url.rstrip("/") + "/"
    problems: list[str] = []

    root_status, root_body = fetch(base_url)
    root_lower = root_body.lower()
    if root_status != 200:
        problems.append(f"Trang chính trả về HTTP {root_status}, cần HTTP 200.")
    if "grid.js" in root_lower or 'aria-label="data table"' in root_lower:
        problems.append(
            "URL đang phát nhầm assets/desk_grid (bảng nội bộ), không phải dashboard."
        )
    if "streamlit" not in root_lower and "_stcore" not in root_lower:
        problems.append("Trang chính không có dấu hiệu của ứng dụng Streamlit.")

    health_url = urljoin(base_url, "_stcore/health")
    health_status, health_body = fetch(health_url)
    if health_status != 200 or health_body.strip().lower() != "ok":
        problems.append(
            f"Endpoint Streamlit /_stcore/health không hợp lệ "
            f"(HTTP {health_status}, nội dung {health_body.strip()[:80]!r})."
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra URL công khai VnStockDesk")
    parser.add_argument(
        "url",
        nargs="?",
        default="http://127.0.0.1:8503",
        help="URL dashboard cần kiểm tra",
    )
    args = parser.parse_args()
    try:
        problems = verify(args.url)
    except (URLError, TimeoutError, OSError) as exc:
        print(f"KHÔNG KẾT NỐI ĐƯỢC: {exc}")
        return 2
    if problems:
        print(f"TRIỂN KHAI CHƯA ĐÚNG: {args.url}")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"TRIỂN KHAI HỢP LỆ: {args.url}")
    print("- Dashboard Streamlit và endpoint sức khỏe đều hoạt động.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
