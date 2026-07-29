# Nhóm feature

## Mục tiêu

Cung cấp taxonomy chung cho feature review.

## Khái niệm chính

Mười nhóm: demographic; income/employment; loan application; repayment; delinquency; bureau; ratio; temporal; aggregated historical; missingness indicators.

## Nhóm aggregated historical và missingness

- **Aggregated historical:** count/sum/max/recency/trend trên events trước cut-off; rủi ro là sai grain, cửa sổ không nhất quán và event tương lai.
- **Missingness indicators:** cờ thiếu theo nguồn/nhóm; có thể phản ánh quy trình, nhưng phải review drift, fairness và availability.

Expected direction chỉ là giả thuyết liên hệ, không phải quan hệ nhân quả; luôn kiểm tra bằng dữ liệu.

## Ví dụ trong credit scoring

Một aggregation `max_days_past_due` thuộc delinquency và aggregated historical; registry chọn category chính và documentation nêu cross-tag.

## Điều cần kiểm tra trong project

- [ ] Ghi source, owner, formula và cut-off.
- [ ] Fit mọi data-dependent transform chỉ trên train.
- [ ] Cập nhật feature registry và test.

## Tài liệu liên quan

- [Feature groups](feature_groups.md)
- [Feature engineering](feature_engineering.md)
- [Leakage](leakage_checklist.md)
- Registry máy đọc: `catalogs/feature_registry.yaml`

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
