# Dự án Credit Scoring — Báo cáo tuần 13/08/2026

## Mục tiêu

Đánh giá pipeline feature nhiều bảng dùng Spark và Parquet ở mức research
candidate, với contract đầu ra có thể kiểm tra và tái sử dụng.

## Khái niệm chính

Pipeline tách block vật lý theo bảng nguồn khỏi family ngữ nghĩa. Mỗi block có
grain khách hàng, schema cố định, manifest và `builder_version`; Parquet giữ
dtype và missing value để các lượt thử nghiệm sau không phải aggregate lại từ
CSV thô.

## Ví dụ trong credit scoring

Block `bureau` được dùng làm ví dụ parity: builder Spark đọc schema khai báo
trước, aggregate theo `SK_ID_CURR`, rồi đối chiếu với builder pandas về key set,
schema, family, null mask và giá trị trước khi được xem xét để promotion.

## Mục tiêu tuần

1. Nghiên cứu và áp dụng Spark vào pipeline xử lý feature, thay cho giới hạn bộ nhớ của pandas khi dữ liệu nhiều bảng có quy mô lớn.
2. Chuẩn hóa việc nhận dữ liệu mẫu mới: phân nhóm feature, tự động build các block theo schema cố định và xuất Parquet để dùng cho feature engineering hoặc ghép vào model.
3. Bổ sung các chốt kiểm soát để pipeline có thể lặp lại an toàn khi nhận dữ liệu gốc.

## Tóm tắt điều hành

Đã hoàn thành Spark parity cho block `bureau`: Spark tạo đúng **61 feature** trên **305.811** khách hàng, khớp pandas về key set, schema, thứ tự cột, family, null mask và giá trị; kết quả full comparison có **0 value mismatch**, **0 infinity**, sai khác tuyệt đối lớn nhất ở fixture là `7,95e-08`.

Pipeline feature hiện tổ chức theo block Parquet và manifest. Khi nhận dữ liệu có cùng contract, các bảng phụ được đọc bằng schema khai báo trước, build thành block ở grain khách hàng, kiểm khóa duy nhất, rồi ghi Parquet không overwrite. Output có thể dùng lại cho feature engineering hoặc merge vào application/model matrix.

Không chạy huấn luyện model mới trong tuần này, nên **không có AUC mới và không kết luận cải thiện model**. Các con số tốc độ trong mục 4 là benchmark Parquet đã được đo ở tuần 06/08; chúng được giữ lại để thể hiện hiệu quả vận hành của pipeline, không phải benchmark Spark mới.

## 1. Công việc đã hoàn thành

### 1.1 Áp dụng Spark vào pipeline feature

Đã triển khai Spark candidate cho các block bảng phụ Home Credit: `bureau`, `previous_application`, `installments_payments`, `credit_card_balance` và `POS_CASH_balance`. Các builder giữ schema đầu ra cố định, không suy luận danh sách cột từ sample, và ghi kết quả thành Spark Parquet kèm manifest.

Block `bureau` là block đã có full parity được xác minh với pandas `bureau-v1`. Luồng xử lý là:

`CSV thô → Spark schema rõ ràng → aggregate theo hợp đồng → client-level feature block → Parquet + manifest → merge vào model matrix`

Ba quy tắc nghiệp vụ được giữ nhất quán giữa Spark và pandas:

- `STATUS="X"` là không quan sát được, không được tính như tháng không quá hạn.
- Tổng amount của nhóm toàn null giữ `NaN`; count mới được điền 0 khi không có bản ghi.
- Tỷ lệ có mẫu số 0/null trả `null`; không tự clip giá trị âm.

### 1.2 Tự động hóa feature group cho dữ liệu mẫu mới

Đã tổ chức feature theo hai lớp:

| Lớp | Cách tổ chức | Mục đích |
|---|---|---|
| Block vật lý | Theo bảng nguồn: `bureau`, `previous_application`, `installments`, `credit_card`, `pos_cash` | Build và lưu độc lập, dễ thay thế một bảng khi nhận dữ liệu mới |
| Family ngữ nghĩa | `counts`, `amounts`, `recency`, `delinquency` | Chọn/so sánh nhóm feature xuyên nhiều bảng mà không phải tính lại block |

Family được khai báo cùng nơi sinh feature và được ghi vào manifest. Vì vậy, khi nhận dữ liệu gốc có cùng schema, pipeline không cần phân loại thủ công từng cột: builder sinh block, manifest giữ thứ tự cột/family/version, và bước merge chỉ nhận các block đã qua kiểm tra.

Tổng contract hiện có **261 feature** từ năm bảng phụ: Bureau 61, Previous Application 45, Installments 86, Credit Card 36 và POS-CASH 33. Đây là research candidate; chưa có feature nào được mô tả là production.

### 1.3 Chuẩn đầu ra để ghép model

Mỗi block output có một dòng cho mỗi `SK_ID_CURR`, file Parquet và manifest JSON. Trước khi ghi/đọc lại, pipeline kiểm tra:

1. `builder_version` phải khớp để tránh dùng cache của công thức cũ.
2. Tập cột và thứ tự cột phải khớp manifest.
3. Số dòng và khóa khách hàng phải hợp lệ; block ở grain khách hàng không được trùng khóa.
4. Merge từ chối tên feature trùng thay vì tự thêm hậu tố khó truy vết.

Nhờ đó, Parquet output có thể làm đầu vào cho hai hướng: feature engineering/ablation theo family hoặc ghép trực tiếp vào application matrix để train/inference.

## 2. Kết quả kiểm chứng Spark

| Hạng mục | Kết quả đã xác minh |
|---|---|
| Runtime smoke | Hoàn tất trên Spark `4.0.2` với full raw-data smoke |
| Quy mô block Bureau | 305.811 dòng / khóa khách hàng duy nhất |
| Schema | 61 feature; schema, thứ tự cột và family mapping khớp pandas |
| Đối chiếu giá trị | 0 value mismatch, 0 infinity, `rtol=1e-5`, `atol=1e-6` |
| Fixture parity | 0 null mismatch; max absolute difference `7,95e-08` |
| An toàn ghi file | Candidate Spark ghi Parquet + manifest riêng và từ chối overwrite |

Kết quả trên chứng minh **tương đương kết quả feature** cho Bureau, không phải benchmark hiệu năng. Spark candidate vẫn cần review riêng trước khi thay pandas reference hoặc được promote.

## 3. Ý nghĩa khi nhận dữ liệu gốc

Khi nhận dữ liệu gốc, quy trình dự kiến không cần sửa tay theo từng bảng:

1. Đọc CSV bằng schema/dtype đã khai báo.
2. Chạy builder theo từng bảng nguồn để sinh feature block Parquet.
3. Đọc lại block với `expected_builder_version` và kiểm manifest.
4. Merge block vào application matrix hoặc chọn family để thử nghiệm feature engineering.

Điểm cần xác nhận trước khi chạy dữ liệu gốc là mapping giữa tên cột/khóa thực tế và contract hiện tại. `TODO(FPT): cần xác nhận với mentor hoặc data owner.`

## 4. Các con số cải thiện vận hành

Các số sau là benchmark đã được xác minh trên tuần 06/08 cho cùng năm block feature; không phải kết quả đo Spark trong tuần này.

| Hoạt động | Trước | Sau | Cải thiện |
|---|---:|---:|---:|
| Tạo lại 5 block từ CSV thô so với đọc lại Parquet | 1.098s | 0,70s | khoảng **1.560×** nhanh hơn khi tái sử dụng feature đã tính |
| Đọc cùng 5 block từ CSV so với Parquet | 9,30s | 0,70s | khoảng **13×** nhanh hơn |
| Dung lượng lưu 5 block | 355,0 MB | 106,5 MB | nhỏ hơn **3,3×** |

Ý nghĩa thực tế là các lần thử model không cần lặp lại aggregate trên dữ liệu thô. Spark giải quyết bước build trên dữ liệu lớn; Parquet làm cho bước dùng lại feature sau đó nhanh, giữ dtype và giữ `NaN` đúng nghĩa.

## 5. Khó khăn và kiểm soát rủi ro

- Spark không được coi là thay thế hoàn toàn pandas chỉ vì code chạy được. Mỗi block cần parity với reference, kiểm schema/key/null/infinity và kiểm thử fixture trước khi dùng dữ liệu thật.
- Các Spark adapter cho bốn block ngoài Bureau vẫn là research candidate; cần chạy parity đầy đủ trên block reference trước khi promotion.
- Dữ liệu sample/gốc không được đưa vào Git, prompt hay báo cáo. Report chỉ ghi contract và metric tổng hợp, không ghi PII.
- Không dùng kết quả Kaggle hay test để chọn feature. Nếu chạy ablation/model mới phải đăng ký experiment riêng trước.

## 6. Công việc bổ sung đề xuất cho tuần kế tiếp

Các mục này là đề xuất mở rộng hợp lý, chưa được ghi nhận là đã hoàn thành:

1. **Data contract check khi nhận file mới:** xuất bảng schema, tỷ lệ null, số khóa trùng và coverage join trước khi build feature. Điều này giúp phát hiện dữ liệu nguồn đổi cột/đổi grain từ đầu.
2. **Parity đầy đủ cho bốn block Spark còn lại:** so key set, schema, null mask, giá trị và manifest với pandas reference; sau đó mới cân nhắc promotion từng block.
3. **Đo hiệu năng công bằng Spark-vs-pandas:** dùng cùng raw data, cùng máy/cấu hình, báo cáo thời gian đọc, build, peak memory và kích thước output. Chỉ sau phép đo này mới được nói Spark nhanh hơn bao nhiêu.
4. **Pre-registration E04:** paired ablation theo từng block và từng family, dùng cùng fold list với E01 để biết block nào đóng góp thực sự vào OOF AUC.
5. **Automation runbook:** một entry point nhận đường dẫn dữ liệu, schema profile, build Parquet, validate manifest và xuất merge-ready matrix; log phiên bản builder để tái lập.

## Điều cần kiểm tra trong project

- Xác nhận mapping tên cột, khóa và time semantics của dữ liệu thực tế trước khi
  build block.
- Kiểm tra `builder_version`, cardinality, schema/order, null mask và infinity
  sau mỗi block; không dùng kết quả chưa có artifact truy vết để chọn feature.
- Chỉ promotion sau khi parity, review owner và validation experiment riêng đã
  hoàn tất.

## Trạng thái áp dụng trong project

Pipeline Spark/Parquet đã sẵn sàng ở mức research candidate cho workflow dữ liệu nhiều bảng. Bureau có bằng chứng parity đầy đủ; các block Spark khác đã có khung xử lý và cần validation tương tự. Chưa thay target, metric, validation strategy hoặc kết luận hiệu quả model.

## Tài liệu liên quan

- [Báo cáo feature store và feature phụ tuần 06/08](../06_08_2026/feature_store_and_auxiliary_features_report.md)
- [Spark Bureau parity candidate](../../features/home_credit_bureau_spark.md)
- [Feature store](../../features/feature_store.md)
- [Experiment log](../experiment_log.md)
