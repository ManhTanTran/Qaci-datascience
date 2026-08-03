# Baseline results

## Mục tiêu

Cung cấp vị trí ghi kết quả baseline đã được xác minh.

## Khái niệm chính

Baseline tối thiểu là Dummy và Logistic cùng dataset/split; báo discrimination, calibration, runtime và artifact. Không có số giả/placebo.



## Ví dụ trong credit scoring

Home Credit application-only baseline E01 đã có output notebook được ghi nhận:
OOF AUC `0.768696` từ 5-fold StratifiedKFold; Kaggle UI hiển thị `Score`
`0.76312` và `Public score` `0.76634`. Xem chi tiết về datasets/features,
reusable source components, cấu hình, artifacts và giới hạn xác minh trong
[Pre-sprint 0 report](30_07_2026/home_credit_application_baseline_report.md).

Submission E02 application features đã được Kaggle chấm: private `0.76330`,
public `0.76708`. So với E01, delta tương ứng là `+0.00018` và `+0.00074`.
Full Kaggle artifact cho OOF AUC `0.769030`, mean fold AUC `0.769076` và runtime
`420,35` giây; delta OOF so với locked E01 là `+0.000334`. OOF có đủ 307.511
hàng, mỗi hàng được validate đúng một lần; submission khớp test prediction.
Xem
[E02 diagnostic report](e02_application_feature_diagnostic.md).

## Điều cần kiểm tra trong project

- [ ] Chỉ ghi kết quả từ artifact có thể truy vết.
- [ ] Không dùng test để lựa chọn.
- [ ] Cập nhật registry/decision record khi phù hợp.

## Tài liệu liên quan

- [Experiment template](experiment_template.md)
- [Baseline results](baseline_results.md)
- [Model selection](../modeling/model_selection.md)

## Trạng thái áp dụng trong project

E01 và E02 leaderboard được ghi nhận từ ảnh Kaggle. E02 Kaggle artifact đã được
kiểm tra nhưng không được commit vào workspace; paired E01/E02 OOF comparison,
family ablation và production validation chưa được xác minh.
