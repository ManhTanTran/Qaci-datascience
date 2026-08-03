# Dự án Credit Scoring — Báo cáo Pre-sprint 0

## Mục tiêu

Pre-sprint 0 tập trung vào ba đầu ra:

1. Khảo sát các dataset credit scoring công khai trên Kaggle và hệ thống hóa
   các nhóm feature cần hiểu.
2. Viết các module tái sử dụng cốt lõi cho modeling, evaluation và tuning.
3. Chạy thử end-to-end một notebook Home Credit để chứng minh các module có
   thể tạo được prediction, artifact và Kaggle submission.

Raw Kaggle data, model binary và output artifacts không được commit vào Git.

## Khái niệm chính

Report ghi lại baseline competition có thể truy vết từ application table, reusable
modules, OOF validation và submission artifact; không xem leaderboard score là
bằng chứng production.

## Ví dụ trong credit scoring

E01 dùng cùng population và 5-fold StratifiedKFold để tạo OOF prediction trước khi
fit/predict test, giúp tách model selection nội bộ khỏi Kaggle feedback.

## 1. Kiến thức cơ bản về credit scoring

| Khái niệm | Nội dung đã tìm hiểu |
|---|---|
| Default, delinquency, DPD | Phân biệt default với quá hạn và các mức DPD30/60/90 |
| PD | Xác suất default trong horizon, population và thời điểm dự đoán xác định |
| Credit score và FICO | Credit score xếp hạng rủi ro; FICO là ví dụ score phổ biến, không phải target/metric Home Credit |
| Observation/performance window | Dữ liệu được phép nhìn thấy khi dự đoán và khoảng quan sát outcome; nền tảng phòng leakage |
| Scorecard | Chuyển risk/log-odds thành score; thường dùng logistic regression và score scaling |
| WoE, IV, binning | WoE là log tỷ lệ good/bad theo bin; IV tóm tắt separation; các bước này phải fit trên train |
| ROC-AUC, Gini, KS | Metric discrimination/ranking; Gini thường bằng `2 × AUC - 1` |
| Calibration và threshold | AUC tốt không có nghĩa PD đã calibration tốt hoặc threshold kinh doanh đã hợp lý |
| PSI và drift | PSI đo dịch chuyển phân phối giữa reference và actual population; là tín hiệu điều tra |
| Validation | Stratified CV phù hợp baseline IID; temporal/OOT validation cần khi có time và performance window xác định |

Các tài liệu này được tổ chức trong `docs/domain`, `docs/evaluation`,
`docs/modeling`, `docs/monitoring` và learning track của repository.

## 2. Dataset, feature và EDA đã tìm hiểu

### Dataset Kaggle đã khảo sát

| Dataset | Bài toán học được | Điểm cần lưu ý |
|---|---|---|
| Give Me Some Credit | Binary classification về serious delinquency trong 2 năm | Một bảng, phù hợp để học baseline, missing/outlier và class imbalance |
| Home Credit Default Risk | Dự đoán khó khăn trả nợ từ application và dữ liệu lịch sử quan hệ | Nhiều bảng, cần kiểm soát key, grain, aggregation và point-in-time leakage |
| Home Credit Credit Risk Model Stability | Xây mô hình có độ ổn định theo thời gian | Cần temporal split, drift và performance theo cohort/time |

### Feature từ Give Me Some Credit

| Feature | Nội dung / ý nghĩa cần kiểm tra |
|---|---|
| `RevolvingUtilizationOfUnsecuredLines` | Mức sử dụng hạn mức tín dụng quay vòng; kiểm tra giá trị cực trị và mẫu số/hạn mức |
| `age` | Tuổi khách hàng; cần kiểm tra giá trị bất thường và fairness/proxy risk |
| `NumberOfTime30-59DaysPastDueNotWorse` | Số lần quá hạn 30–59 ngày; kiểm tra sentinel 96/98 |
| `NumberOfTime60-89DaysPastDueNotWorse` | Số lần quá hạn 60–89 ngày; kiểm tra consistency với nhóm DPD khác |
| `NumberOfTimes90DaysLate` | Số lần quá hạn từ 90 ngày; tín hiệu delinquency nghiêm trọng |
| `DebtRatio` | Tỷ lệ nghĩa vụ nợ trên thu nhập; cần xác minh công thức và extreme values |
| `MonthlyIncome` | Thu nhập tháng; kiểm tra missing, zero và skewness |
| `NumberOfOpenCreditLinesAndLoans` | Số hạn mức/khoản vay đang mở; thể hiện credit capacity và credit mix |
| `NumberRealEstateLoansOrLines` | Số khoản vay/hạn mức bất động sản; thể hiện secured-credit mix |
| `NumberOfDependents` | Số người phụ thuộc; kiểm tra missing và fairness/proxy review |

### Nhóm feature từ Home Credit Default Risk

| Nhóm feature | Nội dung |
|---|---|
| Application và affordability | Thu nhập, số tiền vay, niên kim, giá hàng hóa, quy mô hộ gia đình; tạo các ratio như credit/income và annuity/income |
| Demographic và employment | Tuổi, thời gian làm việc, loại nghề nghiệp/tổ chức; kiểm tra sentinel và fairness trước khi production use |
| External score | `EXT_SOURCE_1/2/3` và aggregate mean/median/min/max/std; cần xác minh lineage và thời điểm lấy score |
| Document, contact và housing | Cờ giấy tờ, thông tin liên hệ và thuộc tính nhà ở; tạo count/aggregate minh bạch |
| Bureau và bureau balance | Số account active/closed, loại tín dụng, utilization, DPD, recency và trend trạng thái |
| Previous applications | Số đơn trước, approved/refused/cancelled, requested-vs-granted amount, product/channel và recency |
| Installments | Days late, shortfall/payment ratio, late-payment count, severity và recency |
| POS/cash và credit card | Balance/utilization, DPD, active months, draw/payment behavior và recency |

### Feature cho bài toán stability

Dataset Home Credit Credit Risk Model Stability bổ sung các khái niệm: decision
date, case/application identifier, aggregation theo depth 0/1/2, missingness
drift, distribution drift, PSI, importance stability và performance theo
tuần/cohort.

Các feature trên là kiến thức/reference từ dữ liệu công khai. Không feature nào
được mặc định phê duyệt cho production; với dữ liệu nội bộ phải xác minh source,
formula, owner, cut-off time, availability, fairness và leakage trước khi dùng.

### Ba insights từ EDA và baseline

1. **Missingness và sentinel mang thông tin.** Full train run có 55,374 giá
   trị `DAYS_EMPLOYED` sentinel; pipeline tách chúng thành missing và anomaly
   flag thay vì coi là employment duration thực.
2. **Application-only là baseline phù hợp trước dữ liệu quan hệ.** Nó tạo được
   matrix 149 feature; các bảng lịch sử là hướng cải thiện tiếp theo nhưng cần
   kiểm soát key, cardinality và point-in-time aggregation.
3. **Validation nội bộ và score Kaggle khá nhất quán.** OOF AUC là `0.768696`;
   Kaggle UI hiển thị `Score` `0.76312` và `Public score` `0.76634`. Đây là
   tín hiệu baseline hoạt động, không phải bằng chứng production model.

**Output EDA:** một báo cáo Markdown có thể render để gửi báo cáo, gồm data
audit, feature groups, validation concepts và kết quả baseline.

## 3. Module tái sử dụng cốt lõi

Theo phạm vi Pre-sprint 0, phần tái sử dụng cốt lõi chỉ gồm **modeling**,
**evaluation** và **tuning**. Data loading, data audit và feature engineering
được giữ notebook-local để linh hoạt theo từng dataset.

| Nhóm | Hàm | Tác dụng |
|---|---|---|
| Modeling | `build_model`, `build_lightgbm_model`, `build_catboost_model`, `build_xgboost_model` | Tạo model bằng interface/config thống nhất |
| Modeling | `run_lightgbm_cv` | Train CV, tạo OOF/test predictions, fold scores, feature importance, best iterations và runtime |
| Evaluation | `create_stratified_folds`, `validate_oof_coverage` | Tạo stratified folds và bảo đảm mỗi sample có đúng một OOF prediction |
| Evaluation | `validate_prediction_array`, `calculate_roc_auc` | Kiểm tra prediction hợp lệ và tính ROC-AUC thống nhất |
| Tuning | `tune_lightgbm` | Tuning LightGBM bằng Optuna khi được bật rõ ràng |

`set_global_seed`, artifact exporters và submission builder là utility hỗ trợ
luồng chạy, không được tính là reusable modeling/evaluation/tuning layer trong
báo cáo này.

## 4. Thử nghiệm end-to-end trên Home Credit

### Luồng chạy

Notebook `02_home_credit_end_to_end.ipynb` sử dụng reusable functions để:

1. Import `run_lightgbm_cv` và evaluation logic từ repository; tuning được để
   ở trạng thái tùy chọn và tắt mặc định.
2. Đọc `application_train`/`application_test`, kiểm tra key, missingness và
   target distribution.
3. Xử lý `DAYS_EMPLOYED` sentinel; tạo application ratio, external-score,
   document/contact và housing features.
4. Chạy LightGBM với 5-fold StratifiedKFold và early stopping.
5. Kiểm tra OOF coverage, export artifact và sinh `submission.csv`.

Data loading, data audit và feature engineering application-only nằm trong
notebook cho ví dụ này. Artifact export và submission chỉ là output utility;
core reusable layer vẫn là modeling, evaluation và tuning.

### Cấu hình và kết quả validation

| Hạng mục | Kết quả |
|---|---|
| Training/test matrix | `(307511, 149)` / `(48744, 149)` |
| Validation | 5-fold StratifiedKFold, shuffle, seed 42 |
| Early stopping | 200 rounds; tối đa 5,000 estimators |
| OOF coverage | Minimum `1`, maximum `1` |
| Fold AUC | `0.765256`, `0.775031`, `0.766180`, `0.771822`, `0.765474` |
| Mean fold AUC | `0.768752` |
| Fold AUC standard deviation | `0.004428` |
| OOF AUC | `0.768696` |
| Runtime model training | `445.24` seconds |

### Output Kaggle

Notebook đã tạo `submission.csv` đúng schema và submission được Kaggle chấm.
Theo ảnh kết quả được cung cấp:

| Chỉ số hiển thị trên Kaggle | Giá trị |
|---|---|
| `Score` | `0.76312` |
| `Public score` | `0.76634` |

Ảnh chỉ ghi nhãn `Score`, không ghi rõ đó là private score; vì vậy báo cáo giữ
nguyên nhãn hiển thị thay vì tự suy diễn. Public score là external feedback,
không thay thế OOF validation để chọn model/feature.

### Artifact tạo ra

Notebook ghi các artifacts sau vào Kaggle Working directory:

- `config.json`, `environment.json`, `run_metadata.json`;
- `fold_metrics.csv`;
- `oof_predictions.csv`, `test_predictions.csv`;
- `feature_importance.csv`;
- `submission.csv`.

## Khó khăn gặp phải

- Thiếu thời gian để EDA sâu toàn bộ bảng quan hệ và thử nhiều phương án
  feature engineering/selection.
- Giới hạn phần cứng làm aggregation nhiều bảng và tuning tốn tài nguyên;
  Kaggle được dùng để chạy full baseline.
- Cần Internet để clone source, Add Input đúng competition data, và bảo đảm
  path/module version khớp giữa repository với Kaggle.
- Chưa có data nội bộ và business definition đã phê duyệt; kiến thức/feature
  hiện là tham khảo từ dữ liệu công khai, chưa production hóa.

## Dự kiến công việc tiếp theo

1. EDA kỹ hơn: missingness theo nhóm, distribution, categorical/segment
   analysis và feature-target relationship.
2. Nghiên cứu feature engineering/feature selection: ablation có kiểm soát,
   importance stability, correlation/redundancy và leakage review.
3. Mở rộng sang bureau, previous applications, installments, POS cash và
   credit-card balance bằng point-in-time aggregation có unit tests.
4. Hoàn thiện pipeline: configuration, experiment tracking, tuning tách biệt,
   calibration, temporal validation và model documentation.
5. Khi có dữ liệu nội bộ: xác minh target, windows, availability, fairness,
   business threshold và monitoring plan.

## Kết luận

Pre-sprint 0 đã hoàn thành khảo sát dataset/feature concepts, xây dựng reusable
modules và chứng minh luồng E2E bằng một submission Home Credit đã được Kaggle
chấm. Đây là baseline học tập/competition; các bước production tiếp theo vẫn
cần target definition nội bộ, temporal validation, calibration, business
threshold, fairness review và monitoring.

## Điều cần kiểm tra trong project

- [ ] Giữ raw data và model artifacts ngoài Git.
- [ ] Tái tạo E01 trước khi so sánh challenger.
- [ ] Không diễn giải Kaggle score như temporal hoặc production validation.

## Tài liệu liên quan

- [Experiment log](../experiment_log.md)
- [Baseline results](../baseline_results.md)
- [Tổng hợp Home Credit solution write-ups](../../references/home_credit_solution_writeups.md)
- [Kế hoạch nâng điểm Home Credit](../../roadmap/home_credit_score_improvement_plan.md)

## Trạng thái áp dụng trong project

E01 đã được ghi nhận từ output notebook và ảnh Kaggle do người dùng cung cấp; raw
experiment artifacts không nằm trong workspace.
