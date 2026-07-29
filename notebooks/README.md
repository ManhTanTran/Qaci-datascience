# Notebook learning plan

Notebook là lớp khám phá và trình bày. Logic tái sử dụng cho preprocessing, feature engineering, validation và metrics phải nằm trong source module và có test.

## Thứ tự artifact đề xuất

```text
notebooks/
├── 00_problem_definition.ipynb
├── 01_give_me_some_credit/
│   ├── 01_data_audit.ipynb
│   ├── 02_eda.ipynb
│   ├── 03_logistic_baseline.ipynb
│   └── 04_tree_baseline.ipynb
├── 02_home_credit_application/
│   ├── 01_gentle_reimplementation.ipynb
│   ├── 02_complete_eda.ipynb
│   └── 03_feature_importance.ipynb
├── 03_home_credit_multitable/
│   ├── 01_application_baseline.ipynb
│   ├── 02_bureau_features.ipynb
│   ├── 03_previous_application.ipynb
│   ├── 04_installment_features.ipynb
│   └── 05_multitable_model.ipynb
├── 04_credit_scorecard/
│   ├── 01_defaults_segments_trends.ipynb
│   ├── 02_binning_woe_iv.ipynb
│   └── 03_credit_scorecard.ipynb
├── 05_model_stability/
│   ├── 01_schema_analysis.ipynb
│   ├── 02_temporal_baseline.ipynb
│   ├── 03_psi_and_drift.ipynb
│   └── 04_weekly_stability.ipynb
└── 06_fpt_application/
    ├── 01_data_audit.ipynb
    ├── 02_eda.ipynb
    ├── 03_baseline.ipynb
    └── 04_stability.ipynb
```

Các file `.ipynb` chưa được tạo vì chưa có implementation hoặc kết quả thật. Khi chạy experiment, cập nhật `docs/experiments/experiment_log.md`; không commit dữ liệu khách hàng, PII, credential hoặc output chứa dữ liệu nhạy cảm.

Xem thứ tự và điều kiện hoàn thành tại `docs/learning/index.md`.
