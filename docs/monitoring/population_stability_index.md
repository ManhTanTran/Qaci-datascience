# Population Stability Index

## Mục tiêu

Dùng PSI như tín hiệu sàng lọc drift, không phải phán quyết độc lập.

## Khái niệm chính

PSI cộng `(actual%-expected%)*ln(actual%/expected%)` theo bins; cần smoothing, bin reference cố định, sample size và threshold được phê duyệt.



## Ví dụ trong credit scoring

PSI tăng do product mix thay đổi cần slice analysis trước hành động.

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
