# E03 Bureau screening pre-registration

## Mục tiêu

Khóa trước tiêu chí screening cho 36 research candidate từ `bureau.csv` và
`bureau_balance.csv`. E03-BASE là E01 application-only; OOF AUC tham chiếu đã
khóa là `0.768696` tại seed 42. Tài liệu này được tạo trước khi chạy full-data
screening và không chứa kết quả screening.

## Khái niệm chính

Mỗi cấu hình family (`counts`, `amounts`, `recency`, `delinquency`) và `E03-ALL`
được so sánh theo cặp với E03-BASE trên cùng năm fold. Target, preprocessing,
LightGBM parameters, fold assignments và seed 42 phải giống nhau giữa các cấu
hình. Public/private leaderboard không tham gia quyết định.

Một cấu hình chỉ **PASS** khi đồng thời thỏa cả hai điều kiện:

1. `delta_oof_auc_vs_baseline >= +0.0005`;
2. `positive_fold_count_vs_baseline >= 4/5`.

Nếu thiếu artifact, E03-BASE không tái lập hợp lý, fold fingerprint khác nhau,
OOF coverage không exactly-once hoặc một trong hai điều kiện không đạt, cấu hình
đó không được coi là PASS. Sau khi có bất kỳ kết quả full screening nào, rule,
ngưỡng và cách đếm fold trong tài liệu này **không được sửa**.
Machine-readable lock: `RULE_LOCKED_AFTER_RESULTS = true`.

## Ví dụ trong credit scoring

Nếu một family có OOF delta `+0.0007` nhưng chỉ `3/5` fold dương thì family đó
FAIL. Nếu OOF delta `+0.0006` và `4/5` fold dương thì family đó PASS. Smoke AUC
không được thay vào các phép kiểm này.

## Điều cần kiểm tra trong project

- [ ] Chạy toàn bộ application train/test, bureau và bureau_balance.
- [ ] Dùng 5-fold StratifiedKFold, seed 42 và cấu hình LightGBM khóa từ E01.
- [ ] Xác minh cùng fold fingerprint và OOF coverage exactly-once.
- [ ] Đối chiếu Bureau Balance loan coverage với mốc profiling `45,11%`.
- [ ] Áp dụng nguyên AND rule `+0.0005` và `4/5`, không sửa sau khi xem kết quả.
- [ ] Chỉ ghi kết quả thật từ artifact vào experiment log.

## Tài liệu liên quan

- [Experiment log](experiment_log.md)
- [Home Credit Bureau features](../features/home_credit_bureau_features.md)
- [Home Credit validation](../evaluation/home_credit_validation.md)
- Notebook: `notebooks/03_home_credit_multitable/01_bureau_ablation.ipynb`

## Trạng thái áp dụng trong project

Pre-registered ngày 2026-08-06 trước full screening. Rule đang khóa và có hiệu
lực cho E03 Phase 3; chưa ghi nhận kết quả full-data tại thời điểm tạo tài liệu.
