# FPT reasoning PoC feature groups

## Mục tiêu

Ghi lại contract raw → business profile cho PoC mà không biến các group research
thành feature production.

## Khái niệm chính

Mười group được khai báo cố định trong `feature_mapping.yaml`: `user_id`, `age`,
`local_context`, `location`, `device_usage`, `payment_history_12m`,
`shopping_installment`, `orders`, `healthcare_spending` và `fpt_education`.

## Ví dụ trong credit scoring

Các cột `is_late_*`, `total_late_day_*` và `payment_month_count_*` được gom vào
`payment_history_12m`; các cột kinh tế vùng được giữ là `contextual_proxy` và có
`personal_income: null`.

## Điều cần kiểm tra trong project

- [ ] Mọi group giữ nguyên danh sách cột theo config, không suy ra schema từ data.
- [ ] Evidence trace ghi raw column, transform, sheet, row/user và validation status.
- [ ] Feature này là research candidate; chưa được phép dùng để train production model.

## Tài liệu liên quan

- Mapping source: `configs/research/fpt_reasoning_poc/feature_mapping.yaml`
- [Feature catalog](feature_catalog.md)
- [FPT dataset card](../datasets/fpt_credit_reasoning_poc.md)

## Trạng thái áp dụng trong project

Đã có source code và test contract. Semantics, unit, availability và owner cho dữ
liệu FPT thật vẫn là `TODO(FPT): cần xác nhận với mentor hoặc data owner.`
