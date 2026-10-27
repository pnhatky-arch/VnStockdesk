"""Vietnam equity settlement dates used by the PAPER broker.

The default calendar excludes weekends. Additional exchange holidays can be
provided as comma-separated ISO dates through ``VN_TRADING_HOLIDAYS``.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import os
from zoneinfo import ZoneInfo


MARKET_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def market_now() -> datetime:
    return datetime.now(MARKET_TZ)


def _holidays() -> set[date]:
    values = os.getenv("VN_TRADING_HOLIDAYS", "")
    result: set[date] = set()
    for value in values.split(","):
        try:
            result.add(date.fromisoformat(value.strip()))
        except ValueError:
            continue
    return result


def is_business_day(value: date) -> bool:
    return value.weekday() < 5 and value not in _holidays()


def add_business_days(value: date, days: int) -> date:
    result = value
    remaining = max(0, int(days))
    while remaining:
        result += timedelta(days=1)
        if is_business_day(result):
            remaining -= 1
    return result


def settlement_time(trade_time: datetime, *, hour: int) -> datetime:
    local = trade_time.astimezone(MARKET_TZ) if trade_time.tzinfo else trade_time.replace(tzinfo=MARKET_TZ)
    settlement_day = add_business_days(local.date(), 2)
    return datetime.combine(settlement_day, time(hour=hour), tzinfo=MARKET_TZ)


def parse_market_time(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(MARKET_TZ) if parsed.tzinfo else parsed.replace(tzinfo=MARKET_TZ)
