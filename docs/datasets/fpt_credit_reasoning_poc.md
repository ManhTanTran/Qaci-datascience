# FPT Credit Reasoning PoC — synthetic dataset

## Mục tiêu

Mô tả workbook synthetic dùng để kiểm thử pipeline reasoning, không mô tả dữ liệu
khách hàng thật và không xác nhận khả năng sẵn sàng cho production.

## Khái niệm chính

Sheet `Synthetic_Customers` là source of truth cho raw input. `Scenario_Design` chỉ
là metadata dùng để tạo research case; `Prompt_View` là legacy/reference và không
được đọc làm profile. `Source_Mapping` bổ sung lineage của dữ liệu synthetic.

## Ví dụ trong credit scoring

Một dòng được validate, gom thành 10 business groups, gắn evidence trace, rồi chạy
rule engine deterministic. AI chỉ nhận business profile và rule result để giải thích.

## Điều cần kiểm tra trong project

- [ ] Không suy ra thu nhập cá nhân từ `avg_monthly_income` cấp khu vực.
- [ ] Không biến missing hoặc invalid thành zero.
- [ ] Xác nhận semantics/unit với data owner trước mọi promotion.

## Tài liệu liên quan

- [FPT reasoning pipeline](../pipelines/fpt_credit_reasoning_poc.md)
- [FPT reasoning feature groups](../features/fpt_reasoning_poc_features.md)
- [Dataset catalog](dataset_catalog.md)

## Trạng thái áp dụng trong project

Research candidate synthetic only. Workbook local được cung cấp qua attachment và
không được commit vào Git; output pipeline cũng nằm trong thư mục bị ignore.
