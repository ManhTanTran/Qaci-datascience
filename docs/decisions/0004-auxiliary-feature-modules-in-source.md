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

Ranh giới mới lấy **tính tái sử dụng** làm tiêu chí, không lấy dataset: hàm nào
dùng lại được thì thuộc source và phải có test, kể cả khi nó gắn cứng với một
dataset. Notebook giữ phần dùng một lần — đọc dữ liệu, EDA, chọn cấu hình
experiment và diễn giải kết quả. Feature trong source vẫn là research candidate
cho tới khi được promote theo quy trình production.

Quyết định này kèm một quy ước lưu trữ: **feature đã tính lưu thành Parquet qua
`credit_scoring.feature_store`**, không phải CSV. Lý do là Parquet giữ nguyên
dtype và `NaN`, nhỏ hơn khoảng ba lần và đọc nhanh hơn khoảng hai mươi lần; đo
trên block bureau thật cho 27,5 MB và 0,31 giây, so với 83,2 MB và 5,84 giây.

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
- [x] Cập nhật `AGENTS.md` theo ranh giới mới.
- [x] Feature đã tính lưu Parquet kèm manifest, không lưu CSV.
- [ ] Thông báo cho mentor khi review; quyết định do repo owner chấp thuận.

## Tài liệu liên quan

- [Decision index](README.md)
- [0001 Project structure](0001-project-structure.md)
- [Home Credit Bureau features](../features/home_credit_bureau_features.md)
- [Feature engineering](../features/feature_engineering.md)

## Trạng thái áp dụng trong project

Accepted ngày 2026-08-06 bởi repo owner. `AGENTS.md` đã cập nhật theo ranh giới
này, gồm cả yêu cầu về schema ổn định, missing khác zero, cardinality, nhãn family
và quy ước lưu Parquet. Chưa đưa ra thảo luận với mentor FPT.
TODO(FPT): cần xác nhận với mentor hoặc data owner khi review.
