# Feature drift

## Mục tiêu

Theo dõi distribution, missingness và category/schema của input.

## Khái niệm chính

Dùng schema checks, missing-rate delta, quantiles, category share, PSI/CSI và source freshness. Phân biệt data issue với population shift.



## Ví dụ trong credit scoring

Một category mới từ upstream mapping phải tạo alert và fallback được kiểm thử.

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
