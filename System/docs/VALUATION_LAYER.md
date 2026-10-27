# Lớp Định giá cổ phiếu — phiên bản 1

## Vị trí và phạm vi

- Dashboard: **Định giá cổ phiếu** giữa Tin tức và Chiến lược; dùng chung Paper/Live, Light/Dark và 5 ngôn ngữ.
- Nút Cập nhật định giá tải lại mã đang chọn. Kiểm tra dữ liệu ở Control Center cũng kiểm tra định giá mã đó.
- Quét thị trường: pha định giá riêng sau kỹ thuật/tin tức, áp dụng tất cả mã phân tích thành công của phạm vi đã chọn. Kết quả cũ chưa có cột mới cho đến lần quét tiếp theo.
- Phân tích danh mục cơ sở: thêm chỉ số, chất lượng dữ liệu và kết luận riêng từng mã.
- AI nhận ngữ cảnh chỉ số, nguồn/kỳ, cảnh báo và kết luận; không gửi cả lịch sử báo cáo.
- Không dùng P/E, P/B cho hợp đồng phái sinh. Không thay đổi hành động BOT, điểm kỹ thuật, confidence, Entry, Stop hay TP.

## Nguồn và đơn vị

Adapter cô lập trong tiến trình con, timeout 75 giây. Ưu tiên KBS qua vnstock Finance; VCI dự phòng. Bản VCI cài hiện tại trả những kỳ cũ ở lời gọi ratio mặc định; bộ kiểm tra độ mới sẽ vô hiệu kết luận, không coi lần tải mới là kỳ mới.

P/E, P/B là số liệu theo kỳ nguồn cung cấp, **không tính lại theo giá realtime**. EPS và BVPS từ KBS tính bằng VND; ROE giữ nguyên % theo kỳ nguồn, không tự annualize. Tăng trưởng lợi nhuận chỉ nhận hàng có nhãn rõ và đơn vị %, không mặc định YoY. Debt/Equity dạng % được chia 100 thành lần; không áp ngưỡng nợ chung cho ngân hàng và doanh nghiệp công nghiệp.

Giữ tối đa 8 kỳ; lần tải KBS hiện tại lấy 4 kỳ (hiện tại + 3 kỳ so sánh). Adapter lấy từng kỳ mỗi trang theo cảnh báo lỗi trộn giá trị khi page_size>1 ngay trong thư viện KBS; vẫn gọi public ratio và giữ các wrapper hạn mức. Không sửa thư viện cài đặt. Nếu còn kỳ mơ hồ, vô hiệu kết luận thay vì chỉ loại cột và coi dữ liệu là đúng. Không điền dữ liệu thiếu bằng 0. So sánh lịch sử có thể chịu ảnh hưởng thay đổi vốn, cơ cấu tài sản và cách nhà cung cấp tính chỉ số; chưa điều chỉnh các yếu tố này.

Tài liệu nguồn: https://vnstocks.com/docs/vnstock/phan-tich-co-ban-fundamental

## Cache và so sánh

- `data/valuation/<SYMBOL>.json`: ghi atomic, TTL 24 giờ, retry lỗi sau 15 phút; nút cập nhật cho phép thử ngay.
- Lỗi nguồn giữ bản thành công trước đó cùng timestamp gốc. Không dùng dữ liệu lỗi/không cập nhật để kết luận thấp tương đối.
- Kỳ quá 200 ngày, trong tương lai, hoặc cache quá 2 ngày: không đủ dữ liệu hợp lệ.
- Ngành ICB cấp 3 từ VCI, lưu 7 ngày. Không rõ ngành thì không so sánh ngành.
- Trung vị tối thiểu 3 kỳ trước hiện tại. Mẫu ngành tối thiểu 3 mã khác, cùng ngành, nguồn, kỳ và cache còn hạn. Loại chính mã đang xét, trùng mã, mẫu lỗi và tỷ số không dương.
- Mẫu chỉ gồm mã đã tải, không tuyên bố là trung vị toàn ngành; UI ghi số mẫu và mã tham chiếu.
- Chênh lệch ±20% là ngưỡng mô tả thủ công, **chưa được backtest**; không phải xác suất sinh lời hay giá mục tiêu.
- Âm/0 P/E, EPS, P/B hoặc BVPS: cảnh báo. ROE không dương hoặc lợi nhuận giảm: kết luận kết hợp yêu cầu rà soát rủi ro, không được nâng thành tín hiệu mua.

Quét lớn lần đầu có thể chậm vì hạn mức nguồn. Có cache từng mã; không cần tải lại tài chính ở mỗi tick giá. Không quét toàn thị trường tự động chỉ vì mở dashboard.

### Hoàn thiện bộ tải và cảnh báo

- Bộ phân trang lấy một kỳ/trang và tiếp tục bỏ qua kỳ trùng, tối đa 12 trang để tìm 4 kỳ khác nhau. Giữ nguyên cặp nhãn kỳ/giá trị từ nguồn; không tự đổi nhãn, không sửa thư viện hoặc bỏ wrapper hạn mức. Chưa đủ 3 kỳ quá khứ vẫn cảnh báo.
- Bản cache dùng bộ tải cũ tự được nâng cấp ở lần xem tiếp theo. Nếu tải mới lỗi, giữ dữ liệu cũ và timestamp gốc kèm cảnh báo; không coi đó là cập nhật thành công.
- Khi mở một mã, tự bổ sung mẫu ICB cấp 3 theo thứ tự mã, dừng khi đủ ít nhất 3 mẫu hợp lệ cho cả P/E và P/B. Tối đa 5 mã bổ sung mỗi lần, ngừng bắt đầu yêu cầu mới sau 90 giây; yêu cầu đang chạy vẫn chịu timeout tiến trình 75 giây. Không tải đệ quy mẫu ngành của các mã bổ sung.
- Ưu tiên tái sử dụng cache hợp lệ. Mã lỗi có backoff 15 phút. Mẫu khác kỳ/nguồn, thiếu chỉ số hoặc vốn chủ/lợi nhuận không dương không được tính để lấp đủ mẫu.
- Đây là mẫu có giới hạn, chọn theo mã chứ không đại diện toàn ngành. UI luôn ghi số mẫu và các mã thực tế. Ngưỡng 3 mẫu và 3 kỳ không hạ thấp.
- Cảnh báo nêu đúng ROE, tăng trưởng lợi nhuận hay Debt/Equity còn thiếu. Không còn thông báo gộp khiến người dùng hiểu nhầm thiếu cả ba. Không tự đặt giá trị 0 cho Debt/Equity ngân hàng.
- Toast và các hộp thông báo dùng nền/chữ theo theme ứng dụng kể cả khi được render ngoài `.stApp`; viền hộp info/success/error/warning giữ màu phân biệt.

## Kiểm tra

`python -m unittest discover -s tests -q`

`streamlit run tests/preview_valuation.py --server.port 8505`

Trang preview dùng dữ liệu giả lập, không chạm lệnh, tài khoản hoặc BOT. Kiểm tra parser, dữ liệu cũ/tương lai, EPS/vốn chủ âm, thiếu ngành/lịch sử, peer cùng kỳ, cache lỗi, ngôn ngữ và tính bất biến của quyết định kỹ thuật.
