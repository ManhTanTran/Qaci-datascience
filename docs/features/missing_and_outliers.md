# Missing value và outlier

## Mục tiêu

Hướng dẫn xử lý không làm mất tín hiệu nghiệp vụ hoặc tạo leakage.

## Khái niệm chính

Phân biệt structural, not-applicable, no-hit, not-collected và data error. Outlier policy phải học trên train và áp dụng cố định.



## Ví dụ trong credit scoring

Bureau no-hit có thể tạo missing indicator; không tự điền 0 nếu 0 có nghĩa “không có nợ”.

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
