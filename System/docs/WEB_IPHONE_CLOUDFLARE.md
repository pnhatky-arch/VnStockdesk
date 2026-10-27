# Web, iPhone và Cloudflare

## Kiến trúc đã chọn

- Windows 24/7 chạy Python, Streamlit, BOT, quét dữ liệu và giữ `Data`.
- Cloudflare Tunnel ánh xạ tên miền HTTPS đến `http://127.0.0.1:8503` mà không mở cổng vào router.
- Cloudflare Access kiểm soát người được đăng nhập.
- iPhone mở tên miền bằng Safari, chọn **Chia sẻ → Thêm vào Màn hình chính** để có biểu tượng chạy như web app toàn màn hình.

Cloudflare không biến ứng dụng Python/Streamlit này thành một website tĩnh. Nếu máy Windows tắt, mất mạng hoặc dịch vụ dashboard dừng thì iPhone không nhận dữ liệu và BOT cũng không chạy.

## Không triển khai nhầm thành website tĩnh

Không upload `System/assets/desk_grid`, riêng thư mục `System`, hoặc gói ZIP lên Cloudflare Workers/Pages để chạy trực tiếp. `assets/desk_grid` chỉ là thành phần bảng được dashboard nhúng vào; nếu trang chỉ hiện bảng trống hoặc mã HTML có `grid.js` thì đã chọn sai thư mục triển khai. Workers/Pages không chạy được backend Python, Streamlit, BOT và dữ liệu của dự án.

Địa chỉ công khai đúng phải đi qua **Cloudflare Tunnel → Published application route → `http://127.0.0.1:8503`** trên máy Windows. Streamlit cần cả trang chính và các đường dẫn `/_stcore/*`; không thay thế chúng bằng static assets hoặc Worker tĩnh.

## Cài trên Windows

1. Chạy `INSTALL_WINDOWS.ps1`, sau đó xác nhận `START_VnStockDesk.cmd` mở được dashboard.
2. Trong Cloudflare Zero Trust, tạo Tunnel `VnStockDesk-Windows` và Published application route. Service URL là `http://127.0.0.1:8503`.
3. Tạo Access application cho đúng hostname trước khi công khai; chỉ Allow email/tài khoản của chủ sở hữu.
4. PowerShell (Administrator): `./INSTALL_CLOUDFLARE_WINDOWS.ps1 -TunnelToken "TOKEN_DO_CLOUDFLARE_CAP"`.
5. Trong Windows Task Scheduler hoặc Startup, chạy `START_VnStockDesk.cmd` khi đăng nhập. `cloudflared` đã chạy dạng Windows Service.

Sau khi cấu hình, kiểm tra bằng `python verify_cloudflare.py https://TEN-MIEN-CUA-BAN` hoặc nhấp đúp `VERIFY_CLOUDFLARE.command` trên macOS. Kết quả chỉ hợp lệ khi trang chính là Streamlit và `/_stcore/health` trả về `ok`.

Không ghi tunnel token, khóa API, mật khẩu hay file `Data/private` vào ZIP/Git/Cloudflare. `cloudflare.example.yml` chỉ là mẫu không chứa bí mật.

## Giới hạn cài như ứng dụng iPhone

Đây là web app cài từ Safari, không phải ứng dụng native ký và phát hành qua App Store. Giao diện hiện tại vẫn dùng một mã nguồn Streamlit cho Desktop/iPhone; BOT chỉ có một tiến trình phía Windows, tránh đặt lệnh trùng.
