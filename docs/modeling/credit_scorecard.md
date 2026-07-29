# Credit scorecard

## Mục tiêu

Mô tả WOE Logistic Scorecard và phép đổi odds thành points.

## Khái niệm chính

Input là WOE bins; Logistic tạo log-odds; scaling dùng base score, base odds và PDO. Ưu điểm governance/giải thích; hạn chế mất chi tiết và cần bin governance. Calibration phụ thuộc sample/target; overfit từ supervised binning phải được kiểm soát.



## Ví dụ trong credit scoring

Mỗi reason code phải truy ngược được tới bin, coefficient và feature definition.

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
