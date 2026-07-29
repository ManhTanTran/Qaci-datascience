# Model selection

## Mục tiêu

Đưa ra khung chọn model không chỉ dựa trên một metric.

## Khái niệm chính

So sánh discrimination, calibration, stability, business value, fairness, explainability, latency, maintainability và governance. Test set chỉ dùng một lần cho đánh giá cuối.



## Ví dụ trong credit scoring

Chọn Logistic nếu chênh lệch ranking nhỏ nhưng governance/calibration tốt; chọn boosting khi lợi ích được chứng minh và controls đủ.

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
