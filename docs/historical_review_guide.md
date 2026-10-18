# Hướng dẫn review thủ công Phase E5

Hai CSV E5 là phiếu gắn nhãn thủ công cho dữ liệu lịch sử TiniX. Các cột bắt đầu
bằng `e4_` hoặc `rule_` là kết quả baseline đã đóng băng; không sửa chúng. Chỉ
điền nhãn, trạng thái review và ghi chú của người review. Để trống nếu cần bỏ qua.

## Review loại giao dịch

Trong `tinix-e5-title-review.csv`, điền `human_label`, `reviewer_notes` và đặt
`review_status=REVIEWED` sau khi đã tự đọc tiêu đề. Nếu chưa review, giữ nhãn trống
và `review_status=NOT_REVIEWED`.

- `SALE`: tiêu đề nói rõ đang bán hoặc chuyển nhượng, không có dấu hiệu cho thuê
  xung đột. Ví dụ giả định: “Chính chủ bán căn hộ hai phòng ngủ”.
- `RENT`: tiêu đề nói rõ đang cho thuê, không có dấu hiệu bán xung đột. Ví dụ giả
  định: “Cho thuê nhà nguyên căn gần trường học”.
- `AMBIGUOUS`: có tín hiệu nhưng cách viết không đủ rõ để kết luận loại giao dịch.
  Ví dụ giả định: “Nhà khu trung tâm, giá tốt, liên hệ để biết thêm”.
- `CONFLICT`: cùng tiêu đề nêu những khẳng định giao dịch loại trừ nhau hoặc có
  mâu thuẫn trực tiếp. Ví dụ giả định: “Bán hoặc cho thuê căn hộ”.
- `INSUFFICIENT_INFORMATION`: tiêu đề thiếu thông tin để xác định giao dịch;
  không suy ra từ giá, loại tài sản hay tên địa điểm. Ví dụ giả định: “Căn hộ
  đường A, 70 m²”.

Các câu trong hướng dẫn chỉ là ví dụ giả định, không phải dữ liệu được gắn nhãn.
Không dùng Gemini hoặc dự đoán E4 làm nhãn con người. Nếu tiêu đề có cả dấu hiệu
bán và thuê, phân biệt `CONFLICT` (cả hai được nêu rõ) với `AMBIGUOUS` (cách viết
không xác định được ý định). Dùng `INSUFFICIENT_INFORMATION` khi không có bằng
chứng giao dịch đủ dùng.

100 dòng được lấy cân bằng theo dự đoán E4, 25 dòng cho mỗi nhóm
`SALE_CONFIRMED_BY_TEXT`, `RENT_CONFIRMED_BY_TEXT`, `AMBIGUOUS`, `CONFLICT`.
Đây không phải mẫu ngẫu nhiên đại diện cho 1.190 candidate. Kết quả chỉ mô tả tập
review và không được diễn giải thành độ chính xác toàn bộ dữ liệu hay production.

## Review loại bất động sản

Trong `tinix-e5-property-review.csv`, điền `human_property_label`, ghi chú nếu có
và đặt `review_status=REVIEWED`:

- `DAT_O`: nội dung rao mô tả đất ở.
- `NHA_RIENG`: nhà riêng/nhà ở gắn liền với đất.
- `CHUNG_CU`: căn hộ/chung cư.
- `OTHER`: loại khác hoặc mục đích hỗn hợp không thuộc ba nhóm trên.
- `UNKNOWN`: tiêu đề và trường dữ liệu không đủ thông tin để phân loại.

Nhãn `DAT_O` chỉ mô tả nội dung lời rao. Cụm từ “đất thổ cư” không chứng minh hồ
sơ pháp lý, mục đích sử dụng đất hoặc hiện trạng tại nguồn. Review tiêu đề không
xác minh trang tin gốc; cột `evidence_status` vẫn là
`HISTORICAL_DATASET_UNVERIFIED`. Cột URL trong phiếu là trang dataset, không phải
URL tin đăng.

## Lưu và kiểm tra CSV

Giữ nguyên `source_row_id` để ghép nhãn với đúng dòng. Nếu dùng Excel, mở CSV với
mã hóa UTF-8 và lưu lại dưới dạng CSV UTF-8. Không xóa hoặc sắp xếp riêng một số
cột làm lệch các hàng. Trạng thái nhãn phải nhất quán:

- Dòng đã review: nhãn hợp lệ và `review_status=REVIEWED`.
- Dòng chưa review/bỏ qua: nhãn trống và `review_status=NOT_REVIEWED`.

Sau khi lưu, chạy lệnh kiểm tra từ README. Bộ kiểm tra chỉ xác thực cấu trúc và
nhãn; nó không ghi vào SQLite, không xác minh nguồn và không tính metric khi chưa
có nhãn độc lập.
