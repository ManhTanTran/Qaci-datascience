# Performance drift

## Mục tiêu

Theo dõi metric khi outcome đã mature.

## Khái niệm chính

Theo dõi AUC/Gini/KS, PR-AUC, Brier/log loss, calibration, bad rate và capture rate với delay/maturity và interval.



## Ví dụ trong credit scoring

Không so bad rate chưa mature với reference đã mature.

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
