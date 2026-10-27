# VnStockDesk trên Google Drive

Đây là thư mục làm việc chính được đồng bộ qua Google Drive.

- `System/`: mã nguồn, giao diện, thuật toán và launcher.
- `Data/market/`: dữ liệu thị trường có thể tải/cập nhật lại.
- `Data/private/`: danh mục, Paper account và trạng thái ứng dụng được đồng bộ. Không chạy BOT đồng thời trên hai máy.
- Python `.venv`, log, PID và `.env` là dữ liệu cục bộ, không đồng bộ giữa các hệ điều hành.

## Runtime cục bộ

- macOS: `~/Library/Application Support/VnStockDesk/runtime/.venv`
- Windows: `%LOCALAPPDATA%\VnStockDesk\runtime\.venv`
- Có thể đổi bằng biến môi trường `VNSTOCKDESK_RUNTIME_DIR`.

Trên mỗi máy mới, chạy `System/INSTALL.command` (macOS) hoặc `System/INSTALL_WINDOWS.ps1` (Windows) một lần. Sau đó dùng launcher trong `System/`.

## Quy tắc đồng bộ

Chờ Google Drive báo đồng bộ hoàn tất trước khi mở dự án trên máy khác. Chỉ chạy dashboard/BOT ghi dữ liệu trên một máy tại một thời điểm để tránh xung đột tệp. iPhone dùng giao diện web qua Cloudflare, không chạy Python trực tiếp.
