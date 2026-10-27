# VnStockDesk

Hướng dẫn nền tảng: [Windows](docs/WINDOWS.md) · [Web/iPhone qua Cloudflare](docs/WEB_IPHONE_CLOUDFLARE.md).

Tên sản phẩm: **VnStockDesk**. Dự án được tách thành hai thư mục con:

- `System/`: mã nguồn, giao diện và thuật toán — đây là nơi duy nhất cần chỉnh sửa và đóng gói triển khai.
- `Data/`: `market/` chứa dữ liệu tải về, `private/` chứa tài khoản/cấu hình riêng. Python runtime và khóa API được giữ cục bộ trên từng máy, không đồng bộ qua Google Drive.

Không upload `Data/` lên Cloudflare hoặc kho mã nguồn. Tài khoản, danh mục và `.env` phải được sao lưu riêng.
Mở bằng `START VnStockDesk.app`, dừng bằng `STOP VnStockDesk.app`;
`VnStockDesk.webloc` mở dashboard tại cổng 8503.
Launcher tự tìm thư mục chứa nó và dùng runtime cục bộ tại
`~/Library/Application Support/VnStockDesk/runtime` trên macOS hoặc
`%LOCALAPPDATA%\VnStockDesk\runtime` trên Windows.

Sau khi đổi tên, hãy STOP rồi START để tiến trình mới nhận tên/đường dẫn mới.
Đường dẫn thư mục cũ chỉ còn là liên kết tương thích cho phiên đang chạy,
không phải một bản sao dự án. Dữ liệu, tài khoản, danh mục và các tên rổ
VN30/VN100 không thay đổi.

Hệ thống phân tích cổ phiếu Việt Nam trên HOSE, HNX, UPCOM hoặc riêng rổ VN30/VN100 theo 4 khung:

Mặc định dữ liệu OHLCV sử dụng cửa sổ 8 năm trượt, phù hợp giới hạn Vnstock Community.

Rổ `Yêu thích` do người dùng tự tạo bằng nút ☆/★ trên dashboard, được lưu bền
trong `../Data/private/user_watchlist.json` và có thể chạy scanner riêng với `--scope FAVORITES`.

- 1D: mỗi nến là 1 ngày
- 1W: mỗi nến là 1 tuần
- 1M: mỗi nến là 1 tháng
- 1Y: mỗi nến là 1 năm

Khung nến được chọn trên dashboard; danh mục cơ sở có MULTI/1D/1W/1M/1Y,
danh mục và biểu đồ phái sinh thêm 15M/1H. Không có 1Q.
Khung danh mục xuất riêng Signal/Score và số nến của khung được chọn;
System Action và Entry/Stop/TP tổng hợp đa khung vẫn được ghi tách biệt.
Chọn khung trong form chỉ có hiệu lực cho lần bấm chạy phân tích kế tiếp.
Chu kỳ BOT 15/30/60 phút là lịch quét, không phải khung phân tích hay độ dài nến.

Nến tuần/tháng/năm được gộp từ OHLCV ngày có thực: Open đầu kỳ, High cao nhất,
Low thấp nhất, Close cuối kỳ, tổng Volume. Dữ liệu được sắp xếp, loại trùng thời
điểm trước khi gộp; không điền thêm kỳ không có dữ liệu. `time` là phiên cuối có
dữ liệu, `period_end` là mốc kết thúc lịch, `source_bars` là số nến nguồn.
Kỳ đầu/cuối có thể chưa trọn kỳ. Cửa sổ 8 năm trượt có thể giao với 9 năm lịch,
không đồng nghĩa có 9 năm đầy đủ; thường chưa đủ MA20/RSI14 trên nến năm.
Phái sinh chỉ dùng lịch sử hợp đồng do nguồn trả về, không tự ghép hợp đồng khác
để tạo đủ nến năm. Báo thiếu lịch sử thay vì dùng nến ngày giả danh nến năm.

Mỗi khung chạy độc lập:

- Wyckoff: cấu trúc/range, Spring, SOS, LPS, UT, SOW và phase tổng quát
- MA20 / MA50 / MA100 / MA200 + slope/alignment
- RSI14
- Volume / Relative Volume
- Support / Resistance
- Tín hiệu BUY / WATCH / HOLD / REDUCE / SELL
- Signal score liên tục từ -100 đến +100, confidence và độ đồng thuận đa khung
- ATR14 / ATR% / ROC20 / biến động chuẩn hoá
- Tin tức doanh nghiệp theo từng mã từ KBS/VCI, cập nhật ít nhất mỗi ngày
- Điểm tác động tin tức 30 ngày và điểm tổng hợp kỹ thuật + tin
- Quyết định tự động đa khung và kế hoạch entry / stop / target tham khảo

## Cài

Trên macOS, nhấp đúp `INSTALL.command`. Trên Windows, chạy
`INSTALL_WINDOWS.ps1`; bộ cài tự tạo runtime cục bộ đúng hệ điều hành.

Khóa được lưu trong vùng cấu hình cục bộ của máy, không đưa lên Google Drive.
Có thể nhập khóa từ dashboard. Nếu cấu hình thủ công, dùng `.env` tại
`~/Library/Application Support/VnStockDesk/private/` trên macOS. Nếu dùng API key Vnstock, điền:

```text
VNSTOCK_API_KEY=...
```

AI Analyst luôn có chế độ nội bộ không cần khóa. Để bật AI Online, lưu khóa
trong `Dữ liệu, API & Yêu thích` trên dashboard hoặc thêm vào `.env`:

```text
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.4
```

AI Online chỉ gửi câu hỏi và context phân tích rút gọn của mã đang xem, không
gửi toàn bộ lịch sử OHLCV. Nếu API lỗi hoặc chưa có khóa, hệ thống tự chuyển về
AI Nội bộ và không làm gián đoạn dashboard.

## Kiểm tra hệ thống

```bash
python doctor.py
python -m unittest discover -v
python tests/test_offline_pipeline.py
```

Doctor bắt buộc phải báo universe > 0 và fetch được ít nhất một mã. Bộ `unittest`
kiểm tra riêng các hàng rào an toàn của bot: PAPER-only, sizing theo rủi ro,
stop-loss, khóa lỗ ngày, dữ liệu tài khoản lỗi và cổng LIVE bị khóa.

## Quét VN100

```bash
python scan.py
```

Kiểm thử nhanh hoặc buộc dựng lại dữ liệu:

```bash
python scan.py --limit 5
python scan.py --refresh
```

Quét theo sàn hoặc toàn thị trường:

```bash
python scan.py --scope HOSE
python scan.py --scope VN30
python scan.py --scope HNX
python scan.py --scope UPCOM
python scan.py --scope ALL
```

Scanner chỉ giữ `STOCK` đang giao dịch; tự loại chứng quyền, trái phiếu, ETF,
hợp đồng tương lai và mã hủy niêm yết. Lượt quét ghi checkpoint mỗi 10 mã và
tự tiếp tục khi chạy lại. Các phạm vi có file kết quả riêng trong `../Data/market/processed`.

Output:
- `../Data/market/processed/vn100_scan.csv`
- `../Data/market/processed/vn100_scan_errors.csv`
- `../Data/market/processed/vn100_scan_meta.json`

Mỗi lượt scan cập nhật tin theo mã nếu cache chưa được làm mới trong ngày. Kết quả gồm
`news_score`, `news_sentiment`, `news_count_30d`, `news_adjusted_score`,
`news_updated_at` và `news_status`.

## Dashboard

```bash
streamlit run app.py
```

Dashboard có:
- Mục `TẢI VỀ DATA`: khởi tạo thư mục dữ liệu, tải mới, bổ sung thiếu, cập nhật, tạm dừng/tiếp tục và theo dõi checkpoint
- Chuyển đổi đồng bộ giao diện tối/sáng ngay trong Control Center
- Bộ chọn ngôn ngữ có cờ: Tiếng Việt, English, 中文, Русский và Deutsch;
  branding, điều khiển, KPI, biểu đồ và các tab chính đổi theo ngôn ngữ đang chọn
- Giao diện macOS mới: SF system font, sidebar/topbar vật liệu kính tiết chế,
  content card rõ lớp, control tối thiểu 32 px và bố cục thích ứng cửa sổ
- Market Overview
- VN100 Scanner
- Stock Detail
- Candlestick + MA
- Volume
- RSI
- Bảng 1D / 1W / 1M / 1Y
- Wyckoff / MA / RSI / Signal từng khung
- TradingView Lightweight Charts: zoom con lăn, kéo để di chuyển, reset khung nhìn
- Cấu trúc Wyckoff 2.0 và các đường Creek / Ice / EQ / Support / Resistance
- Tin tức và sự kiện ảnh hưởng trực tiếp theo mã
- AI Analyst phong cách macOS 27: hội thoại theo mã, câu hỏi gợi ý, context trực
  tiếp, AI Nội bộ luôn sẵn sàng và AI Online qua OpenAI Responses API

Nút `Refresh data` buộc tải lại cả giá và tin tức của mã đang xem. Nếu nguồn tin
tạm lỗi, hệ thống dùng bản cache gần nhất và hiển thị trạng thái rõ ràng.

## Nguyên tắc fail-safe

Nếu không lấy được VN100 universe hoặc không fetch được dữ liệu:
- hệ thống báo `NO DATA`
- không suy diễn BULLISH/BEARISH
- không tạo tín hiệu giả


## Dashboard FULL
- 6 khu vực dữ liệu: đa khung, OHLC/chỉ báo, scanner, Paper Trading, kiểm định và AI Analyst.
- Mỗi khung có OHLC, Volume, MA20/50/100/200, RSI14.
- Chart 4 tầng: Candlestick+MA, Volume, RSI, Wyckoff Structure/Events.
- Wyckoff chart hiển thị Support, Resistance, Range Low/High và event SPRING/SOS/LPS/UT/SOW.
- Bảng lịch sử OHLC theo từng khung để xem giá mở cửa/đóng cửa từng ngày/tuần/tháng/quý/năm.
- Scanner hiển thị market breadth, tuổi dữ liệu, confidence và metadata lần quét.
# Paper Trading và bot tự động

Dashboard có khu vực `PAPER TRADING & BOT` để chạy một chu kỳ mô phỏng hoặc bật bot định kỳ 15/30/60 phút. Bot chỉ mua khi hệ thống trả về `MUA_CÓ_XÁC_NHẬN`, tự tính khối lượng theo rủi ro, quản lý stop/target và giảm/thoát vị thế khi tín hiệu suy yếu.

Chạy một lần từ terminal:

```bash
python market_bot.py --symbol FPT
```

Live Trading được khóa có chủ đích. Muốn kết nối lệnh thật cần viết adapter theo API chính thức của công ty chứng khoán, cấu hình xác thực an toàn và kiểm thử sandbox/UAT trước khi mở khóa.

## VN30F1M Futures Desk và BOT PAPER

Tab `VN30F1M · PHÁI SINH` dùng dữ liệu 15M/1H/1D để lập kế hoạch Long, Short
hoặc đứng ngoài. 1D xác định xu hướng chính, 1H xác nhận cấu trúc và 15M làm
trigger. Dashboard hiển thị hỗ trợ, kháng cự, vùng vào, stop 2–4 điểm, TP1/TP2,
số hợp đồng tối đa, ký quỹ và lỗ ước tính.

BOT Futures có ba cách điều khiển ngay trong tab:

- `START`: chạy nền theo chu kỳ 5/15/30 phút.
- `STOP`: dừng tiến trình BOT Futures.
- `1 CYCLE`: chạy đúng một vòng PAPER để kiểm tra quyết định.

Điều kiện mở vị thế tự động: trong 08:50–11:15 hoặc 13:00–14:15; action là
LONG/SHORT; confidence tối thiểu 70%; alignment tối thiểu 67%; nến 15M cùng
hướng; không có risk flag; sizing lớn hơn 0. BOT ưu tiên stop loss, chốt một
phần tại TP1 rồi dời stop về hòa vốn, đóng phần còn lại tại TP2, thoát khi có
tín hiệu đối nghịch mạnh và đóng toàn bộ từ 14:25.

Giới hạn mặc định: rủi ro 0,5% equity/lệnh, tối đa 30% equity cho ký quỹ mô
hình, khóa lỗ ngày 1,5% và tối đa 3 giao dịch/ngày. Tỷ lệ ký quỹ 17% chỉ là
tham số mô hình; trước khi sử dụng cần đối chiếu VSDC và công ty chứng khoán.
BOT chỉ dùng `state/paper_futures_vn30f1m.json`; LIVE Futures luôn bị khóa.

Chạy một vòng kiểm tra từ terminal:

```bash
python futures_bot.py
```

## PRO Decision V3

Signal engine V3 tách riêng điểm xu hướng khỏi chất lượng bằng chứng. `confidence` kết hợp độ phủ dữ liệu, confidence từng khung, đồng thuận đa khung và độ mạnh điểm; quality gate tiếp tục giới hạn các mã cũ hoặc kém thanh khoản. Kết quả bổ sung hạng bằng chứng A–D, market regime, conflict level và các decision drivers. Hạng bằng chứng không phải xác suất sinh lời và không thay thế backtest/kiểm định ngoài mẫu.

## Chạy không cần Terminal trên macOS

Nhấp đúp `START VnStockDesk.app` trong Finder để chạy dashboard dưới nền và tự mở `http://localhost:8503/`; không cần mở Terminal và có thể đóng cửa sổ Terminal cũ. Launcher kiểm tra cổng 8503 để tránh chạy trùng. Nhấp đúp `STOP VnStockDesk.app` để dừng tiến trình do launcher quản lý. Log nằm tại `state/dashboard.log`. File `VnStockDesk.webloc` dùng để mở lại giao diện khi dịch vụ đã chạy.
