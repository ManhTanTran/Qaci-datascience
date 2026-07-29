# Explainability

## Mục tiêu

Phân biệt giải thích toàn cục, cục bộ và reason code.

## Khái niệm chính

Coefficient/WOE, tree rules, permutation importance, PDP/ICE và SHAP trả lời câu hỏi khác nhau. Giải thích liên hệ mô hình không phải causal explanation; correlated features làm attribution bất ổn.



## Ví dụ trong credit scoring

Reason code cho hồ sơ phải dùng feature được phép, ngôn ngữ nghiệp vụ và kiểm tra consistency.

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
