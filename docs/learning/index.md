# Learning track

## Mục tiêu

Biến knowledge base theo chủ đề thành một thứ tự học thực hành từ nền tảng credit scoring đến áp dụng dữ liệu FPT.

## Khái niệm chính

Mỗi stage kết hợp kiến thức miền, dataset, feature, modeling, validation và governance. Hoàn thành stage bằng bằng chứng như data audit, source module, test hoặc experiment log; không chỉ bằng việc đọc notebook.

## Thứ tự học

| Stage | Nội dung | Dataset/nguồn chính | Kết quả cần đạt |
| --- | --- | --- | --- |
| 00 | [Credit scoring foundation](00_credit_scoring_foundation.md) | Domain docs | Giải thích được target, grain, cut-off và horizon. |
| 01 | [Give Me Some Credit](01_give_me_some_credit.md) | Give Me Some Credit | Baseline đơn bảng có pipeline và validation. |
| 02 | [Home Credit gentle introduction](02_home_credit_gentle_introduction.md) | Application table | Tái tạo EDA và baseline bằng API hiện hành. |
| 03 | [Complete EDA và feature importance](03_complete_eda_feature_importance.md) | Home Credit notebooks | EDA có hệ thống và diễn giải importance có kiểm soát. |
| 04 | [Home Credit multi-table](04_home_credit_default_risk.md) | Home Credit Default Risk | Data mart một dòng/application, join và aggregation có test. |
| 05 | [Defaults, segments và trends](05_defaults_segments_trends.md) | Lending Club reference notebook | Segment/vintage analysis và nhận diện outcome leakage. |
| 06 | [WOE và credit scorecard](06_woe_credit_scorecard.md) | Internal modeling docs | Binning → WOE/IV → Logistic → score scaling. |
| 07 | [Model stability](07_credit_risk_model_stability.md) | Home Credit Model Stability | Temporal/OOT validation và drift monitoring. |
| 08 | [Áp dụng dữ liệu FPT](08_fpt_dataset_application.md) | Dữ liệu nội bộ đã phê duyệt | Baseline, threshold và monitoring theo governance. |

## Ví dụ trong credit scoring

Không chuyển sang feature engineering nhiều bảng khi chưa chứng minh được grain, split và baseline đơn bảng ở stage trước.

## Điều cần kiểm tra trong project

- [ ] Mỗi stage có artifact và tiêu chí hoàn thành rõ ràng.
- [ ] Logic tái sử dụng nằm trong source module và có test, không chỉ trong notebook.
- [ ] Experiment thật được ghi vào experiment log; không ghi metric giả trong learning track.

## Tài liệu liên quan

- [Lộ trình tổng quát](../roadmap/learning_path.md)
- [Kaggle notebooks](../references/kaggle_notebooks.md)
- [Competition map](../references/competitions.md)
- [Weekly checklist](../roadmap/weekly_checklist.md)

## Trạng thái áp dụng trong project

Learning track này là thứ tự học đề xuất; trạng thái dữ liệu FPT vẫn là `TODO(FPT): cần xác nhận với mentor hoặc data owner.`
