# ADR-0003: Primary metric

## Mục tiêu

Cung cấp khung chọn primary metric mà không tự gán metric production.

## Khái niệm chính

Metric phải phù hợp mục tiêu: ranking, probability, policy hoặc stability; luôn kèm guardrails calibration/business/fairness. Quyết định cuối chưa được phê duyệt.



## Ví dụ trong credit scoring

ROC-AUC có thể là metric ranking, nhưng không thay thế Brier/calibration và business simulation.

## Điều cần kiểm tra trong project

- [ ] Ghi owner, ngày và trạng thái.
- [ ] Liên kết evidence/experiment.
- [ ] Tạo ADR mới khi supersede quyết định accepted.

## Tài liệu liên quan

- [Decision index](README.md)
- [Validation](../evaluation/validation_strategy.md)
- [Metrics](../evaluation/credit_risk_metrics.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
