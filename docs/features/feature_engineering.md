# Feature engineering

## Mục tiêu

Đưa feature từ ý tưởng thành phép biến đổi có lineage và test.

## Khái niệm chính

Pipeline gồm define grain/cut-off, join an toàn, aggregate, transform, fit-on-train, validate và register.



## Ví dụ trong credit scoring

Tạo delinquency count chỉ từ events trước decision time và test bằng synthetic boundary cases.

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
