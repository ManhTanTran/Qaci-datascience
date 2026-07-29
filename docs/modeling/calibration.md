# Calibration

## Mục tiêu

Đảm bảo probability dự báo khớp tần suất quan sát.

## Khái niệm chính

Dùng calibration curve, Brier/log loss và calibration intercept/slope. Platt hoặc isotonic phải fit trên calibration split/cross-fitting, không trên test. Calibration phụ thuộc population và base rate.



## Ví dụ trong credit scoring

Một boosting model có AUC cao nhưng overpredict bad rate cần calibration trên sample độc lập và monitoring sau triển khai.

## Điều cần kiểm tra trong project

- [ ] So sánh với Dummy và Logistic baseline.
- [ ] Tách train/validation/test trước feature selection và tuning.
- [ ] Đánh giá explainability, calibration, overfit và trường hợp sử dụng.

## Tài liệu liên quan

- [Tổng quan](modeling_overview.md)
- [Model selection](model_selection.md)
- [Calibration](calibration.md)
- [Validation](../evaluation/validation_strategy.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
