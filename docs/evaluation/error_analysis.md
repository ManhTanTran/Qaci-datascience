# Error analysis

## Mục tiêu

Tìm cohort và failure mode có thể hành động.

## Khái niệm chính

Phân tích false positive/negative theo score band, time, source, product và nhóm được phép; kiểm tra calibration, missingness, data quality và reason codes. Không duyệt PII ở mức cá nhân trong report.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Bad bị bỏ sót tập trung ở thin-file applicants có thể gợi ý cải thiện bureau no-hit handling.

## Điều cần kiểm tra trong project

- [ ] Gắn metric với population, split và confidence interval.
- [ ] Khóa test set cho đánh giá cuối.
- [ ] Báo discrimination, calibration và business impact cùng nhau.

## Tài liệu liên quan

- [Classification metrics](classification_metrics.md)
- [Credit risk metrics](credit_risk_metrics.md)
- [Validation](validation_strategy.md)
- [Threshold](threshold_selection.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
