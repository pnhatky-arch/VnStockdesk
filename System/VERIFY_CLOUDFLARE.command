#!/bin/bash
set -u
cd "$(dirname "$0")"

RUNTIME_DIR="${VNSTOCKDESK_RUNTIME_DIR:-$HOME/Library/Application Support/VnStockDesk/runtime}"
PYTHON="$RUNTIME_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

PUBLIC_URL="${1:-https://vnstockdesk.p-nhatky.workers.dev}"
"$PYTHON" verify_cloudflare.py "$PUBLIC_URL"
RESULT=$?
echo
if [ "$RESULT" -ne 0 ]; then
  echo "Hãy sửa Published application route của Cloudflare Tunnel về http://127.0.0.1:8503."
fi
read -n 1 -s -r -p "Nhấn phím bất kỳ để đóng..."
echo
exit "$RESULT"
