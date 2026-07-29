# Stage 01 — Give Me Some Credit

## Mục tiêu

Học vòng đời baseline credit-risk classification trên dataset đơn bảng trước khi xử lý dữ liệu quan hệ.

## Khái niệm chính

Thứ tự thực hành: schema → data audit → EDA → Dummy baseline → Logistic Regression → tree baseline → evaluation và error analysis.

## Kiến thức và feature cần học

- Missingness của `MonthlyIncome` và `NumberOfDependents`; không mặc định missing at random.
- Outlier/sentinel của utilization, debt ratio, tuổi và ba biến delinquency.
- Class imbalance, stratified split, preprocessing pipeline và `predict_proba`.
- ROC-AUC, PR-AUC, Gini, calibration và bad rate theo score band.
- Nhóm feature: revolving utilization, age, DPD 30–59/60–89/90+, debt ratio, monthly income, open credit lines, real-estate loans/lines và dependents.
- Không dùng cột row identifier làm predictor.

Artifact đề xuất: data audit, EDA, Logistic baseline và tree baseline. Notebook chỉ điều phối; preprocessing và feature logic phải nằm trong source module có test.

## Ví dụ trong credit scoring

So sánh Dummy, Logistic và tree model trên cùng một split; chỉ kết luận feature hữu ích khi cải thiện ổn định trên validation đã khóa.

## Điều cần kiểm tra trong project

- [ ] Hoàn thành [stage 01 checklist](../checklists/stage_01_single_table_baseline.md).
- [ ] Profile riêng các giá trị 96/98 ở biến delinquency trước khi coi là số lần quá hạn thật.
- [ ] Fit imputer, scaler, binning và encoder chỉ trên training fold.

## Tài liệu liên quan

- [Dataset card](../datasets/give_me_some_credit.md)
- [Missing và outlier](../features/missing_and_outliers.md)
- [Classification metrics](../evaluation/classification_metrics.md)
- [Calibration](../modeling/calibration.md)

## Trạng thái áp dụng trong project

Dataset này chỉ dùng làm nguồn học công khai; không suy rộng kết luận sang FPT.
