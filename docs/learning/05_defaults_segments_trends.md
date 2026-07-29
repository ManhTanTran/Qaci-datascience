# Stage 05 — Defaults, segments và trends

## Mục tiêu

Học phân tích bad rate theo phân khúc, cohort và thời gian, đồng thời nhận diện feature hậu nghiệm.

## Khái niệm chính

Nguồn tham khảo là [Credit Risk EDA: Defaults, Segments & Trends](https://www.kaggle.com/code/beatafaron/credit-risk-eda-defaults-segments-trends-1), sử dụng dataset Lending Club riêng, không phải Home Credit.

## Kiến thức và cách đọc có phản biện

- Default rate tổng phải đi cùng target definition và label maturity.
- Segment analysis cần bad rate, sample count, missingness và uncertainty.
- Trend theo issue cohort/vintage khác với trend theo calendar observation.
- WOE/IV chỉ được fit trên training fold; notebook tính trước split nên không phải mẫu validation an toàn.
- Mapping `Current`/`In Grace Period` thành good và late/default/charged-off thành bad cần maturity/cure/indeterminate policy.
- Các biến như `recoveries`, `last_pymnt_amnt`, `total_rec_prncp`, `total_rec_int`, `total_rec_late_fee`, `out_prncp`, `debt_settlement_flag` và ngày thanh toán cuối thường là post-origination/outcome leakage cho application scoring.
- Không dùng ngày chạy notebook làm mốc impute cho feature thời gian.

Artifact đề xuất: segment/vintage report chỉ dùng feature và trạng thái hợp lệ theo observation point.

## Ví dụ trong credit scoring

So sánh bad rate theo vintage chỉ khi các cohort có cùng performance window đã trưởng thành.

## Điều cần kiểm tra trong project

- [ ] Ghi rõ dataset khác Home Credit và không trộn schema.
- [ ] Audit availability của từng cột trước khi phân tích/modeling.
- [ ] Tách indeterminate loans thay vì ép mọi trạng thái chưa trưởng thành thành good.

## Tài liệu liên quan

- [Target definition](../domain/target_definition.md)
- [Business metrics](../domain/business_metrics.md)
- [Prohibited features](../governance/prohibited_features.md)
- [Temporal validation](../evaluation/temporal_validation.md)

## Trạng thái áp dụng trong project

Notebook chỉ là nguồn học phản biện; không xác nhận target hoặc policy FPT.
