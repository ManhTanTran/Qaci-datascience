# Give Me Some Credit

## Mục tiêu

Tạo dataset card tham khảo cho Give Me Some Credit, không khẳng định số liệu chưa được xác minh.

## Khái niệm chính

Dataset card là hợp đồng tài liệu về provenance, grain, target, thời gian, hạn chế và cách dùng có trách nhiệm.

## Bài toán và cấu trúc

- **Bài toán:** Bài toán tabular binary classification minh họa rủi ro khó khăn tài chính.
- **Grain:** Một dòng cho một hồ sơ quan sát; cột đầu là row identifier và không phải predictor.
- **Target:** `SeriousDlqin2yrs`; semantics nghiệp vụ phải đối chiếu Data Dictionary của version đang dùng.
- **Cấu trúc bảng:** Bảng huấn luyện và bảng chấm điểm; không ghi số cột/dòng khi chưa profile bản local.
- **Nhóm feature:** Demographic proxy, utilization, delinquency, debt/income và credit lines theo schema công khai.
- **Missing value:** Thường có missing; phải lập profile theo cột và không mặc định missing at random.
- **Thời gian:** Mốc thời gian hạn chế; không phù hợp để chứng minh temporal validation thực tế.

## Feature cần học và kiểm tra

| Feature gốc | Câu hỏi cần học |
| --- | --- |
| `RevolvingUtilizationOfUnsecuredLines` | Mẫu số/limit là gì, vì sao có giá trị vượt 1, cap/log transform có giữ ý nghĩa không? |
| `age` | Kiểm tra tuổi 0/phi thực tế; đánh giá fairness và proxy risk trước khi modeling. |
| `NumberOfTime30-59DaysPastDueNotWorse` | Phân biệt frequency với severity; điều tra sentinel 96/98. |
| `NumberOfTime60-89DaysPastDueNotWorse` | Kiểm tra consistency với các ngưỡng DPD khác và observation window. |
| `NumberOfTimes90DaysLate` | Tín hiệu severe delinquency; kiểm tra sentinel và target overlap. |
| `DebtRatio` | Xác minh công thức/đơn vị; extreme value có thể do missing income hoặc mẫu số nhỏ. |
| `MonthlyIncome` | Missingness, zero, skewness và imputation theo train only. |
| `NumberOfOpenCreditLinesAndLoans` | Phân biệt capacity, credit mix và duplicate accounts. |
| `NumberRealEstateLoansOrLines` | Count, secured-credit mix và extreme value. |
| `NumberOfDependents` | Missingness và fairness/proxy review; không mặc định được phép dùng. |

Profile tạm thời trên public training file ngày 2026-07-29 xác nhận missing tập trung ở `MonthlyIncome` và `NumberOfDependents`, đồng thời có extreme/sentinel ở utilization, debt ratio, age và delinquency counts. Đây là câu hỏi data quality, không phải căn cứ tự động xóa/cap.

## Đánh giá khả năng sử dụng

- **Metric thường dùng:** ROC-AUC thường dùng trong competition; bổ sung PR-AUC, calibration và business metrics khi học.
- **Điều có thể học:** Học baseline, imputation, outlier handling, imbalance và leakage discipline.
- **Hạn chế:** Ngữ cảnh vận hành, cost và time semantics hạn chế.
- **Mức phù hợp với người mới:** Cao cho người mới nếu bắt đầu từ baseline đơn giản.
- **Bài tập đề xuất:** So sánh Dummy, Logistic và tree model bằng cùng validation split; lập error analysis.

## Ví dụ trong credit scoring

Trước khi modeling, biến mô tả trên card thành kiểm tra schema, uniqueness, missingness, time range và target coding cho Give Me Some Credit.

## Điều cần kiểm tra trong project

- [ ] Đối chiếu với data dictionary/source version đang sử dụng.
- [ ] Kiểm tra grain trước mọi join hoặc aggregation.
- [ ] Không commit raw data, PII hoặc credential.

## Tài liệu liên quan

- [Dataset catalog](dataset_catalog.md)
- [So sánh dataset](dataset_comparison.md)
- [Data quality](data_quality_checklist.md)
- [Target](../domain/target_definition.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
