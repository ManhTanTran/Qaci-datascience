# Class imbalance

## Mục tiêu

Xử lý event hiếm mà không làm sai probability.

## Khái niệm chính

Accuracy có thể vô nghĩa khi bad hiếm. Dùng stratification thích hợp, class weight/resampling chỉ trong training fold, PR-AUC và threshold analysis. Resampling làm thay đổi prior nên cần kiểm tra calibration.



## Ví dụ trong credit scoring

Không SMOTE trước khi split; mọi synthetic sample chỉ sinh trong training fold.

## Điều cần kiểm tra trong project

- [ ] So sánh với Dummy và Logistic baseline.
- [ ] Tách train/validation/test trước feature selection và tuning.
- [ ] Đánh giá explainability, calibration, overfit và trường hợp sử dụng.

## Tài liệu liên quan

- [Tổng quan](modeling_overview.md)
- [Model selection](model_selection.md)
- [Calibration](calibration.md)
- [Validation](../evaluation/validation_strategy.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
