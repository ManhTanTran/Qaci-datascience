# Home Credit application features

## Mục tiêu

Ghi lại feature engineering application-only của baseline E01 và experiment
E02. Cả hai chỉ dùng `application_train.csv` và `application_test.csv`; không
join bảng phụ.

## Khái niệm chính

Các feature được tạo ở application grain, sau bước cleaning sentinel và trước
modeling. Logic tái sử dụng nằm tại
`src/credit_scoring/features/home_credit_application.py`, không chỉ nằm trong
notebook. `safe_divide` trả về `float32`, biến mẫu số bằng 0 hoặc missing thành
`NaN` và không bao giờ trả về infinity.

E01 là đường replay tương thích với notebook đã tạo reference OOF AUC
`0.768696`. E02 bắt đầu từ chính ma trận E01 rồi chỉ thêm hoặc chuẩn hóa các
nhóm application-level sau:

- credit/income: `CREDIT_INCOME_RATIO`, `ANNUITY_INCOME_RATIO`,
  `CREDIT_ANNUITY_RATIO`, `GOODS_CREDIT_RATIO`, `CREDIT_GOODS_DIFF`,
  `INCOME_PER_PERSON`;
- age/employment: `AGE_YEARS`, `EMPLOYED_YEARS`, `EMPLOYED_AGE_RATIO`; sentinel
  `DAYS_EMPLOYED=365243` được đổi thành missing trước khi tính;
- external source: row-wise mean/min/max/std và số lượng giá trị có mặt từ
  `EXT_SOURCE_1/2/3`;
- application/contact: document count, contact count, số năm từ lần đổi điện
  thoại và tỷ lệ trẻ em trong gia đình;
- housing tùy chọn: row-wise mean/min/max riêng cho các nhóm numeric
  `AVG`/`MODE`/`MEDI` có cùng base name và đủ cả ba suffix.

Các feature E01 trùng tên và cùng định nghĩa không bị nhân đôi. Khi ablation,
mỗi family E02 được thêm trên cùng locked E01 matrix; vì vậy delta đo giá trị
gia tăng so với reference, không phải một pipeline raw độc lập.

`build_aligned_application_features` xác minh tập cột raw train/test, sắp test
theo thứ tự train, sinh feature riêng cho từng split rồi assert tên và thứ tự
cột giống hệt nhau. Việc ghép train/test chỉ dùng để thống nhất category
vocabulary; `TARGET` đã bị loại trước bước này.

## Ví dụ trong credit scoring

`ANNUITY_INCOME_RATIO` là proxy cho gánh nặng nghĩa vụ trả nợ trên thu nhập.
Đây là feature học tập trên dữ liệu Kaggle; chưa được phê duyệt cho production
và không đại diện cho feature policy của FPT.

## Điều cần kiểm tra trong project

- [x] Không đưa `TARGET` vào feature.
- [x] Không để `inf` sau phép chia.
- [x] Kiểm tra train/test có cùng cột và thứ tự cột bằng unit test.
- [ ] Ghi ablation thực tế sau khi notebook chạy thành công.
- [ ] Xác nhận availability, fairness và owner trước production.

## Tài liệu liên quan

- [Feature engineering](feature_engineering.md)
- [Ratio features](ratio_features.md)
- [Leakage checklist](leakage_checklist.md)
- Source: `src/credit_scoring/features/home_credit_application.py`
- Experiment runner: `src/credit_scoring/experiments/home_credit_application.py`
- Kaggle notebook E01: `notebooks/02_home_credit_application/02_home_credit_end_to_end.ipynb`
- Kaggle notebook E02: `notebooks/02_home_credit_application/03_home_credit_e02_application_features.ipynb`
- Kaggle notebook E02 ablation:
  `notebooks/02_home_credit_application/04_home_credit_e02_feature_ablation.ipynb`
- Kaggle notebook E02 credit/amount factorial ablation:
  `notebooks/02_home_credit_application/05_home_credit_e02_credit_amount_factorial_ablation.ipynb`

## Trạng thái áp dụng trong project

Đã triển khai source module và unit tests cho E02 application-only. Metric E02
chỉ được ghi vào experiment log sau khi chạy thật trên full train/test với
LightGBM; feature chưa được phê duyệt production.

## Phân rã nhóm credit/amount E02-A

Module `src/credit_scoring/features/home_credit_credit_amount_factorial.py`
biểu diễn thay đổi E02-A bằng ba nhân tố có thể kết hợp độc lập:

- `N`: ghi đè có khai báo bốn feature E01
  `CREDIT_INCOME_RATIO`, `ANNUITY_INCOME_RATIO`, `GOODS_CREDIT_RATIO` và
  `INCOME_PER_PERSON` bằng `safe_divide`/`float32`;
- `R`: chỉ thêm `CREDIT_ANNUITY_RATIO`;
- `D`: chỉ thêm `CREDIT_GOODS_DIFF`.

Khi không bật `N`, toàn bộ cột E01 được giữ nguyên. Mọi ghi đè phải
nằm trong manifest `overwritten_columns`; comparator sẽ báo lỗi nếu phát hiện
một shared column thay đổi mà không khai báo.

Diagnostic đã chạy trên full local `application_train.csv` cho thấy:

| Feature | E01 dtype → E02-A dtype | Số hàng khác | Max absolute difference |
|---|---:|---:|---:|
| `CREDIT_INCOME_RATIO` | float64 → float32 | 272,039 | 2.810830e-06 |
| `ANNUITY_INCOME_RATIO` | float64 → float32 | 305,261 | 5.836487e-08 |
| `GOODS_CREDIT_RATIO` | float32 → float32 | 0 | 0 |
| `INCOME_PER_PERSON` | float64 → float32 | 118 | 0.0125 |

Hai cột `CREDIT_ANNUITY_RATIO` và `CREDIT_GOODS_DIFF` được xác nhận là cột
mới. Trên ma trận train này, `E02-NRD` khớp chính xác với builder
E02-A hiện tại. Đây là kiểm tra ma trận feature, không phải kết quả AUC;
full factorial baseline vẫn chưa được chạy.
