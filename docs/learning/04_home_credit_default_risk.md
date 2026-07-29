# Stage 04 — Home Credit Default Risk multi-table

## Mục tiêu

Học data modeling, point-in-time aggregation và feature lineage trên dữ liệu tín dụng nhiều bảng.

## Khái niệm chính

Phải hiểu grain, primary/foreign key và quan hệ one-to-many của application, bureau, bureau balance, previous applications, POS cash, credit-card balance và installments trước modeling.

## Kiến thức và feature cần học

- Application features: amount/income/annuity ratios, external scores và anomaly flags.
- Bureau features: active/closed accounts, utilization, credit type mix, delinquency severity và recency.
- Previous application features: count, approval/refusal mix, amount ratios và recency.
- Installment features: days/amount late, payment ratio, frequency, maximum severity và trend trước cut-off.
- POS/credit-card features: balance, utilization, DPD, active months, recency và trend.
- Aggregation cần học: count, nunique, mean, median, min/max, standard deviation, last valid value và time-window aggregates.
- Kiểm soát duplicate grain, point-in-time join, missing-as-no-history so với missing-as-unknown.

Artifact đề xuất: application baseline, bureau features, previous-application features, installment features và multi-table model.

## Ví dụ trong credit scoring

Aggregate từng bảng phụ về một dòng/application và assert uniqueness trước khi join vào base table.

## Điều cần kiểm tra trong project

- [ ] Hoàn thành [stage 03 checklist](../checklists/stage_03_multitable_features.md).
- [ ] Mọi aggregate có source table, key, cut-off, window và test cardinality.
- [ ] Không dùng record phát sinh sau decision time.

## Tài liệu liên quan

- [Competition map](../references/competitions.md)
- [Feature engineering](../features/feature_engineering.md)
- [Bureau features](../features/bureau_features.md)
- [Repayment features](../features/repayment_features.md)

## Trạng thái áp dụng trong project

Đây là stage học trên dữ liệu công khai; mapping sang schema FPT là `TODO(FPT): cần xác nhận với mentor hoặc data owner.`
