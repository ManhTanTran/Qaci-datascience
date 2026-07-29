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

## Tài liệu liên quan

- [Dataset catalog](dataset_catalog.md)
- [So sánh dataset](dataset_comparison.md)
- [Data quality](data_quality_checklist.md)
- [Target](../domain/target_definition.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
