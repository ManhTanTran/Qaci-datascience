# LightGBM và CatBoost

## Mục tiêu

Mô tả gradient boosting mạnh cho tabular data.

## Khái niệm chính

Các cây học tuần tự từ residual/gradient. LightGBM cần quản lý categorical encoding theo API; CatBoost có cơ chế categorical target statistics chống leakage khi dùng đúng. Mạnh về ranking, nhưng dễ overfit/tuning và probability có thể cần calibration.



## Ví dụ trong credit scoring

So sánh boosting với Logistic bằng temporal validation, SHAP, latency và stability.

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
