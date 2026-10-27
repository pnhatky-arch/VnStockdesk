from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from .paths import ENV_FILE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ENV = ENV_FILE

# Known locations from prior local projects. We do not print secret values.
CANDIDATE_ENV_FILES = [
    PROJECT_ENV,
    PROJECT_ROOT.parent / "Data" / "private" / ".env",  # migration fallback
    Path.home() / "stock-ai" / ".env",
    Path.home() / "vn100-wyckoff" / ".env",
    Path.home() / "vn100-market-system" / ".env",
    Path.home() / "Downloads" / "VN100_ANALYSIS_SYSTEM" / ".env",
    Path.home() / "Downloads" / "VN100_ANALYSIS_SYSTEM_FIXED" / ".env",
    Path.home() / "Downloads" / "VN100_ANALYSIS_SYSTEM_KEYED" / ".env",
]


def _read_key_from_env_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            if key.strip() != "VNSTOCK_API_KEY":
                continue

            value = value.strip().strip('"').strip("'")
            if value.startswith("vnstock_") and len(value) > 20:
                return value
    except Exception:
        return None

    return None


def _write_project_env(key: str) -> None:
    # Preserve any existing non-VNStock settings.
    existing_lines = []
    if PROJECT_ENV.exists():
        try:
            existing_lines = PROJECT_ENV.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()
        except Exception:
            existing_lines = []

    kept = [
        line
        for line in existing_lines
        if not line.strip().startswith("VNSTOCK_API_KEY=")
    ]
    kept.append(f"VNSTOCK_API_KEY={key}")

    PROJECT_ENV.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_ENV.write_text(
        "\n".join(kept).rstrip() + "\n",
        encoding="utf-8",
    )

    try:
        os.chmod(PROJECT_ENV, 0o600)
    except Exception:
        pass


def ensure_vnstock_key() -> dict:
    """
    Load VNSTOCK_API_KEY before any vnstock import.

    Search order:
    1) Current process environment
    2) Project .env
    3) Known prior project .env files

    If found outside this project, copy it silently into this project's .env.
    Secret is never printed.
    """

    # Load local .env first if it exists.
    if PROJECT_ENV.exists():
        load_dotenv(PROJECT_ENV, override=False)

    key = os.getenv("VNSTOCK_API_KEY", "").strip()

    if key.startswith("vnstock_") and len(key) > 20:
        return {
            "loaded": True,
            "source": "environment/project .env",
            "tier_hint": "COMMUNITY_OR_HIGHER",
        }

    for path in CANDIDATE_ENV_FILES:
        candidate = _read_key_from_env_file(path)
        if candidate:
            os.environ["VNSTOCK_API_KEY"] = candidate

            if path.resolve() != PROJECT_ENV.resolve():
                _write_project_env(candidate)

            return {
                "loaded": True,
                "source": str(path),
                "tier_hint": "COMMUNITY_OR_HIGHER",
            }

    return {
        "loaded": False,
        "source": None,
        "tier_hint": "GUEST",
    }


# Execute immediately on import.
KEY_STATUS = ensure_vnstock_key()
