# 0006 — FPT reasoning PoC boundary

## Mục tiêu

Ghi nhận ranh giới giữa pipeline dữ liệu dùng chung, application upload và research
runner cho FPT Credit Reasoning PoC.

## Khái niệm chính

Raw data được validate trước khi map thành 10 business groups. Evidence/source trace
đi cùng profile. Rule engine giữ quyết định deterministic; AI chỉ tạo explanation,
phân loại evidence, phát hiện missing/contradiction và báo `rule_conflict`.

## Ví dụ trong credit scoring

`avg_monthly_income` và `avg_monthly_spend` là `contextual_proxy`; profile giữ giá trị
nguồn nhưng `personal_income`/`personal_spend` là `null`. Khoảng tuổi `23-30` không
được gán midpoint và trả `UNKNOWN` cho research condition age > 23.

## Điều cần kiểm tra trong project

- [ ] Không promote research candidate thành production feature.
- [ ] Không đổi missing/invalid thành zero.
- [ ] Không đưa API key vào source, notebook, log hoặc output.
- [ ] `age > 23` vẫn cần mentor/data-owner xác nhận nếu muốn thành hard rule chính thức.

## Tài liệu liên quan

- [FPT reasoning pipeline](../pipelines/fpt_credit_reasoning_poc.md)
- [FPT synthetic dataset](../datasets/fpt_credit_reasoning_poc.md)
- [FPT reasoning feature groups](../features/fpt_reasoning_poc_features.md)

## Trạng thái áp dụng trong project

Accepted cho research PoC và UI prototype. Đây không phải quyết định production; các
uncertainty về unit, availability, target và policy vẫn là
`TODO(FPT): cần xác nhận với mentor hoặc data owner.`
