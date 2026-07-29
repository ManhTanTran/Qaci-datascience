# Checklist stage 05 — Model stability

## Mục tiêu

Đánh giá hiệu quả và độ ổn định theo thời gian trước khi chọn model hoặc feature.

## Khái niệm chính

Mean metric không đủ; cần metric theo cohort/time, drift, label maturity và degradation.

## Checklist hoàn thành

- [ ] Xác định time index, decision date và label maturity.
- [ ] Tạo train/validation/OOT theo thứ tự thời gian.
- [ ] Fit preprocessing/selection chỉ trên training periods.
- [ ] Báo discrimination và calibration theo tuần/tháng.
- [ ] Tính PSI/feature drift/prediction drift trên bin/reference đã khóa.
- [ ] Phân tích missingness drift và schema drift.
- [ ] So sánh mean performance với variance/degradation.
- [ ] Định nghĩa monitoring cadence, threshold và escalation owner.

## Ví dụ trong credit scoring

Không so bad rate của cohort chưa đủ performance window với cohort reference đã trưởng thành.

## Điều cần kiểm tra trong project

- [ ] Không dùng random split làm bằng chứng stability.
- [ ] Không thay đổi metric/validation nếu chưa có decision record.
- [ ] Ghi rõ delay của target khi monitoring.

## Tài liệu liên quan

- [Stage 07](../learning/07_credit_risk_model_stability.md)
- [Temporal validation](../evaluation/temporal_validation.md)
- [Model stability](../monitoring/model_stability.md)
- [Monitoring plan](../monitoring/monitoring_plan.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
