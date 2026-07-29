# Stage 03 — Complete EDA và feature importance

## Mục tiêu

Học EDA có hệ thống trên nhiều bảng và diễn giải feature importance với giới hạn rõ ràng.

## Khái niệm chính

Nguồn tham khảo là [Home Credit: Complete EDA + Feature Importance](https://www.kaggle.com/code/codename007/home-credit-complete-eda-feature-importance). Notebook đọc bảy nguồn dữ liệu, phân tích missingness/segments và fit Random Forest để lấy in-sample impurity importance.

## Kiến thức và cách đọc có phản biện

- EDA theo từng bảng: shape, grain, missingness, target distribution và segment bad rate.
- Luôn báo cả sample count và bad rate; segment nhỏ dễ tạo kết luận không ổn định.
- Impurity importance của Random Forest có bias và notebook không có validation cho bước importance.
- Cần học permutation importance hoặc SHAP trên validation/OOT, kèm stability theo fold/cohort.
- Importance, correlation và SHAP không chứng minh quan hệ nhân quả hoặc tính hợp lệ về fairness.
- Notebook encode category bằng train+test và fill missing bằng `-999`; không sao chép máy móc vào pipeline.

Artifact đề xuất: EDA report và feature-importance comparison trên validation.

## Ví dụ trong credit scoring

Một category có bad rate cao nhưng rất ít hồ sơ phải đi kèm confidence interval/sample count và không tự động trở thành policy rule.

## Điều cần kiểm tra trong project

- [ ] Tách descriptive EDA khỏi feature selection.
- [ ] Fit mọi transform bằng training data.
- [ ] Kiểm tra importance theo fold, thời gian và nhóm feature tương quan.

## Tài liệu liên quan

- [Explainability](../modeling/explainability.md)
- [Feature stability](../features/feature_stability.md)
- [Fairness](../governance/fairness_and_bias.md)
- [Kaggle notebook reviews](../references/kaggle_notebooks.md)

## Trạng thái áp dụng trong project

Nguồn được rà soát ngày 2026-07-29; kết quả notebook không được coi là metric của project.
