# Prediction drift

## Mục tiêu

Theo dõi score/PD trước khi label trưởng thành.

## Khái niệm chính

Theo dõi mean/quantile/bin share, approval impact và calibration proxy có thận trọng. Prediction drift có thể đến từ input hoặc model version.



## Ví dụ trong credit scoring

Tỷ lệ hồ sơ ở high-risk band tăng cần phân rã theo source/product/time.

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
