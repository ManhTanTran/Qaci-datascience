# Stage 07 — Credit risk model stability

## Mục tiêu

Học xây model và chọn feature có hiệu quả ổn định theo thời gian, không chỉ có điểm trung bình cao.

## Khái niệm chính

Nguồn chính là [Home Credit — Credit Risk Model Stability](https://www.kaggle.com/competitions/home-credit-credit-risk-model-stability/data), có base table và các bảng partition theo depth 0/1/2.

## Kiến thức và feature cần học

- `case_id`, decision date, week/month index, target và quy tắc label maturity.
- Depth 0: một dòng/case; depth 1: nhiều dòng/case; depth 2: nhiều dòng trong từng record depth 1.
- Aggregate history bằng count, recency, frequency, severity, mean/max/last và trend.
- Temporal split, OOT validation, Gini/AUC theo tuần/cohort và confidence interval.
- Missingness drift, feature drift, prediction drift, performance drift và PSI.
- Stability-aware selection: đánh đổi mean performance với variance/degradation qua thời gian.

Artifact đề xuất: schema analysis, temporal baseline, PSI/drift report và weekly performance report.

## Ví dụ trong credit scoring

Một feature tăng AUC trung bình nhưng làm Gini giảm mạnh ở các tuần tương lai không nên được chọn chỉ theo điểm trung bình.

## Điều cần kiểm tra trong project

- [ ] Hoàn thành [stage 05 checklist](../checklists/stage_05_model_stability.md).
- [ ] Không flatten depth 1/2 bằng join trực tiếp gây nhân bản case.
- [ ] Fit feature selection và preprocessing theo training periods.

## Tài liệu liên quan

- [Dataset card](../datasets/home_credit_model_stability.md)
- [Temporal validation](../evaluation/temporal_validation.md)
- [Feature drift](../monitoring/feature_drift.md)
- [Performance drift](../monitoring/performance_drift.md)

## Trạng thái áp dụng trong project

Metadata công khai được rà soát ngày 2026-07-29; công thức competition metric cần xác minh từ rules trước khi triển khai.
