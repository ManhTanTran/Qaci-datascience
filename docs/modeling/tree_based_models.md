# Decision Tree và Random Forest

## Mục tiêu

Giải thích mô hình cây trước boosting.

## Khái niệm chính

Decision Tree chia không gian theo rule, dễ minh họa nhưng dễ overfit. Random Forest bagging nhiều cây, robust hơn nhưng giải thích toàn cục kém hơn. Input cần missing/encoding phù hợp implementation; output score/probability thường cần calibration.



## Ví dụ trong credit scoring

Giới hạn depth/min samples cho tree; với forest kiểm tra OOB/validation gap và probability calibration.

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
