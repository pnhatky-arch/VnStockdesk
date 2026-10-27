#!/bin/bash
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
RUNTIME_DIR="${VNSTOCKDESK_RUNTIME_DIR:-$HOME/Library/Application Support/VnStockDesk/runtime}"

if [ ! -d "$RUNTIME_DIR/.venv" ]; then
  mkdir -p "$RUNTIME_DIR"
  "$PYTHON" -m venv "$RUNTIME_DIR/.venv"
fi

source "$RUNTIME_DIR/.venv/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "=== AUTO-IMPORT VNSTOCK KEY ==="
python - <<'PY'
from src.bootstrap import KEY_STATUS
if KEY_STATUS["loaded"]:
    print("VNSTOCK_API_KEY: LOADED")
    print("Source:", KEY_STATUS["source"])
else:
    print("VNSTOCK_API_KEY: NOT FOUND")
    print("System will use Guest throttle until a key is available.")
PY

echo
python doctor.py

echo
echo "INSTALL COMPLETE"
read -n 1 -s -r -p "Press any key to close..."
echo
