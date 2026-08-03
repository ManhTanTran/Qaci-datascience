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

Notebook Kaggle đầu tiên đã được thêm tại
`02_home_credit_application/01_kaggle_load_data.ipynb`. Notebook clone source
code từ GitHub, thêm `src` vào `sys.path` và đọc competition data trực tiếp từ
`/kaggle/input/home-credit-default-risk`; không cài package vào máy local.

Notebook application-only end-to-end tại
`02_home_credit_application/02_home_credit_end_to_end.ipynb` chứa data audit,
E01 feature engineering, LightGBM OOF, diagnostics và submission.

Notebook E02 nằm tại
`02_home_credit_application/03_home_credit_e02_application_features.ipynb`.
Notebook giữ workflow E01: data/feature engineering ở notebook và chỉ dùng
model, CV, artifact, tuning và submission functions đã có trên public repo.
Không phụ thuộc module E02 chưa push; full baseline ghi file dễ tải tại
`/kaggle/working/submission.csv`.

Notebook ablation E02 nằm tại
`02_home_credit_application/04_home_credit_e02_feature_ablation.ipynb`. Notebook
dùng reusable source feature builders, chạy tuần tự E01, E02-A đến E02-E và
E02-ALL trên cùng fold assignment, rồi xuất OOF/test prediction, fold metrics,
feature importance và bảng delta so với E01 cho từng experiment. Mặc định là
`smoke`; chỉ dùng `baseline` để ghi kết quả sau khi smoke run thành công.
Notebook này import E02 feature/experiment modules từ repository, vì vậy cần
commit và push source tương ứng trước khi chạy bản Kaggle clone từ `main`.

Khi chạy experiment, cập nhật `docs/experiments/experiment_log.md`; không
commit dữ liệu khách hàng, PII, credential hoặc output chứa dữ liệu nhạy cảm.

Xem thứ tự và điều kiện hoàn thành tại `docs/learning/index.md`.
