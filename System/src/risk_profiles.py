"""Shared BOT risk profiles for equity and futures execution."""
from __future__ import annotations

RISK_PROFILES = {
    "LOW": {
        "label": "Thấp",
        "confidence": 78,
        "alignment": 75,
        "risk_multiplier": 0.60,
        "position_multiplier": 0.70,
        "allow_watch_buy": False,
    },
    "MEDIUM": {
        "label": "Trung bình",
        "confidence": 70,
        "alignment": 67,
        "risk_multiplier": 1.00,
        "position_multiplier": 1.00,
        "allow_watch_buy": False,
    },
    "HIGH": {
        "label": "Cao",
        "confidence": 62,
        "alignment": 55,
        "risk_multiplier": 1.25,
        "position_multiplier": 1.15,
        "allow_watch_buy": True,
    },
}


def normalize_risk_profile(value: str | None) -> str:
    profile = str(value or "MEDIUM").strip().upper()
    if profile not in RISK_PROFILES:
        raise ValueError("Mức quản trị rủi ro hợp lệ: LOW, MEDIUM hoặc HIGH.")
    return profile


def risk_profile(value: str | None) -> dict:
    return RISK_PROFILES[normalize_risk_profile(value)]
