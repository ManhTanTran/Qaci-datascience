# Kaggle notebooks

## Mục tiêu

Lập tiêu chí dùng notebook công khai như tài liệu học, không copy mù.

## Khái niệm chính

Đánh giá license, data version, leakage, validation, reproducibility và applicability. Notebook leaderboard không phải bằng chứng production.

## Thứ tự đọc đề xuất

Trước khi đọc notebook, nên hoàn thành [định nghĩa target](../domain/target_definition.md), [observation/performance window](../domain/observation_performance_window.md) và [dataset card Home Credit Default Risk](../datasets/home_credit_default_risk.md). Thứ tự notebook hiện tại:

| Thứ tự | Notebook | Mức độ | Vai trò trong lộ trình |
| --- | --- | --- | --- |
| 1 | [Start Here: A Gentle Introduction](https://www.kaggle.com/code/willkoehrsen/start-here-a-gentle-introduction) — Will Koehrsen | Cơ bản | Đọc đầu tiên để hiểu quy trình EDA → preprocessing → feature engineering → baseline trên bảng application chính; đọc trước các notebook manual/automated feature engineering nhiều bảng. |
| 2 | [Home Credit: Complete EDA + Feature Importance](https://www.kaggle.com/code/codename007/home-credit-complete-eda-feature-importance) — Lathwal | Cơ bản–trung bình | Đọc sau Gentle Introduction để mở rộng EDA sang toàn bộ bảng; dùng để học cách đặt câu hỏi, không sao chép feature-importance workflow. |
| 3 | [Credit Risk EDA: Defaults, Segments & Trends](https://www.kaggle.com/code/beatafaron/credit-risk-eda-defaults-segments-trends-1) — Beata Faron | Trung bình, đọc phản biện | Đọc sau target/window và validation; dùng dataset Lending Club riêng để học segment/WOE/trend và nhận diện outcome leakage. |

Ngày truy cập và rà soát nội dung: **2026-07-29**.

## Phân tích giá trị notebook

### 1. Start Here: A Gentle Introduction

**Nội dung chính**

1. Giới thiệu bài toán phân loại nhị phân Home Credit Default Risk và metric ROC-AUC.
2. Khảo sát bảng `application_train`/`application_test`: mất cân bằng target, missing value, kiểu dữ liệu và biến categorical.
3. Minh họa label encoding, one-hot encoding và căn chỉnh cột train/test.
4. Phát hiện giá trị bất thường của `DAYS_EMPLOYED`, tạo cờ anomaly và thay giá trị bất thường bằng missing.
5. Phân tích correlation, tuổi và các biến `EXT_SOURCE`.
6. Thử polynomial features và các tỷ lệ có ý nghĩa nghiệp vụ như credit/income, annuity/income và employed/age.
7. Xây Logistic Regression baseline, Random Forest, feature importance và phần LightGBM mở rộng với cross-validation.

**Giá trị học tập**

- **Rất phù hợp để nhập môn:** trình bày một vòng đời ML tabular hoàn chỉnh bằng một bảng dữ liệu, đủ đơn giản để người mới theo dõi.
- **Tốt cho tư duy baseline:** bắt đầu từ Logistic Regression rồi mới tăng độ phức tạp; giúp tách giá trị của preprocessing, feature và model.
- **Tốt cho EDA có mục đích:** các bước missingness, anomaly, target rate và correlation đều được nối với quyết định modeling.
- **Có giá trị cho credit scoring:** giới thiệu class imbalance, xác suất dự đoán, ROC-AUC và các ratio feature có thể diễn giải.
- **Là cầu nối sang dữ liệu nhiều bảng:** notebook cố ý chỉ dùng bảng application, phù hợp làm nền trước khi học aggregation từ bureau, installments và previous applications.

**Giới hạn và cách đọc có phản biện**

- Notebook phục vụ competition, vì vậy leaderboard score không thay thế validation phù hợp với production, calibration, threshold hay business simulation.
- Phần LightGBM dùng random `KFold`; không nên sao chép làm validation strategy cho dữ liệu có thời gian. Project này vẫn tuân theo temporal/OOT validation đã phê duyệt.
- Logistic Regression và Random Forest ban đầu được đánh giá chủ yếu qua submission, chưa có local validation đủ chặt để so sánh model.
- Notebook chỉ dùng bảng application chính nên chưa dạy grain, cardinality, point-in-time join hoặc aggregation an toàn cho sáu bảng phụ.
- Một số API đã cũ, ví dụ `sklearn.preprocessing.Imputer`, `get_feature_names` và cách truyền early stopping của LightGBM; cần chuyển sang API hiện hành khi tái triển khai.
- Correlation và feature importance chỉ cho thấy quan hệ dự đoán, không chứng minh quan hệ nhân quả hoặc tính hợp lệ về fairness.
- Các feature “domain knowledge” là giả thuyết cần kiểm tra về source, formula, availability và leakage trước khi đưa vào registry/production.
- Chưa xác minh license cho việc tái sử dụng code; chỉ dùng notebook như tài liệu học cho đến khi license được kiểm tra.

**Cách học đề xuất**

1. Chạy lại phần đọc dữ liệu và EDA; tự giải thích grain, target và ý nghĩa của missing/anomaly.
2. Tái tạo Logistic Regression bằng pipeline hiện hành và đánh giá trên validation độc lập, không dùng leaderboard làm validation chính.
3. Viết lại anomaly handling và ratio features thành source module có unit test; không giữ logic quan trọng chỉ trong notebook.
4. So sánh baseline với và không có feature mới bằng cùng split và metric đã khóa.
5. Chỉ đọc phần LightGBM sau khi đã hiểu out-of-fold prediction, early stopping và nguy cơ từ random split.

### 2. Home Credit: Complete EDA + Feature Importance

**Giá trị học tập**

- Đọc và kiểm tra missingness trên application cùng sáu bảng lịch sử.
- Gợi ý các lát cắt EDA theo income type, family status, occupation, education, housing và previous applications.
- Hữu ích để luyện báo song song sample count và bad rate theo segment.

**Giới hạn**

- Tên “Complete” không có nghĩa notebook hoàn thiện data mart hoặc validation.
- Category encoder được fit bằng cách ghép giá trị train/test và missing được thay bằng `-999` mà không có semantic review.
- Random Forest được fit trên toàn training set và impurity importance được báo in-sample; không có holdout/permutation/SHAP stability.
- Segment demographic có nguy cơ fairness/proxy; không chuyển thành feature/policy khi chưa được phê duyệt.

### 3. Credit Risk EDA: Defaults, Segments & Trends

**Giá trị học tập**

- Giới thiệu target mapping, missingness, categorical EDA, WOE/IV, segment analysis, feature selection và nhiều model.
- Gợi ý phân tích bad rate theo segment, cohort/vintage và population shift.
- Tốt để luyện phát hiện feature availability và phân biệt application với behavioral/outcome data.

**Giới hạn nghiêm trọng**

- Notebook dùng một dataset Lending Club riêng, không phải Home Credit; không trộn tên cột hoặc kết luận giữa hai schema.
- `Current` và `In Grace Period` được gộp thành good mà chưa chứng minh label maturity; late/default/charged-off được gộp bad mà chưa nêu cure/indeterminate policy.
- WOE/IV và một số bước xử lý được thực hiện trước train/test split.
- Các biến được chọn gồm recoveries, last payment, principal/interest đã thu, late fee, outstanding principal và debt settlement; đây thường là post-outcome leakage cho application scoring.
- Dùng ngày chạy notebook để điền missing date làm feature, khiến kết quả phụ thuộc thời điểm chạy và có thể nhìn vào tương lai.


## Ví dụ trong credit scoring

Tái tạo một baseline nhỏ trong pipeline thay vì giữ logic quan trọng chỉ trong notebook.

## Điều cần kiểm tra trong project

- [ ] Xác minh license và nguồn.
- [ ] Ghi version/ngày truy cập khi thêm link.
- [ ] Không coi nguồn ngoài là xác nhận chính sách FPT.

## Tài liệu liên quan

- [Dataset catalog](../datasets/dataset_catalog.md)
- [Lộ trình](../roadmap/learning_path.md)
- [Reproducibility](../governance/reproducibility.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
