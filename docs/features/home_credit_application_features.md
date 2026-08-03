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

## Trạng thái áp dụng trong project

Đã triển khai source module và unit tests cho E02 application-only. Metric E02
chỉ được ghi vào experiment log sau khi chạy thật trên full train/test với
LightGBM; feature chưa được phê duyệt production.
