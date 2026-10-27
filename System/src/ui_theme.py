"""Shared iOS-inspired presentation tokens for PAPER and LIVE.

No broker, quote, or session state belongs here. Solid content surfaces keep
financial data legible; translucent materials are reserved for navigation.
"""
from pathlib import Path

FONT_STACK = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif'

PALETTES = {
    "light": {
        "bg": "#f2f2f7", "panel": "#ffffff", "panel2": "#f5f5f9",
        "panel3": "#e9e9ef", "border": "#dcdce4", "text": "#1c1c1e",
        "muted": "#62626b", "blue": "#005ac1", "green": "#18743b",
        "red": "#c62b32", "purple": "#763ac1", "amber": "#855400", "orange": "#a34400",
        "glass": "#f7f7fa", "shadow": "0 1px 2px rgba(25,25,45,.045)",
        "grid": "#e9e9ef", "tab-accent": "#d9303e",
    },
    "dark": {
        "bg": "#101012", "panel": "#1c1c1e", "panel2": "#242426",
        "panel3": "#323236", "border": "#3a3a40", "text": "#f5f5f7",
        "muted": "#b0b0ba", "blue": "#79b8ff", "green": "#61d88b",
        "red": "#ff8585", "purple": "#c7a1ff", "amber": "#f2c66d", "orange": "#ffac6b",
        "glass": "#18181b", "shadow": "0 1px 2px rgba(0,0,0,.28)",
        "grid": "#2d2d31", "tab-accent": "#ff5964",
    },
}


def palette(light: bool) -> dict[str, str]:
    return dict(PALETTES["light" if light else "dark"])


def stylesheet(light: bool) -> str:
    tokens = palette(light)
    variables = ";".join(f"--{key}:{value}" for key, value in tokens.items())
    css = (Path(__file__).resolve().parent.parent / "assets" / "ios_theme.css").read_text(encoding="utf-8")
    return f"<style>:root{{{variables};color-scheme:{'light' if light else 'dark'}}}</style><style>{css}</style>"


def signal_colors(light: bool) -> dict[str, str]:
    p = palette(light)
    return {
        **dict.fromkeys(("STRONG_BUY", "BUY", "WATCH_BUY"), p["green"]),
        "HOLD": p["blue"], "WATCH": p["muted"],
        "REDUCE": p["amber"], "AVOID": p["amber"],
        "SELL": p["red"], "STRONG_SELL": p["red"],
    }
