# Dataset catalog

## Mục tiêu

Lập chỉ mục các dataset tham khảo và liên kết tới registry/card tương ứng.

## Khái niệm chính

Catalog phục vụ điều hướng; nguồn sự thật dạng máy đọc là `catalogs/dataset_registry.yaml`. Card giải thích semantics và hạn chế.



## Ví dụ trong credit scoring

Dataset được thêm vào local chỉ được coi là registered khi registry có version, local path và documentation path hợp lệ.

## Điều cần kiểm tra trong project

- [ ] Đồng bộ catalog với registry.
- [ ] Không đánh dấu available nếu local path chưa được xác minh.
- [ ] Mỗi dataset có data owner hoặc nguồn công khai.

## Tài liệu liên quan

- [Give Me Some Credit](give_me_some_credit.md)
- [Home Credit Default Risk](home_credit_default_risk.md)
- [Model Stability](home_credit_model_stability.md)
- [FPT placeholder](fpt_dataset_template.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
