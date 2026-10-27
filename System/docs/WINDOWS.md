# Chạy VnStockDesk trên Windows

1. Giữ `System` và `Data` cạnh nhau trong thư mục `VnStockDesk`.
2. Mở PowerShell trong `System`, chạy `Set-ExecutionPolicy -Scope Process Bypass`, rồi `./INSTALL_WINDOWS.ps1`.
3. Nhấp đúp `START_VnStockDesk.cmd`. Dùng `STOP_VnStockDesk.cmd` để dừng đúng tiến trình launcher quản lý.

BOT, dữ liệu và tài khoản đều dùng `../Data`; gói cập nhật `System` không ghi đè dữ liệu riêng. Windows phải luôn bật và có Internet nếu dùng Cloudflare Tunnel để truy cập từ iPhone.
