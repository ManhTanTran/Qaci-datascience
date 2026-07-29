# Competitions

## Mục tiêu

Lập bản đồ competition theo kỹ năng học.

## Khái niệm chính

Give Me Some Credit cho tabular baseline; Home Credit Default Risk cho multi-table aggregation; Model Stability cho robustness/time. Luôn đọc rules/data description version hiện hành.

## Thứ tự đọc nguồn

| Thứ tự | Nguồn | Kiến thức mới cần đạt |
| --- | --- | --- |
| 0 | [Give Me Some Credit — Overview](https://www.kaggle.com/competitions/GiveMeSomeCredit/overview) | Bài toán đơn bảng, target horizon hai năm, utilization, delinquency, missing/outlier, baseline và calibration. |
| 1 | [Home Credit Default Risk — Competition](https://www.kaggle.com/competitions/home-credit-default-risk) | Bài toán application scoring, metric, seven logical data sources, key/grain và target semantics. |
| 2 | [Start Here: A Gentle Introduction](https://www.kaggle.com/code/willkoehrsen/start-here-a-gentle-introduction) | EDA/preprocessing/baseline trên application table. |
| 3 | [Home Credit kernels theo vote](https://www.kaggle.com/c/home-credit-default-risk/kernels?competitionId=9120&group=everyone&pageSize=20&sortBy=voteCount) | Dùng như discovery index cho EDA, manual/automated feature engineering, LightGBM, feature selection và memory optimization; không phải một bài đọc tuyến tính. |
| 4 | [Credit Risk EDA: Defaults, Segments & Trends](https://www.kaggle.com/code/beatafaron/credit-risk-eda-defaults-segments-trends-1) | Segment/vintage/WOE và bài học leakage trên một dataset Lending Club khác. |
| 5 | [Home Credit — Credit Risk Model Stability: Data](https://www.kaggle.com/competitions/home-credit-credit-risk-model-stability/data) | Tables theo depth, temporal split, stability-aware feature engineering và drift. |

Snapshot top-voted Home Credit kernels ngày 2026-07-29 cho thấy các nhánh học chính: Gentle Introduction, complete EDA, LightGBM simple features, manual feature engineering, null importances, model tuning, automated feature engineering, feature selection, memory reduction và all-table models. Vote count chỉ dùng để khám phá nguồn, không dùng làm thước đo chất lượng kỹ thuật hoặc tính phù hợp production.

## Bản đồ kiến thức mới

- **Từ Give Me Some Credit:** data audit đơn bảng, sentinel/outlier, imbalanced classification và pipeline baseline.
- **Từ Home Credit Default Risk:** grain/cardinality, point-in-time aggregation, feature lineage và nhiều bảng lịch sử.
- **Từ notebook segment/trend:** target maturity, cohort/vintage, WOE/IV fitting discipline và outcome leakage.
- **Từ Model Stability:** temporal/OOT evidence, metric theo tuần, feature/prediction/performance drift và model degradation.


## Ví dụ trong credit scoring

Không chuyển leaderboard metric thành production KPI.

## Điều cần kiểm tra trong project

- [ ] Xác minh license và nguồn.
- [ ] Ghi version/ngày truy cập khi thêm link.
- [ ] Không coi nguồn ngoài là xác nhận chính sách FPT.

## Tài liệu liên quan

- [Dataset catalog](../datasets/dataset_catalog.md)
- [Lộ trình](../roadmap/learning_path.md)
- [Reproducibility](../governance/reproducibility.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
