#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
RUNTIME_DIR="${VNSTOCKDESK_RUNTIME_DIR:-$HOME/Library/Application Support/VnStockDesk/runtime}"
PYTHON="$RUNTIME_DIR/.venv/bin/python"
"$PYTHON" - <<'PY'
from pathlib import Path
from src.bot_manager import cleanup_legacy_bot_workers
stopped = cleanup_legacy_bot_workers(Path.cwd())
print("Đã dừng tiến trình BOT cũ:", ", ".join(map(str, stopped)) if stopped else "không có")
PY
echo "Có thể đóng cửa sổ này."
