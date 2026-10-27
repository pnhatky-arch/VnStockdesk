#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
OUT="${TMPDIR:-/tmp}/VnStockDesk-System-$(date +%Y%m%d-%H%M%S).zip"
/usr/bin/zip -qr "$OUT" . -x '*.pyc' '*/__pycache__/*' '.pytest_cache/*' '.DS_Store' '*.log' '.env' '*.app/*'
echo "Đã tạo gói System: $OUT"
echo "Data, tài khoản, runtime và khóa API không nằm trong gói này."
open -R "$OUT" 2>/dev/null || true
