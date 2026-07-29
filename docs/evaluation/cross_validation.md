# Cross-validation

## Mục tiêu

Dùng nhiều fold để ước lượng variance mà không rò rỉ.

## Khái niệm chính

Stratified K-fold hữu ích cho class imbalance IID; GroupKFold cho entity; time-series split cho ordering. Toàn bộ preprocessing, resampling, selection và calibration phải nằm trong fold.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Target encoding phải fit theo training fold, không tính từ toàn dataset.

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
