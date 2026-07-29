# Stage 08 — Áp dụng dữ liệu FPT

## Mục tiêu

Chuyển kỹ năng từ dataset công khai sang bài toán nội bộ sau khi có phê duyệt dữ liệu, target và governance.

## Khái niệm chính

Trình tự bắt buộc: target nội bộ → schema/grain/owner → observation/performance window → feature availability → leakage/fairness review → baseline → temporal validation → business threshold → monitoring plan.

## Nội dung cần xác nhận

- Target event, DPD threshold, cure, indeterminate class và label maturity.
- Population, application/behavioral use case và decision time.
- Primary key, grain, source system, owner và refresh schedule của từng bảng.
- Feature availability, source, formula, cut-off và permitted flag.
- Production metric, validation strategy, approval policy, business cost và threshold.
- Monitoring cadence, drift limits, retraining/escalation owner và model card.

Mọi thông tin nội bộ chưa được xác nhận phải dùng marker chính xác: `TODO(FPT): cần xác nhận với mentor hoặc data owner.`

## Ví dụ trong credit scoring

Chỉ map một feature Home Credit sang FPT khi đã chứng minh hai bên có cùng semantics, thời điểm sẵn có và đơn vị.

## Điều cần kiểm tra trong project

- [ ] Không đưa PII, dữ liệu khách hàng hoặc tín dụng thật vào Git, prompt hay docs.
- [ ] Không tự thay đổi target, production metric hoặc validation strategy.
- [ ] Mọi production feature có source, formula, owner; model có model card.

## Tài liệu liên quan

- [FPT dataset template](../datasets/fpt_dataset_template.md)
- [Prohibited features](../governance/prohibited_features.md)
- [Model approval checklist](../governance/model_approval_checklist.md)
- [Monitoring plan](../monitoring/monitoring_plan.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
