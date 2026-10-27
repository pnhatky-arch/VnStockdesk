#!/bin/bash
cd "$(dirname "$0")" || exit 1
RUNTIME_DIR="${VNSTOCKDESK_RUNTIME_DIR:-$HOME/Library/Application Support/VnStockDesk/runtime}"
source "$RUNTIME_DIR/.venv/bin/activate"
python scan.py --scope ALL
