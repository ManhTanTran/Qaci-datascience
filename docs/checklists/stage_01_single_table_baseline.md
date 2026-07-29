# Checklist stage 01 — Single-table baseline

## Mục tiêu

Kiểm tra baseline đơn bảng có thể tái lập, không leakage và có đánh giá phù hợp.

## Khái niệm chính

Dummy, Logistic và tree baseline phải dùng cùng population, split và metrics để so sánh công bằng.

## Checklist hoàn thành

- [ ] Xác nhận schema, grain, ID và target coding.
- [ ] Profile missingness, duplicates, range và sentinel/outlier.
- [ ] Tách train/validation trước khi fit transform.
- [ ] Dùng pipeline cho imputation, encoding và scaling.
- [ ] Có Dummy baseline và Logistic baseline.
- [ ] Báo ROC-AUC, PR-AUC, Gini và calibration; không chỉ accuracy.
- [ ] So sánh tree model trên cùng split.
- [ ] Có error analysis và test cho preprocessing.

## Ví dụ trong credit scoring

Không fit median imputer trên toàn dataset trước split vì median đã nhìn thấy validation.

## Điều cần kiểm tra trong project

- [ ] Không dùng row ID làm predictor.
- [ ] Không resample validation/test.
- [ ] Ghi experiment thật vào experiment log.

## Tài liệu liên quan

- [Stage 01](../learning/01_give_me_some_credit.md)
- [Give Me Some Credit](../datasets/give_me_some_credit.md)
- [Validation](../evaluation/validation_strategy.md)
- [Experiment log](../experiments/experiment_log.md)

## Trạng thái áp dụng trong project

Checklist dùng cho dataset học công khai; mapping FPT chưa được phê duyệt.
