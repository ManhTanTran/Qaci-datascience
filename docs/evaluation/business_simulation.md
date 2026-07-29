# Business simulation

## Mục tiêu

Biến prediction thành kịch bản quyết định có assumptions rõ.

## Khái niệm chính

Simulation cần population, policy, score ordering, revenue/cost/loss, capacity, reject handling và uncertainty. Không khẳng định uplift causal từ retrospective classification.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

So sánh policy tại cùng approval rate và stress-test loss-given-bad assumptions.

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
