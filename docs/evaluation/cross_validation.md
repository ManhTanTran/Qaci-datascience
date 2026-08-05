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

`run_ablation` trong `src/credit_scoring/experiments/ablation.py` nhận các
`PreparedDataset` và một fold list đã tính trước. Runner chạy baseline
trước, buộc target và identifier của các arm giống nhau, kiểm tra
fold fingerprint chung và trả paired fold delta so với baseline.

`run_lightgbm_cv` trả cả `fold_assignments` trong `CVResult`, ngoài
`validation_counts` và fold fingerprint. Assignment dùng chỉ số zero-based
theo thứ tự fold list; artifact trình bày có thể đổi sang one-based.
