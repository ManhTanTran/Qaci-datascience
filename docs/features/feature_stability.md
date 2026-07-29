# Feature stability

## Mục tiêu

Đánh giá độ bền phân phối và quan hệ feature-target qua thời gian/cohort.

## Khái niệm chính

Theo dõi missing rate, quantiles, category share, PSI, rank/order, IV hoặc model attribution với sample-size context.



## Ví dụ trong credit scoring

Feature có PSI cao do thay đổi upstream cần root-cause analysis trước khi re-train.

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
