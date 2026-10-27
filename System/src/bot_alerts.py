"""Presentation freshness, not a change to trading risk checks or audit logs."""
from datetime import datetime, timezone


def is_recent_alert(alert: dict, now: datetime | None = None) -> bool:
    try:
        timestamp = datetime.fromisoformat(str(alert.get("time", "")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return False
        age = ((now or datetime.now(timezone.utc)) - timestamp).total_seconds()
        return 0 <= age <= 300
    except (TypeError, ValueError, OverflowError):
        return False
