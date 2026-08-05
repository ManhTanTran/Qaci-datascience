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

Numeric helper dùng chung `safe_divide` nằm tại
`src/credit_scoring/numeric.py`. Hàm căn chỉnh theo index của pandas Series,
trả `float32`, và biến mẫu số bằng 0/missing cùng mọi kết quả
infinite thành `NaN`. Các dataset-specific feature builder có thể gọi helper
này nhưng vẫn phải định nghĩa formula và missing policy trong notebook.
