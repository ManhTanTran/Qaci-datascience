# Hướng dẫn thứ tự đọc

## Mục tiêu

Giúp người mới biết nên đọc tài liệu nào trước, tài liệu nào phụ thuộc kiến thức trước đó và khi nào có thể chuyển sang thực hành.

## Khái niệm chính

Có hai cách dùng knowledge base:

1. Theo **learning stage**: dùng [Learning track](learning/index.md) khi học từ đầu đến áp dụng.
2. Theo **chủ đề**: dùng thứ tự trong trang này khi cần học riêng domain, feature, modeling, evaluation hoặc monitoring.

Không cần đọc tất cả file theo thứ tự alphabet. Mỗi nhóm bên dưới đi từ khái niệm nền → kỹ thuật → kiểm soát.

## Thứ tự đọc tổng thể

### 1. Kiến thức miền

Đọc trước khi mở dataset:

1. [Tổng quan credit scoring](domain/credit_scoring_overview.md)
2. [Quy trình cho vay](domain/lending_process.md)
3. [Glossary](domain/glossary.md)
4. [Định nghĩa target](domain/target_definition.md)
5. [Observation/performance window](domain/observation_performance_window.md)
6. [Credit score và PD](domain/credit_score_vs_pd.md)
7. [Business metrics](domain/business_metrics.md)

Điều kiện chuyển tiếp: giải thích được target, grain, decision time, observation window và performance window.

### 2. Dataset

1. [Dataset catalog](datasets/dataset_catalog.md)
2. [So sánh dataset](datasets/dataset_comparison.md)
3. Chọn một dataset card:
   - [Give Me Some Credit](datasets/give_me_some_credit.md) cho baseline đơn bảng.
   - [Home Credit Default Risk](datasets/home_credit_default_risk.md) cho dữ liệu nhiều bảng.
   - [Home Credit Model Stability](datasets/home_credit_model_stability.md) cho temporal robustness.
4. [Data quality checklist](datasets/data_quality_checklist.md)

Người mới nên học Give Me Some Credit trước Home Credit.

### 3. Feature — nên đọc gì trước?

#### Chặng A — Hiểu feature và kiểm soát leakage

1. [Feature catalog](features/feature_catalog.md)
2. [Feature groups](features/feature_groups.md)
3. [Leakage checklist](features/leakage_checklist.md)
4. [Missing values và outliers](features/missing_and_outliers.md)

Đây là chặng bắt buộc. Chưa nên tạo feature nếu chưa trả lời được source, formula, cut-off và missing policy.

#### Chặng B — Feature tại application time

5. [Demographic features](features/demographic_features.md)
6. [Income và employment features](features/income_employment_features.md)
7. [Loan/application features](features/loan_features.md)
8. [Ratio features](features/ratio_features.md)

Thứ tự này đi từ cột nguồn sang feature dẫn xuất. Đọc ratio sau income và loan để hiểu tử số, mẫu số, đơn vị và zero-denominator policy.

#### Chặng C — Feature lịch sử tín dụng

9. [Bureau features](features/bureau_features.md)
10. [Repayment features](features/repayment_features.md)
11. [Delinquency features](features/delinquency_features.md)
12. [Temporal features](features/temporal_features.md)

Đọc bureau/repayment trước delinquency và temporal vì DPD, frequency, severity và recency cần hiểu event nguồn, observation window và cut-off.

#### Chặng D — Xây và kiểm chứng feature

13. [Feature engineering](features/feature_engineering.md)
14. [Feature stability](features/feature_stability.md)

Sau chặng này mới đăng ký candidate trong `catalogs/feature_registry.yaml`. Feature production còn cần source, formula, owner, availability, governance approval và validation evidence.

Đường tắt theo mục tiêu:

| Mục tiêu | Thứ tự tối thiểu |
| --- | --- |
| Baseline Give Me Some Credit | Catalog → Groups → Leakage → Missing/Outlier → Ratio → Delinquency → Engineering |
| Home Credit application table | Catalog → Leakage → Missing/Outlier → Income/Employment → Loan → Ratio → Engineering |
| Home Credit nhiều bảng | Catalog → Leakage → Bureau → Repayment → Delinquency → Temporal → Engineering → Stability |
| Model stability | Leakage → Temporal → Engineering → Feature Stability → Monitoring |

### 4. Modeling

1. [Modeling overview](modeling/modeling_overview.md)
2. [Logistic Regression](modeling/logistic_regression.md)
3. [Tree-based models](modeling/tree_based_models.md)
4. [LightGBM/CatBoost](modeling/lightgbm_catboost.md)
5. [Class imbalance](modeling/class_imbalance.md)
6. [WOE/IV/binning](modeling/woe_iv_binning.md)
7. [Credit scorecard](modeling/credit_scorecard.md)
8. [Calibration](modeling/calibration.md)
9. [Explainability](modeling/explainability.md)
10. [Model selection](modeling/model_selection.md)

Không bắt đầu bằng boosting hoặc tuning. Cần Dummy/Logistic baseline và validation trước.

### 5. Evaluation

1. [Classification metrics](evaluation/classification_metrics.md)
2. [Credit-risk metrics](evaluation/credit_risk_metrics.md)
3. [Validation strategy](evaluation/validation_strategy.md)
4. [Cross-validation](evaluation/cross_validation.md)
5. [Temporal validation](evaluation/temporal_validation.md)
6. [Threshold selection](evaluation/threshold_selection.md)
7. [Business simulation](evaluation/business_simulation.md)
8. [Error analysis](evaluation/error_analysis.md)

Metric phải được đọc cùng split, population và label maturity.

### 6. Monitoring

Đọc sau modeling và temporal validation:

1. [Model stability](monitoring/model_stability.md)
2. [PSI](monitoring/population_stability_index.md)
3. [Feature drift](monitoring/feature_drift.md)
4. [Prediction drift](monitoring/prediction_drift.md)
5. [Performance drift](monitoring/performance_drift.md)
6. [Monitoring plan](monitoring/monitoring_plan.md)

### 7. Governance

Nên đọc leakage/privacy từ sớm; phần approval đọc trước khi bàn giao model:

1. [Data privacy](governance/data_privacy.md)
2. [Prohibited features](governance/prohibited_features.md)
3. [Fairness và bias](governance/fairness_and_bias.md)
4. [Model risks](governance/model_risks.md)
5. [Reproducibility](governance/reproducibility.md)
6. [Model approval checklist](governance/model_approval_checklist.md)

## Ví dụ trong credit scoring

Nếu muốn tạo `annuity_to_income`, trước tiên đọc income/employment và loan features để hiểu hai cột nguồn, sau đó đọc ratio features để định nghĩa công thức, rồi leakage và feature stability để kiểm tra availability và robustness.

## Điều cần kiểm tra trong project

- [ ] Dùng Learning track nếu chưa biết bắt đầu từ đâu.
- [ ] Hoàn thành điều kiện chuyển tiếp trước khi sang nhóm phức tạp hơn.
- [ ] Không chỉ đọc notebook; phải có source module, test hoặc artifact phù hợp.
- [ ] Không tự áp dụng feature công khai sang FPT khi chưa xác minh semantics.

## Tài liệu liên quan

- [Learning track](learning/index.md)
- [Feature catalog](features/feature_catalog.md)
- [Stage checklists](checklists/stage_00_foundation.md)
- [Kaggle notebook reviews](references/kaggle_notebooks.md)

## Trạng thái áp dụng trong project

Đây là thứ tự đọc đề xuất. Các quyết định target, feature và modeling cho dữ liệu nội bộ vẫn là `TODO(FPT): cần xác nhận với mentor hoặc data owner.`
