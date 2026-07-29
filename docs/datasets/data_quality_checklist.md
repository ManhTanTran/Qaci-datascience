# Checklist chất lượng dữ liệu

## Mục tiêu

Chuẩn hóa kiểm tra trước modeling và khi dữ liệu thay đổi.

## Khái niệm chính

Kiểm tra schema, type, grain, key uniqueness, cardinality, duplicates, ranges, missingness, target rate, time coverage, referential integrity, leakage và drift.



## Ví dụ trong credit scoring

Join application với payment history phải kiểm tra số dòng trước/sau, unmatched keys và mọi payment có timestamp không vượt decision time.

## Điều cần kiểm tra trong project

- [ ] Lưu report tổng hợp không chứa PII.
- [ ] So sánh theo cohort/time/source.
- [ ] Fail pipeline khi vi phạm contract nghiêm trọng.

## Tài liệu liên quan

- [Dataset catalog](dataset_catalog.md)
- [Missing/outlier](../features/missing_and_outliers.md)
- [Leakage](../features/leakage_checklist.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
