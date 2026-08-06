# ADR-0004: Auxiliary-table feature modules thuộc source

## Mục tiêu

Nới ranh giới source/notebook để feature engineering của các bảng phụ Home Credit
(`bureau`, `previous_application`, `installments_payments`, `credit_card_balance`,
`POS_CASH_balance`) nằm trong `src/credit_scoring/features/` thay vì trong
notebook. Quyết định này thay đổi một quy tắc đang có hiệu lực trong `AGENTS.md`,
nên được ghi lại thay vì áp dụng ngầm.

## Khái niệm chính

Quy tắc cũ đặt mọi feature engineering gắn với dataset vào notebook, với lý do
schema và grain khác nhau ở từng dataset nên trừu tượng hóa sớm sinh ra
abstraction sai. Lý do đó vẫn đúng cho feature một bảng.

Nó không còn đúng cho aggregation nhiều tầng. Năm bảng phụ cần khoảng 1.500 dòng
code, mỗi bảng đi qua hai tầng grain (row → contract → client). Ba tính chất sau
không thể bảo đảm bằng một cell assertion trong notebook:

- **Schema ổn định.** Cột đầu ra phải là hàm của code, không phải của dữ liệu.
  Nếu danh sách cột phụ thuộc vào category nào xuất hiện trong dữ liệu, block ghi
  từ mẫu sẽ không ghép được với block ghi từ full data, mà manifest không phát
  hiện được vì cả hai file đều tự nhất quán.
- **Phân biệt missing với zero.** Tổng amount phải trả `NaN` khi không quan sát
  được giá trị nào, thay vì `0`.
- **Cardinality sau mỗi tầng ghép.** Sai một tầng aggregate làm nhân bản dòng, và
  hậu quả chỉ lộ ra ở metric.

Ba tính chất này cần pytest, tức là cần code nằm trong source.

Ranh giới mới: **aggregation nhiều tầng và feature bảng phụ thuộc source, có
test**; notebook giữ phần đọc dữ liệu, EDA, chọn cấu hình experiment và diễn giải
kết quả. Feature trong source vẫn là research candidate cho tới khi được promote
theo quy trình production.

## Ví dụ trong credit scoring

`BUREAU_AMT_CREDIT_SUM_DEBT_SUM` dùng `sum(min_count=1)`. Một khách hàng không có
bản ghi nợ nào giữ `NaN` thay vì `0`. Nếu để `0`, khách "không có dữ liệu nợ" và
khách "nợ bằng 0" nhập làm một, trong khi rủi ro hai nhóm khác hẳn nhau. Đây là
loại bất biến phải có test chứ không thể kiểm bằng mắt trong notebook.

## Điều cần kiểm tra trong project

- [x] Module aggregate dùng chung có test cho `sum` với `min_count=1`.
- [x] Mỗi builder có test chứng minh schema không đổi khi tập client thay đổi.
- [x] Mỗi builder có test cardinality `SK_ID_CURR` duy nhất.
- [x] Mỗi feature có nhãn family sinh ra từ cùng khai báo tạo ra giá trị.
- [ ] Cập nhật `AGENTS.md` khi quyết định này được xác nhận với mentor.

## Tài liệu liên quan

- [Decision index](README.md)
- [0001 Project structure](0001-project-structure.md)
- [Home Credit Bureau features](../features/home_credit_bureau_features.md)
- [Feature engineering](../features/feature_engineering.md)

## Trạng thái áp dụng trong project

Proposed ngày 2026-08-06. Code đã theo quyết định này; `AGENTS.md` chưa sửa vì
ranh giới source/notebook vừa được merge và cần mentor xác nhận trước khi thay.
TODO(FPT): cần xác nhận với mentor hoặc data owner.
