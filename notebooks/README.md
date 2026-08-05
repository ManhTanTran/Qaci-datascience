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

Notebook factorial ablation cho nhóm credit/amount nằm tại
`02_home_credit_application/05_home_credit_e02_credit_amount_factorial_ablation.ipynb`.
Notebook tách E02-A thành ba nhân tố độc lập: `N` chuẩn hóa lại bốn
ratio E01, `R` thêm `CREDIT_ANNUITY_RATIO`, và `D` thêm
`CREDIT_GOODS_DIFF`. Tám tổ hợp được chạy tuần tự trên cùng fold list;
`E02-NRD` phải khớp chính xác với E02-A hiện tại trước khi notebook được
phép chọn `E02-FINAL`. Mặc định `smoke` chỉ kiểm tra luồng chạy; chỉ
`baseline` đầy đủ mới tạo cấu hình `E02-FINAL` và `submission.csv`.
Notebook không tự submit lên Kaggle và không dùng leaderboard để chọn feature.

Notebook robustness check nằm tại
`02_home_credit_application/06_home_credit_e02_d_robustness.ipynb`. Notebook
chỉ chạy hai cấu hình khác nhau đúng một cột — `E01` và
`E01 + CREDIT_GOODS_DIFF` — trên ba validation seed `42`, `52` và `62`. Trong
mỗi seed, hai cấu hình dùng chung một fold list và được xác nhận bằng
`fold_fingerprint` trùng nhau; model random seed cố định `42` và LightGBM
parameters giữ nguyên cấu hình đã khóa từ E01. Feature matrix dựng một lần rồi
dùng lại cho cả ba seed, chỉ fold thay đổi.

Quy tắc quyết định được khóa trước tại
`docs/experiments/e02_d_robustness_preregistration.md`. **Tài liệu đó phải được
commit và push trước khi chạy cell đầu tiên** — notebook kiểm tra sự tồn tại
của nó trong repository đã clone và dừng nếu thiếu. Chỉ lượt `baseline` mới có
hiệu lực quyết định; lượt `smoke` chỉ kiểm tra pipeline. Notebook xuất
`oof_predictions.csv` có cột `FOLD`, `fold_assignments.csv`, `fold_metrics.csv`,
`robustness_summary.csv` và `decision.json`.

Notebook E03 Bureau ablation nằm tại
`03_home_credit_multitable/01_bureau_ablation.ipynb`. Logic đọc, aggregate hai
tầng và merge dữ liệu Home Credit nằm trong các hàm của notebook; notebook chỉ
gọi source chung cho `safe_divide`, E01 preparation, folds, LightGBM, ablation
và artifact writers. Chế độ `smoke` lấy application trước rồi lọc Bureau theo
ID để không tạo mẫu gần như không giao nhau. Sau Checkpoint 3, notebook được
chuyển sang `screening`: toàn bộ application, 5 folds và LightGBM configuration
khóa từ E01. Cell đầu tiên kiểm tra pre-registration trước khi chạy model.

Khi chạy experiment, cập nhật `docs/experiments/experiment_log.md`; không
commit dữ liệu khách hàng, PII, credential hoặc output chứa dữ liệu nhạy cảm.

Xem thứ tự và điều kiện hoàn thành tại `docs/learning/index.md`.
