# Home Credit Credit Risk Model Stability

## Mục tiêu

Tạo dataset card tham khảo cho Home Credit Credit Risk Model Stability, không khẳng định số liệu chưa được xác minh.

## Khái niệm chính

Dataset card là hợp đồng tài liệu về provenance, grain, target, thời gian, hạn chế và cách dùng có trách nhiệm.

## Bài toán và cấu trúc

- **Bài toán:** Học xây dựng mô hình ổn định khi dữ liệu có nhiều bảng và thay đổi theo thời gian.
- **Grain:** Case/application ở base table; bảng depth khác nhau có nhiều record mỗi case.
- **Target:** Nhãn competition; phải xác minh semantics và availability của từng cột.
- **Cấu trúc bảng:** Nhiều bảng train/test theo depth; join keys và time columns phải lấy từ metadata chính thức.
- **Nhóm feature:** Static, person, bureau, deposit, debit-card và các aggregation theo cấu trúc competition.
- **Missing value:** Missing phản ánh coverage và quy trình; cần theo dõi missingness drift theo thời gian.
- **Thời gian:** Yếu tố temporal/stability là trọng tâm; split phải tôn trọng ordering và quy tắc competition.

## Feature cần học và kiểm tra

- **Base/time:** case identifier, decision date, week/month index, target maturity và cohort.
- **Depth 0:** static application/person/bureau snapshot ở một dòng/case.
- **Depth 1:** count, recency, frequency, severity, mean/max/last từ nhiều record/case.
- **Depth 2:** aggregate hai tầng; trước hết về parent record, sau đó về case để tránh nhân bản.
- **Stability features:** missing indicators, record coverage, age/recency, rolling aggregates và trend/slope khi event time hợp lệ.
- **Stability checks:** missingness drift, distribution drift, PSI, importance stability và performance theo tuần/cohort.

Không chọn feature chỉ theo mean Gini/AUC. Cần so performance trung bình với variance, worst-period performance và degradation qua thời gian.

## Đánh giá khả năng sử dụng

- **Metric thường dùng:** Competition metric và stability component phải đọc từ nguồn version đang dùng; không tự ghi công thức.
- **Điều có thể học:** Học pipeline nhiều bảng, temporal validation, drift và robust feature engineering.
- **Hạn chế:** Độ phức tạp cao; semantics cột mã hóa và compute cost là thách thức.
- **Mức phù hợp với người mới:** Thấp đến trung bình cho người mới; phù hợp sau khi nắm pipeline cơ bản.
- **Bài tập đề xuất:** Dựng subset nhỏ, kiểm tra schema drift và so sánh random với temporal validation.

## Ví dụ trong credit scoring

Trước khi modeling, biến mô tả trên card thành kiểm tra schema, uniqueness, missingness, time range và target coding cho Home Credit Credit Risk Model Stability.

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
