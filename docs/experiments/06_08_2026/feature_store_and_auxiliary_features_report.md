# Dự án Credit Scoring — Báo cáo tuần 06/08/2026

## Mục tiêu

Ghi lại công việc tuần: feature engineering cho năm bảng phụ Home Credit, cơ chế
lưu dữ liệu đã xử lý để giảm thời gian upload và tính lại, và lượt chạy
end-to-end trên toàn bộ dữ liệu.

## Khái niệm chính

Một **feature block** là ma trận feature ở grain `SK_ID_CURR`, lưu thành một file
Parquet kèm một manifest JSON ghi key column, thứ tự cột, nhóm ngữ nghĩa của từng
feature và `builder_version` của code đã sinh ra chúng.

Block tách việc **tính** feature khỏi việc **dùng** feature. Trước đây mỗi lượt
thử nghiệm phải đọc và tổng hợp lại toàn bộ dữ liệu thô; nay chỉ đọc kết quả đã
tính sẵn.

Kết quả OOF trong báo cáo này đến từ một lượt chạy gộp toàn bộ feature, không
phải paired ablation, nên không dùng để chọn hay loại bất kỳ feature nào.

## Ví dụ trong credit scoring

Khách hàng `100002` có 8 khoản vay trong `bureau.csv` và 110 dòng lịch sử tháng
trong `bureau_balance.csv`. Sau xử lý còn **một dòng, 61 cột**, trong đó có những
đặc trưng không tồn tại ở dữ liệu gốc dưới bất kỳ dạng nào:

| Feature | Giá trị | Ý nghĩa |
|---|---|---|
| `BUREAU_BB_DPD_MONTH_SHARE_MEAN` | 0,299 | 30% số tháng bị trễ hạn |
| `BUREAU_BB_LONGEST_DPD_STREAK_MAX` | 2 | Trễ liên tiếp dài nhất 2 tháng |
| `BUREAU_BB_DPD_EPISODES_SUM` | 14 | Có 14 đợt trễ riêng biệt |

Ba con số này cho biết khách trễ **thường xuyên nhưng ngắn** — trễ rồi trả ngay,
lặp lại nhiều lần. Hồ sơ này khác hẳn một khách có cùng tổng số tháng trễ nhưng
dồn vào một đợt kéo dài, và sự khác biệt đó chỉ hiện ra sau khi tính.

## 1. Mục tiêu công việc

1. Feature engineering cho năm bảng phụ Home Credit: `bureau`,
   `previous_application`, `installments_payments`, `credit_card_balance`,
   `POS_CASH_balance`.
2. Tìm cách lưu dữ liệu đã xử lý để giảm thời gian upload và tính lại feature.
3. Chạy end-to-end trên toàn bộ dữ liệu và sinh file submission hợp lệ.

## 2. Công việc đã hoàn thành

### 2.1 Feature engineering cho năm bảng phụ

Xây năm module feature trong `src/credit_scoring/features/`, mỗi module nhận
bảng thô và trả về ma trận một dòng mỗi khách hàng kèm nhãn nhóm cho từng cột.

| Block | Feature | Nội dung |
|---|---|---|
| `bureau` | 61 | Lịch sử tín dụng tại tổ chức khác: dư nợ, hạn mức, tháng trễ hạn |
| `previous_application` | 45 | Lịch sử xin vay tại Home Credit: tỷ lệ duyệt, số lần bị từ chối |
| `installments` | 86 | Hành vi trả nợ thực tế, kèm cửa sổ 60/90/180/365 ngày |
| `credit_card` | 36 | Mức sử dụng thẻ tín dụng, tỷ lệ dùng trên hạn mức |
| `pos_cash` | 33 | Trả góp tại điểm bán, trạng thái hoàn thành hợp đồng |

Tổng **261 feature**, chia bốn nhóm ngữ nghĩa: `delinquency` 99, `amounts` 88,
`counts` 63, `recency` 11.

Các bảng có nhiều dòng cho một hợp đồng được gom hai tầng — dòng tháng lên hợp
đồng, rồi hợp đồng lên khách hàng — thay vì gom thẳng lên khách hàng. Gom thẳng
sẽ khiến hợp đồng dài lấn át hợp đồng ngắn chỉ vì nó có nhiều dòng hơn.

Trước khi viết code chính thức, em chạy thử toàn bộ đường ống trên mẫu 5.000
train và 2.000 test lấy từ dữ liệu thật. Lượt chạy thử này phát hiện bốn lỗi
trong code nguồn, tất cả đã sửa:

| Lỗi | Hậu quả nếu không sửa |
|---|---|
| `sum()` không có `min_count=1` | Khách không có dữ liệu nợ bị ghi `SUM = 0` trong khi `MEAN = NaN` trên cùng cột; "không rõ dư nợ" và "dư nợ bằng 0" bị nhập làm một |
| Danh sách cột phụ thuộc dữ liệu | Block ghi từ mẫu không ghép được với block ghi từ full data, và manifest không phát hiện được vì cả hai file đều tự nhất quán |
| Tên feature chứa dấu phẩy | LightGBM từ chối chạy |
| Xu hướng sắp xếp mới-nhất-trước | Dấu hệ số góc bị đảo ngược |

### 2.2 Lưu dữ liệu đã xử lý vào block Parquet

Xây `credit_scoring.feature_store`. Mỗi block gồm một file Parquet và một
manifest, với bốn chốt kiểm tra khi đọc lại: `builder_version` khớp, tập và thứ
tự cột khớp manifest, số dòng khớp, khóa duy nhất.

`builder_version` là chốt quan trọng nhất. Feature code thay đổi thường xuyên hơn
dữ liệu thô, và một cache trả về giá trị của công thức cũ không làm gì hỏng theo
cách nhìn thấy được: không có lỗi, không có cảnh báo, chỉ là những con số sai.

Block chia theo bảng nguồn, còn nhóm ngữ nghĩa là nhãn trong manifest. Một feature
thuộc đúng một bảng, nhưng một nhóm ngữ nghĩa có thể trải nhiều bảng, nên chia
file theo nhóm sẽ khiến mỗi lần thêm bảng phải sửa lại mọi file nhóm.

### 2.3 Chạy end-to-end từ dữ liệu đã lưu

Ghép năm block lên ma trận E01 application đã khóa, chạy 5-fold LightGBM với đúng
cấu hình E01, xuất file submission. Ma trận cuối cùng có **410 feature × 307.511
dòng**, đỉnh bộ nhớ 2,7 GB trên máy 16 GB.

## 3. Kết quả thực nghiệm end-to-end trên Home Credit

### 3.1 Thời gian

Có hai phép so sánh khác nhau, không nên gộp làm một.

**Đọc block đã lưu, thay vì tính lại từ CSV thô:**

| | Thời gian |
|---|---|
| Build năm block từ CSV thô | 1.098s (18 phút 18) |
| Đọc năm block từ Parquet | 0,70s |
| **Nhanh hơn** | **khoảng 1.560 lần** |

Phần tiết kiệm này chủ yếu đến từ việc bỏ hẳn bước tổng hợp hơn 30 triệu dòng,
không phải từ bản thân định dạng Parquet.

**Lưu chính năm block đó bằng Parquet thay vì CSV:**

| | CSV | Parquet |
|---|---|---|
| Đọc năm block | 9,30s | 0,70s |
| Ghi năm block | 52,0s | gần như tức thì |
| **Nhanh hơn** | | **13 lần** |

Đây mới thuần là công của định dạng. Ngoài tốc độ, Parquet còn giữ nguyên kiểu dữ
liệu: qua CSV một vòng thì `int32` thành `int64` và `category` thành `object`, nên
`categorical_features` của LightGBM phải cast lại thủ công mỗi lần chạy.

### 3.2 Dung lượng

| | Dung lượng |
|---|---|
| CSV | 355,0 MB |
| Parquet | 106,5 MB |
| **Chênh lệch** | **3,3 lần** |

### 3.3 Kết quả model

| Cấu hình | Số feature | OOF ROC-AUC |
|---|---|---|
| E01 application-only (baseline đã khóa) | 149 | 0.768696 |
| E01 + năm block feature phụ | 410 | **0.793570** |

Fold AUC: 0.789722 / 0.799113 / 0.792266 / 0.796997 / 0.789945; độ lệch chuẩn
0.004246. Năm fold nằm gọn trong khoảng hẹp, không có fold nào lệch bất thường.

File submission 48.744 dòng đã sinh và qua kiểm schema, chưa nộp.

### 3.4 Cách đọc con số này

Đây **không phải kết quả experiment**, vì ba lý do:

1. Cả 261 feature vào một lượt, nên chênh lệch `+0.0249` không quy được cho bảng
   nào. Có thể một bảng đóng góp gần hết, cũng có thể một bảng đang làm hại mà bị
   bảng khác che.
2. Số cột khác nhau (410 so với 149). Nhiều feature hơn thì AUC cao hơn là chuyện
   thường, không nói lên chất lượng feature.
3. Không thuộc E03. E03 đang khóa pre-registration với 36 candidate bureau riêng,
   bộ feature này khác hẳn.

Điều lượt chạy này thật sự chứng minh: đường ống chạy thông từ CSV thô đến file
nộp được, và bộ feature phụ có tín hiệu chứ không phải nhiễu.

## 4. Khó khăn gặp phải

### 4.1 Bộ nhớ khi xử lý bảng lớn

`bureau_balance.csv` có 27,3 triệu dòng. Đọc bằng cấu hình mặc định của pandas
cho một frame **1.927 MB**, trên máy 16 GB đang chạy sẵn nhiều ứng dụng thì hệ
điều hành phải dùng swap và tốc độ giảm rõ rệt.

Cách xử lý: khai `dtype` ngay trong `read_csv` thay vì đọc xong mới downcast.
Điểm mấu chốt là đỉnh bộ nhớ nằm ở lúc đọc — downcast sau vẫn phải dựng frame
64-bit trước đã, tức là vẫn chạm đỉnh. Riêng cột `STATUS` chuyển sang `category`
đã đóng góp phần lớn mức giảm, vì nó chỉ có tám giá trị khác nhau trên 27 triệu
dòng.

Kết quả: **1.927 MB xuống 182 MB**, cùng thời gian đọc. Đỉnh bộ nhớ cả lượt build
là 2,7 GB.

### 4.2 Lỗi không lộ ra khi chạy

Ba trong bốn lỗi ở mục 2.1 đều làm chương trình dừng hoặc cho kết quả nhìn thấy
được ngay. Riêng lỗi danh sách cột phụ thuộc dữ liệu thì không: nó chạy trơn tru,
không báo gì, và mỗi file kết quả đều tự nhất quán. Nó chỉ lộ ra khi đọc kỹ từng
dòng code để chuyển sang repo, không lộ ra qua bất kỳ lượt chạy nào.

Đây là loại lỗi đáng lo nhất vì nó im lặng. Cách phòng đã áp dụng: mỗi builder có
một test chạy trên hai tập khách hàng khác nhau và bắt buộc hai lần cho ra đúng
cùng danh sách cột.

### 4.3 Xung đột với quy tắc đang có của repo

`AGENTS.md` có quy tắc cấm thêm module gắn với dataset vào `src/`, trong khi công
việc tuần này cần đưa khoảng 1.500 dòng feature engineering vào đúng chỗ đó.

Em không lách quy tắc mà viết ADR-0004 ghi lại việc đổi quy tắc kèm lý do, rồi
cập nhật `AGENTS.md` cho khớp. Ranh giới mới lấy **tính tái sử dụng** làm tiêu
chí thay vì lấy dataset: hàm nào dùng lại được thì thuộc source và phải có test.
Nếu để code và quy tắc mâu thuẫn nhau thì người đọc repo sau này không biết bên
nào đúng.

### 4.4 Một bảng chạy chậm hơn hẳn

`installments` chiếm 492s trong tổng 1.098s build, gần bằng bốn bảng còn lại cộng
lại. Nghi ngờ nằm ở hai hàm tính chuỗi trễ hạn liên tiếp, vì chúng chạy vòng lặp
Python trên hơn 800 nghìn nhóm. **Chưa đo để xác nhận**, nên chưa tối ưu — sửa
theo phỏng đoán dễ mất công vào chỗ không phải nút thắt.

### 4.5 Chưa quy được đóng góp cho từng bảng

Lượt chạy end-to-end đưa cả 261 feature vào một lượt nên không tách được đóng góp
của từng bảng. Đây là hạn chế của thiết kế thử nghiệm chứ không phải của dữ liệu,
và là lý do mục 5.1 được xếp ưu tiên cao nhất.

## 5. Đề xuất công việc tiếp theo

### 5.1 E04 — paired ablation theo từng block (ưu tiên cao nhất)

Chạy mỗi block một cấu hình trên **cùng một danh sách fold**, so từng cặp với
baseline E01. Đây là phép đo duy nhất trả lời được câu "bảng nào đáng giữ", và hạ
tầng đã sẵn sàng: `run_ablation` có sẵn, năm block đã nằm trên đĩa, chi phí đọc
lại gần bằng không.

Cần làm trước khi chạy:

- Viết pre-registration khóa ngưỡng delta OOF AUC và số fold dương tối thiểu, theo
  đúng mẫu E03.
- Ghi rõ rằng ngưỡng không được sửa sau khi nhìn thấy kết quả.

Sau khi có kết quả từng block, chạy thêm ablation theo **nhóm ngữ nghĩa** xuyên
bảng (`delinquency`, `amounts`, `recency`, `counts`) — manifest đã mang sẵn nhãn
nên không phải tính lại gì.

### 5.2 Đưa application features thành block thứ sáu

Hiện 149 feature E01 vẫn tính lại mỗi lượt chạy, mất khoảng 30 giây. Đưa vào
block sẽ khiến toàn bộ bước feature engineering về gần bằng không.

Cần thận trọng vì đây là baseline đã khóa ở `0.768696`: phải chứng minh block cho
ra đúng cùng ma trận trước khi thay thế, không được để lệch dù một cột.

### 5.3 Đo rồi mới tối ưu `installments`

Chạy profiler xác định nút thắt thật, rồi mới quyết định có vector hóa hai hàm
chuỗi hay không. Mức lợi tối đa là khoảng 7 phút mỗi lần build lại, mà build lại
chỉ xảy ra khi sửa công thức — nên việc này xếp sau 5.1.

### 5.4 Hoàn thiện quy trình

- Đưa ADR-0004 ra review với mentor; hiện mới ở mức repo owner chấp thuận.
- Xác nhận với mentor các quy ước missing policy đang áp dụng, đặc biệt quy tắc
  count điền 0 còn amount giữ `NaN`.
- Cân nhắc mở rộng cách làm này sang bộ dữ liệu Credit Risk Model Stability, vì
  `feature_store` không phụ thuộc dataset nào.

## Điều cần kiểm tra trong project

- [x] Mọi feature code trong source có test; `pytest` 110 passed.
- [x] Danh sách cột block không đổi giữa mẫu và full data, có test bảo vệ.
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

Năm block đã build trên toàn bộ dữ liệu và dùng được ngay. Feature trong báo cáo
này là research candidate, chưa qua ablation nên chưa feature nào được chọn hay
loại, và không thuộc E03. Lượt chạy end-to-end là kiểm chứng đường ống, không
phải experiment; leaderboard không tham gia quyết định chọn feature.
