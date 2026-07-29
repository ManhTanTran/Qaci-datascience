# Credit risk metrics

## Mục tiêu

Giải thích Gini, KS, calibration curve và PSI trong bối cảnh credit risk.

## Khái niệm chính

Gini thường là `2*AUC-1`; KS là khoảng cách lớn nhất giữa cumulative score distributions của good/bad; calibration curve so predicted với observed rate; PSI so phân phối theo bins và cần context.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Một KS cao không đảm bảo probability calibrated hoặc policy có lợi nhuận.

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
