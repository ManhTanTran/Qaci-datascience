# Logistic Regression

## Mục tiêu

Giải thích baseline tuyến tính xác suất.

## Khái niệm chính

Input là feature numeric/encoded; output là log-odds và probability. Cần imputation, encoding, scaling tùy regularization; ưu điểm đơn giản, dễ giải thích; hạn chế tuyến tính trong log-odds. Calibration thường tốt hơn model rank-only nhưng vẫn phải kiểm tra; overfit được kiểm soát bằng regularization.



## Ví dụ trong credit scoring

Dùng Logistic làm baseline có coefficient sign review và calibration curve.

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
