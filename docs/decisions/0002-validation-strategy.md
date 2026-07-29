# ADR-0002: Validation strategy

## Mục tiêu

Cung cấp khung quyết định validation mà không giả định chiến lược FPT.

## Khái niệm chính

Đề xuất ưu tiên temporal/OOT khi có time semantics; group control khi entity lặp lại; random/stratified chỉ là baseline. Quyết định cuối chưa được phê duyệt.



## Ví dụ trong credit scoring

Nếu một borrower có nhiều hồ sơ, temporal split đơn thuần vẫn cần kiểm tra entity overlap.

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
