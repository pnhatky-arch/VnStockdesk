"""Persistent user preferences for dashboard push notifications."""
from __future__ import annotations

import json
from pathlib import Path

from .local_io import atomic_json, file_lock
from .paths import STATE_DIR


def _settings_path() -> Path:
    return STATE_DIR / "alert_preferences.json"


def _sound_dir() -> Path:
    return STATE_DIR / "alert_audio"


def load_alert_preferences() -> dict:
    try:
        value = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    return {"push_enabled": bool(value.get("push_enabled", True))}


def set_push_enabled(enabled: bool) -> None:
    path = _settings_path()
    with file_lock(path.with_suffix(".lock"), wait_seconds=2):
        atomic_json(path, {"push_enabled": bool(enabled)})


def selected_alert_sound() -> tuple[Path | None, str]:
    sound_dir = _sound_dir()
    try:
        config = json.loads((sound_dir / "config.json").read_text(encoding="utf-8"))
        sound_path = sound_dir / str(config["file"])
        if sound_path.is_file():
            return sound_path, str(config.get("name") or sound_path.name)
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None, "Bốn kênh"


def save_alert_sound(name: str, payload: bytes, max_bytes: int = 5 * 1024 * 1024) -> bool:
    if len(payload) > max_bytes:
        return False
    suffix = Path(name).suffix.lower()
    if suffix not in {".mp3", ".wav", ".m4a", ".ogg"}:
        raise ValueError("Định dạng âm thanh không được hỗ trợ.")
    sound_dir = _sound_dir()
    sound_dir.mkdir(parents=True, exist_ok=True)
    target = sound_dir / f"custom_alert{suffix}"
    for old_sound in sound_dir.glob("custom_alert.*"):
        if old_sound != target:
            old_sound.unlink(missing_ok=True)
    if not target.exists() or target.read_bytes() != payload:
        target.write_bytes(payload)
    atomic_json(sound_dir / "config.json", {"file": target.name, "name": Path(name).name})
    return True


def reset_alert_sound() -> None:
    sound_dir = _sound_dir()
    for old_sound in sound_dir.glob("custom_alert.*"):
        old_sound.unlink(missing_ok=True)
    (sound_dir / "config.json").unlink(missing_ok=True)
