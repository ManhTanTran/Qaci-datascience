# Home Credit Default Risk

## Mục tiêu

Tạo dataset card tham khảo cho Home Credit Default Risk, không khẳng định số liệu chưa được xác minh.

## Khái niệm chính

Dataset card là hợp đồng tài liệu về provenance, grain, target, thời gian, hạn chế và cách dùng có trách nhiệm.

## Bài toán và cấu trúc

- **Bài toán:** Dự đoán khả năng gặp khó khăn trả nợ từ application và lịch sử quan hệ nhiều bảng.
- **Grain:** Application ở bảng chính; bảng phụ có grain theo bureau record, prior application hoặc payment event.
- **Target:** Nhãn bảng chính; phải đọc competition description và data dictionary trước khi diễn giải.
- **Cấu trúc bảng:** Kiến trúc quan hệ nhiều bảng; key và cardinality phải được kiểm tra trước aggregation.
- **Nhóm feature:** Application, bureau, prior loans, installments, credit-card balance và POS cash.
- **Missing value:** Missing có thể mang ý nghĩa quy trình/sản phẩm; profile theo source table và cohort.
- **Thời gian:** Có trường thời gian tương đối; cần kiểm tra cut-off và không suy ra OOT nếu không có calendar time phù hợp.

## Feature cần học và kiểm tra

- **Application:** credit/income, annuity/income, credit/annuity, employed/age, `EXT_SOURCE` aggregates, missing/anomaly flags.
- **Bureau/bureau balance:** active/closed count, credit type mix, utilization, maximum DPD, delinquency frequency/severity, recency và status trend.
- **Previous applications:** count, approved/refused/cancelled mix, requested-vs-granted amount, product/channel mix và recency.
- **Installments:** days late, amount shortfall/payment ratio, late-payment count, maximum severity, recency và trend.
- **POS/credit card:** balance/utilization, DPD, active months, draw/payment behavior và recency.
- **Kỹ thuật bắt buộc:** aggregate từng source về application grain; kiểm tra key/cardinality, point-in-time availability, duplicate records và missing-as-no-history.

Không đưa toàn bộ candidate vào model cùng lúc. Mỗi feature cần source, formula, owner, cut-off, missing/outlier policy và validation stability.

## Đánh giá khả năng sử dụng

- **Metric thường dùng:** ROC-AUC cho ranking; thêm calibration, Gini/KS và simulation khi học credit risk.
- **Điều có thể học:** Học join discipline, aggregation, feature lineage và validation cho dữ liệu quan hệ.
- **Hạn chế:** Phức tạp, dễ duplicate grain và leakage nếu aggregate sai.
- **Mức phù hợp với người mới:** Trung bình; nên học sau một dataset đơn bảng.
- **Bài tập đề xuất:** Tạo data mart một dòng/application với unit tests về cardinality và as-of time.

## Ví dụ trong credit scoring

Trước khi modeling, biến mô tả trên card thành kiểm tra schema, uniqueness, missingness, time range và target coding cho Home Credit Default Risk.

## Điều cần kiểm tra trong project

- [ ] Đối chiếu với data dictionary/source version đang sử dụng.
- [ ] Kiểm tra grain trước mọi join hoặc aggregation.
- [ ] Không commit raw data, PII hoặc credential.

Loader hiện yêu cầu các file gốc sau trong `data/home_credit/` hoặc thư mục được
khai báo bởi biến môi trường `HOME_CREDIT_DATA_DIR`:

```text
application_train.csv
application_test.csv
bureau.csv
bureau_balance.csv
previous_application.csv
POS_CASH_balance.csv
credit_card_balance.csv
installments_payments.csv
```

Sau khi cài project bằng
`python -m pip install -e ".[dev,modeling,notebook]"`, chạy kiểm tra nhanh:

```bash
python -m credit_scoring.data.home_credit --nrows 1000
```

Trên Kaggle không cần cài project. Mở notebook
`notebooks/02_home_credit_application/01_kaggle_load_data.ipynb`; notebook sẽ
clone repository, thêm `src` vào Python path và đọc dữ liệu tại
`/kaggle/input/home-credit-default-risk`. Internet phải được bật cho bước clone
và competition data phải được thêm bằng **Add Input**.

Notebook application-only end-to-end tiếp theo là
`notebooks/02_home_credit_application/02_home_credit_end_to_end.ipynb`; notebook
này chứa cleaning, feature engineering, OOF LightGBM và submission. Các bảng
1-n chưa nằm trong phạm vi implementation lần này.

Mặc định loader chỉ đọc hai bảng application. Dùng `--tables all` sau khi
baseline application chạy ổn vì các bảng lịch sử lớn hơn đáng kể. Loader kiểm
tra cột khóa tối thiểu, tính duy nhất của khóa ở bảng có grain duy nhất và mã
nhãn nhị phân; dữ liệu dòng không được ghi ra log.

## Tài liệu liên quan

- [Dataset catalog](dataset_catalog.md)
- [So sánh dataset](dataset_comparison.md)
- [Data quality](data_quality_checklist.md)
- [Target](../domain/target_definition.md)

## Trạng thái áp dụng trong project

Đã có loader và structural audit cho dữ liệu Kaggle công khai; chưa tải dữ liệu,
chưa chạy experiment và chưa ghi nhận metric. Dữ liệu FPT vẫn dùng marker:
TODO(FPT): cần xác nhận với mentor hoặc data owner.
