# Dự án Credit Scoring — Báo cáo tuần 06/08/2026

## Mục tiêu

Ghi lại công việc tuần: tái sử dụng feature engineering cho năm bảng phụ Home
Credit, xây cơ chế lưu feature đã tính, và chạy end-to-end trên full data để kiểm
chứng đường ống.

## Khái niệm chính

Một **feature block** là ma trận feature ở grain `SK_ID_CURR`, lưu thành Parquet
kèm manifest ghi key column, thứ tự cột, family từng feature và `builder_version`.
Block tách việc **tính** feature khỏi việc **dùng** feature: tính một lần, dùng
nhiều lần.

Kết quả OOF trong báo cáo này đến từ một lượt chạy gộp toàn bộ feature, không
phải paired ablation, nên không dùng để chọn hay loại feature nào.

## Ví dụ trong credit scoring

`BUREAU_AMT_CREDIT_SUM_DEBT_SUM` dùng `sum(min_count=1)`. Khách không có bản ghi
dư nợ nào giữ `NaN` thay vì `0`, để "không biết nợ bao nhiêu" không bị nhập làm
một với "nợ bằng 0" — hai nhóm có rủi ro khác hẳn nhau.

## 1. Mục tiêu công việc

1. Tái sử dụng feature engineering từ repo nhóm cho các bảng phụ Home Credit, kết
   hợp với bộ module reusable đã có.
2. Xây cơ chế lưu feature đã tính để không phải xử lý lại mỗi lần thử nghiệm.
3. Chia feature theo nhóm ngữ nghĩa, làm nền cho việc đo đóng góp từng nhóm.
4. Chạy end-to-end trên toàn bộ dữ liệu Home Credit và sinh file submission hợp lệ.

## 2. Công việc đã hoàn thành

### 2.1 Kiểm chứng trước khi tích hợp

Em dựng mẫu 5.000 train và 2.000 test từ dữ liệu thật với ID nhất quán qua cả bảy
bảng, rồi chạy thử toàn bộ đường ống trước khi viết code chính thức. Các module FE
ghép được vào `PreparedDataset` và `run_ablation` có sẵn mà không phải sửa gì.

Quá trình này phát hiện bốn lỗi trong code nguồn, tất cả đã sửa khi port:

| Lỗi | Hậu quả |
|---|---|
| `sum()` không có `min_count=1` | Khách không có dữ liệu nợ bị ghi `SUM = 0` trong khi `MEAN = NaN` trên cùng cột |
| Schema phụ thuộc dữ liệu | Block ghi từ mẫu không ghép được với block ghi từ full data |
| Tên feature chứa dấu phẩy | LightGBM từ chối chạy |
| Trend sắp xếp mới-nhất-trước | Dấu hệ số góc bị đảo ngược |

Lỗi thứ hai nghiêm trọng nhất vì nó phá chính mô hình block: hai file đều tự nhất
quán nên manifest không phát hiện được.

### 2.2 Module mới trong source

- `credit_scoring.feature_store` — lưu và đọc block Parquet kèm manifest, có bốn
  chốt kiểm tra khi load: `builder_version`, tập và thứ tự cột, số dòng, khóa duy nhất.
- Năm module feature cho `bureau`, `previous_application`, `installments`,
  `credit_card`, `pos_cash`, cùng một module aggregation dùng chung.
- `compact_home_credit_dtypes` — khai dtype ngay lúc parse thay vì downcast sau,
  giảm `bureau_balance` từ 1.927 MB xuống 182 MB.

Tổng 48 test mới; toàn repo hiện có 110 test.

### 2.3 Chuẩn hóa quy trình

- `AGENTS.md` viết lại ranh giới source/notebook theo tiêu chí **tái sử dụng**
  thay vì theo dataset, kèm chín yêu cầu bắt buộc với feature code trong source.
- ADR-0004 ghi lại quyết định đổi ranh giới, trạng thái Accepted bởi repo owner.
- Feature registry thêm 17 entry theo family; tài liệu 320 dòng feature được
  **sinh tự động từ khai báo trong code** nên không thể lệch khỏi code đang chạy.

## 3. Kết quả thử nghiệm end-to-end

Chạy trên toàn bộ dữ liệu Home Credit:

| Block | Khách hàng | Feature | Build | Parquet |
|---|---|---|---|---|
| `bureau` | 305.811 | 61 | 284s | 27,5 MB |
| `previous_application` | 338.857 | 45 | 145s | 32,2 MB |
| `installments` | 339.587 | 86 | 492s | 29,4 MB |
| `credit_card` | 103.558 | 36 | 85s | 8,5 MB |
| `pos_cash` | 337.252 | 33 | 92s | 9,0 MB |

Tổng 18 phút 18 giây cho lần build đầu, ra 106,6 MB Parquet; đọc lại dưới một giây.

Cả năm block cho **đúng cùng số cột** khi chạy trên mẫu 7.000 khách và trên hơn
300.000 khách — xác nhận lỗi schema đã được sửa thật.

### Kết quả model

| Cấu hình | OOF ROC-AUC |
|---|---|
| E01 application-only (baseline đã khóa) | 0.768696 |
| E01 + năm block feature phụ (410 feature) | 0.793570 |

Fold AUC: 0.789722 / 0.799113 / 0.792266 / 0.796997 / 0.789945; độ lệch chuẩn
0.004246. File submission 48.744 dòng đã sinh và qua kiểm schema, chưa nộp.

**Cách đọc con số này.** Đây không phải kết quả experiment. Cả 261 feature vào một
lượt nên chênh lệch `+0.0249` không quy được cho bảng nào; số cột cũng khác nhau
(410 so với 149) nên không phải so sánh có kiểm soát. Nó chứng minh đường ống chạy
thông và bộ feature phụ có tín hiệu, không kết luận feature nào đáng giữ.

### Hiệu quả về thời gian

| | Trước | Sau |
|---|---|---|
| Mỗi lần thử nghiệm mới | 18 phút xử lý lại | dưới 1 giây |
| Dung lượng lưu trung gian | ~320 MB (CSV) | 106,6 MB (Parquet) |
| Đỉnh RAM khi build | — | 2,7 GB trên máy 16 GB |

## 4. Kế hoạch tiếp theo

1. **E04 với paired ablation** — mỗi block một cấu hình trên cùng fold, so từng
   cặp với baseline. Đây mới là phép đo trả lời được "bảng nào đáng giữ". Cần
   pre-registration khóa ngưỡng và cách đếm fold trước khi chạy.
2. Cân nhắc biến application features thành block thứ sáu để bỏ nốt bước tính lại.
3. Tối ưu phần chậm trong `installments`, hiện chiếm 8 phút trong 18 phút build.
4. Đưa ADR-0004 ra review với mentor; hiện mới ở mức repo owner chấp thuận.

## Điều cần kiểm tra trong project

- [x] Mọi feature code trong source có test; `pytest` 110 passed.
- [x] Schema block không đổi giữa mẫu và full data, có test bảo vệ.
- [x] Feature registry và tài liệu feature cập nhật cùng thay đổi code.
- [x] Dữ liệu, block và file submission không commit vào git.
- [ ] Chạy paired ablation trước khi kết luận về bất kỳ feature nào.
- [ ] Không ghi kết quả lượt chạy này vào E03; E03 đang khóa pre-registration.

## Tài liệu liên quan

- [Feature store](../../features/feature_store.md)
- [Home Credit auxiliary features](../../features/home_credit_auxiliary_features.md)
- [ADR-0004](../../decisions/0004-auxiliary-feature-modules-in-source.md)
- [Experiment log](../experiment_log.md)
- [E03 screening pre-registration](../e03_screening_preregistration.md)

## Trạng thái áp dụng trong project

Năm block đã build trên full data và dùng được ngay. Feature trong báo cáo này là
research candidate, chưa qua ablation nên chưa feature nào được chọn hay loại, và
không thuộc E03. Lượt chạy end-to-end là kiểm chứng đường ống, không phải
experiment; leaderboard không tham gia quyết định chọn feature.
