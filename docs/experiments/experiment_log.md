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
| E02-D-ROBUSTNESS | 2026-08-05 | Locked E01 so với E01 + `CREDIT_GOODS_DIFF` | Paired 5-fold StratifiedKFold trên seed 42/52/62; model seed 42; pre-registered AND gate | `9/15` fold delta dương, thấp hơn ngưỡng `10/15`; symmetric trimmed mean từ số hiển thị khoảng `+0.000195` | [E02-D robustness result](e02_d_robustness_result.md); run code commit `9d58b210d11eea239bf6203c0ee159f4bf7bdfa1` | Completed from user-supplied fold metrics; gate fail; khóa `E03-BASE = E01`; global seed summary chưa được lưu trong workspace |
| E03-P2-SMOKE | 2026-08-06 | E01 application-only + 36 Bureau/Bureau Balance candidates; 5.000 train + 5.000 test | 3-fold StratifiedKFold, seed 42; fingerprint `acbcf4e4...60b5f121`; 300 estimators | Mean fold AUC: BASE `0.733400`, counts `0.735423`, amounts `0.733501`, recency `0.735712`, delinquency `0.735374`, ALL `0.734589`; pooled OOF chỉ là smoke diagnostic | [Feature contract](../features/home_credit_bureau_features.md); [private Kaggle run v3](https://www.kaggle.com/code/tantranmanh/e03-bureau-ablation-smoke); code commit `f439d867...75ebb61e` | Smoke completed; exactly-once OOF và artifact verified; không dùng metric này để chọn feature; chưa chạy full baseline |

Kết quả E01 được trích từ output notebook và ảnh Kaggle do người dùng cung
cấp. E02-DIAG được chạy thật trên full train; E02-KAGGLE có full OOF/test
artifact và submission đã được chấm trên competition test. Không dùng
leaderboard để chọn feature hoặc thay thế OOF/temporal validation.
E02-D-ROBUSTNESS áp dụng nguyên decision rule đã commit trước khi chạy; không
hạ ngưỡng sau khi quan sát kết quả.

E03-P2-SMOKE đọc nguyên 27.299.925 dòng `bureau_balance` rồi lọc theo tập ID của
application smoke. Sau lọc có 49.227 Bureau rows và 1.207.059 Bureau Balance
rows; aggregate tạo 36 feature và giữ cardinality one-to-one. Coverage loan-level
của Bureau Balance trong mẫu smoke là `69,57%` (`34.247/49.227`); mẫu ID nhỏ này
không đại diện cho mốc full-data `45,11%`, nhưng cùng diagnostics sẽ được đối
chiếu trong screening. Fold AUC và pooled OOF đều không có tính quyết định ở smoke.

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
