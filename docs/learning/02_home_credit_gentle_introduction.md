# Stage 02 — Home Credit gentle introduction

## Mục tiêu

Tái tạo có phản biện notebook mở đầu Home Credit trên bảng application chính.

## Khái niệm chính

Nguồn chính là [Start Here: A Gentle Introduction](https://www.kaggle.com/code/willkoehrsen/start-here-a-gentle-introduction): categorical encoding, train/test alignment, missingness, anomaly, correlation, feature construction và baseline.

## Kiến thức và feature cần học

- Label encoding so với one-hot encoding và xử lý category chưa thấy.
- `DAYS_EMPLOYED` anomaly flag; không xóa tín hiệu missing/sentinel tùy tiện.
- `EXT_SOURCE_1/2/3`, tuổi và các application features như những tín hiệu dự đoán cần kiểm tra semantics.
- Ratio candidates: credit/income, annuity/income, credit/annuity và employed/age.
- Logistic Regression, Random Forest và LightGBM chỉ là các mức baseline; leaderboard không phải validation production.

Artifact đề xuất: `gentle_reimplementation` dùng API hiện hành và validation độc lập.

## Ví dụ trong credit scoring

Tái tạo ratio feature trong source module, khóa chính sách mẫu số bằng 0 và kiểm tra train/test parity bằng unit test.

## Điều cần kiểm tra trong project

- [ ] Hoàn thành [stage 02 checklist](../checklists/stage_02_home_credit_application.md).
- [ ] Không sao chép `Imputer`, `get_feature_names` hoặc LightGBM callback API đã lỗi thời.
- [ ] Không dùng random K-fold như bằng chứng temporal stability.

## Tài liệu liên quan

- [Đánh giá notebook](../references/kaggle_notebooks.md#1-start-here-a-gentle-introduction)
- [Home Credit dataset card](../datasets/home_credit_default_risk.md)
- [Ratio features](../features/ratio_features.md)
- [Leakage checklist](../features/leakage_checklist.md)

## Trạng thái áp dụng trong project

Nguồn được rà soát ngày 2026-07-29; license tái sử dụng code cần được xác minh trước khi copy.
