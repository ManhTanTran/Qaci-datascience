# Threshold selection

## Mục tiêu

Chọn cut-off từ mục tiêu và ràng buộc nghiệp vụ trên validation.

## Khái niệm chính

Threshold liên kết score với approve/review/decline. Chọn theo cost, approval capacity, bad-rate ceiling, capture target và fairness controls; probability threshold không mặc định 0.5.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Vẽ frontier approval rate–bad rate trên validation; test chỉ báo cáo threshold đã khóa.

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
