from __future__ import annotations

from typing import Protocol


class BrokerAdapter(Protocol):
    def account(self) -> dict: ...
    def positions(self) -> list[dict]: ...
    def submit_order(self, symbol: str, side: str, quantity: int, price: float) -> dict: ...


class LockedLiveBroker:
    """Cổng an toàn: không có adapter CTCK chính thức thì không thể gửi lệnh thật."""

    reason = "LIVE đang khóa: chưa cấu hình adapter API chính thức của công ty chứng khoán."

    def account(self) -> dict:
        raise RuntimeError(self.reason)

    def positions(self) -> list[dict]:
        raise RuntimeError(self.reason)

    def submit_order(self, symbol: str, side: str, quantity: int, price: float) -> dict:
        raise RuntimeError(self.reason)
