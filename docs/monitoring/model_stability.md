# Model stability

## Mục tiêu

Theo dõi tính ổn định tổng thể của scorecard/model.

## Khái niệm chính

Stability gồm input, score, performance, calibration và policy outcomes theo time/cohort. Drift không tự động đồng nghĩa model hỏng.



## Ví dụ trong credit scoring

Score distribution ổn định nhưng bad rate tăng có thể do concept drift hoặc label/process change.

## Điều cần kiểm tra trong project

- [ ] Xác nhận reference window và label maturity.
- [ ] Gắn owner, cadence, threshold và escalation.
- [ ] Lưu monitoring artifact đã khử định danh.

## Tài liệu liên quan

- [Monitoring plan](monitoring_plan.md)
- [Feature stability](../features/feature_stability.md)
- [Metrics](../evaluation/credit_risk_metrics.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
