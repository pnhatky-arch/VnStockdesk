#!/bin/bash
set -e
cd "$(dirname "$0")"

RUNTIME_DIR="${VNSTOCKDESK_RUNTIME_DIR:-$HOME/Library/Application Support/VnStockDesk/runtime}"
if [ ! -f "$RUNTIME_DIR/.venv/bin/activate" ]; then
  echo "Chưa cài môi trường. Chạy INSTALL.command trước."
  exit 1
fi

source "$RUNTIME_DIR/.venv/bin/activate"
python rebuild_history.py
