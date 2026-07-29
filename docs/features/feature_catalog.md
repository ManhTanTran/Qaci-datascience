# Feature catalog

## Mục tiêu

Định nghĩa điểm vào cho feature documentation và registry.

## Khái niệm chính

Feature registry là inventory máy đọc; feature card/group page chứa semantics, công thức, owner, availability và controls.

Nếu chưa biết bắt đầu từ file nào, đọc phần **Feature — nên đọc gì trước?** trong [hướng dẫn thứ tự đọc](../reading_order.md).



## Ví dụ trong credit scoring

Một feature ratio chỉ sẵn sàng khi source columns, division-by-zero policy và as-of logic được kiểm thử.

## Điều cần kiểm tra trong project

- [ ] Ghi source, owner, formula và cut-off.
- [ ] Fit mọi data-dependent transform chỉ trên train.
- [ ] Cập nhật feature registry và test.

## Tài liệu liên quan

- [Hướng dẫn thứ tự đọc](../reading_order.md)
- [Feature groups](feature_groups.md)
- [Feature engineering](feature_engineering.md)
- [Leakage](leakage_checklist.md)
- Registry máy đọc: `catalogs/feature_registry.yaml`

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
