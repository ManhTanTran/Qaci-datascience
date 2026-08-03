# Experiment log

## Mục tiêu

Lập chỉ mục experiment có thể tái lập mà không tạo kết quả giả.

## Khái niệm chính

Mỗi dòng cần ID, ngày, owner, hypothesis, dataset/feature/model version, validation, artifact path, trạng thái và link report.

## Ví dụ trong credit scoring

E01 ghi OOF AUC và Kaggle score từ artifact đã được cung cấp; một experiment mới
chỉ được thêm khi có cấu hình, output và report có thể truy vết tương ứng.



## Experiment đã đăng ký

| ID | Ngày ghi nhận | Dataset / feature scope | Validation | Kết quả | Artifact / report | Trạng thái |
|---|---|---|---|---|---|---|
| E01 | 2026-07-30 | Home Credit application-only | 5-fold StratifiedKFold, seed 42 | OOF AUC `0.768696`; Kaggle `Score` `0.76312`; public `0.76634` | [Pre-sprint 0 report](30_07_2026/home_credit_application_baseline_report.md); Kaggle Working artifact path ghi trong report | Completed; Kaggle score ghi theo nhãn ảnh cung cấp |
| E02-DIAG | 2026-08-03 | Home Credit application-only E01 + 18 E02 features; train-only diagnostic | Cùng fixed 5-fold, seed 42; fingerprint `9ad19c60...a4684bdc` | E01 diagnostic OOF `0.768683`; E02 diagnostic OOF `0.769071`; delta `+0.000388` | [E02 diagnostic report](e02_application_feature_diagnostic.md) | Diagnostic only; thiếu application_test.csv, chưa ablation, không phải completed E02 |
| E02-KAGGLE | 2026-08-03 | Home Credit application-only E01 + 18 E02 features; Kaggle full train/test | 5-fold StratifiedKFold, seed 42; cấu hình model khóa như E01 | OOF `0.769030`; mean fold `0.769076`; delta OOF so với locked E01 `+0.000334`; private `0.76330`; public `0.76708` | [E02 diagnostic and Kaggle artifact review](e02_application_feature_diagnostic.md); run commit `32533899...` | Completed; OOF/submission artifact verified; family ablation pending |

Kết quả E01 được trích từ output notebook và ảnh Kaggle do người dùng cung
cấp. E02-DIAG được chạy thật trên full train; E02-KAGGLE có full OOF/test
artifact và submission đã được chấm trên competition test. Không dùng
leaderboard để chọn feature hoặc thay thế OOF/temporal validation.

## Điều cần kiểm tra trong project

- [ ] Chỉ ghi kết quả từ artifact có thể truy vết.
- [ ] Không dùng test để lựa chọn.
- [ ] Cập nhật registry/decision record khi phù hợp.

## Tài liệu liên quan

- [Experiment template](experiment_template.md)
- [Baseline results](baseline_results.md)
- [Model selection](../modeling/model_selection.md)

## Trạng thái áp dụng trong project

Đã ghi nhận E01 và E02 leaderboard từ ảnh Kaggle và đã kiểm tra E02 OOF/test
artifact do người dùng cung cấp ngoài workspace. Raw data và prediction artifact
không được commit; temporal/OOT validation và family ablation chưa được xác minh.
