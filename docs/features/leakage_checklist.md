# Checklist leakage

## Mục tiêu

Phát hiện target, temporal, train-test, group và preprocessing leakage.

## Khái niệm chính

Các nguồn phổ biến: outcome columns, post-decision events, future snapshots, duplicate entity giữa split, imputation/binning fit trên toàn bộ data.



## Ví dụ trong credit scoring

Một cột collection outcome có tương quan cao nhưng chỉ phát sinh sau default phải bị loại khỏi application model.

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
