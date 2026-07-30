# Home Credit application features

## Mục tiêu

Ghi lại feature engineering application-only được triển khai trong notebook
Kaggle đầu tiên.

## Khái niệm chính

Các feature được tạo ở application grain, sau bước cleaning sentinel và trước
modeling. Loader không tạo feature. Notebook dùng `safe_divide` để tránh
infinite values và giữ missing nếu mẫu số không hợp lệ.

Nhóm feature hiện có:

- amount/affordability ratios;
- age/employment and family ratios;
- `EXT_SOURCE` aggregates, product, range và missing count;
- document/contact flag counts;
- selected housing aggregate.

## Ví dụ trong credit scoring

`ANNUITY_INCOME_RATIO` là proxy cho gánh nặng nghĩa vụ trả nợ trên thu nhập.
Đây là feature học tập trên dữ liệu Kaggle; chưa được phê duyệt cho production
và không đại diện cho feature policy của FPT.

## Điều cần kiểm tra trong project

- [ ] Không đưa `TARGET` vào feature.
- [ ] Không để `inf` sau phép chia.
- [ ] Kiểm tra train/test có cùng cột và thứ tự cột.
- [ ] Ghi ablation thực tế sau khi notebook chạy thành công.
- [ ] Xác nhận availability, fairness và owner trước production.

## Tài liệu liên quan

- [Feature engineering](feature_engineering.md)
- [Ratio features](ratio_features.md)
- [Leakage checklist](leakage_checklist.md)
- Notebook: `notebooks/02_home_credit_application/02_home_credit_end_to_end.ipynb`

## Trạng thái áp dụng trong project

Đã triển khai application-only trong notebook Kaggle; chưa chạy artifact
verified trong workspace và chưa được phê duyệt production.
