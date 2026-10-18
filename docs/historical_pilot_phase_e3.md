# Phase E3 — mở rộng mẫu lịch sử và kiểm toán chất lượng

**Ngày hoàn tất:** 2026-10-15 (giờ Việt Nam)  
**Mục đích:** nghiên cứu/học tập phi thương mại do chủ project xác nhận.  
**Dataset:** [TiniX AI Vietnam Real Estate Listings](https://huggingface.co/datasets/tinixai/vietnam-real-estates), [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).  
**Revision:** `ca3fedcbb089bf65f7e4cfb03316cce4bd0d779f`.  
**Batch:** `tinix-e3-10000-ca3fedcbb089`.

## Kết quả

| Chỉ số | E3 |
|---|---:|
| Source rows đã khảo sát | 10.000 / 3.500.744 |
| Rows mới lấy qua Dataset Viewer `/rows` | 9.000 |
| Rows E2 được tái sử dụng | 1.000 |
| Rows khớp exact tỉnh + quận/huyện cũ + phường/xã Top 50 | 1.258 |
| Địa bàn có ít nhất một candidate | 48 / 50 |
| Candidate duy nhất được lưu trong pilot DB | 1.190 |
| Observation | 1.190 |
| Candidate đủ điều kiện thống kê lịch sử | 468 |
| Candidate bị quarantine vì giá thiếu/không hợp lệ | 67 |
| Exact duplicate theo normalized content | 1 |
| Possible duplicate | 0 |
| Nhóm thống kê theo địa bàn + loại + tháng | 315 |
| Batch trong pilot database | 2 (E2 và E3) |

1.145 rows khớp địa bàn thuộc 9.000 rows mới của E3; 113 rows khớp đã có trong
batch E2. Từ 1.258 rows khớp, hệ thống giữ 1.190 candidate duy nhất, quarantine
67 rows thiếu/không hợp lệ về giá và nhận diện một nội dung trùng. Có 48 target
có dữ liệu; rank 17 và 22 chưa xuất hiện trong mẫu. Việc không có dữ liệu trong
mẫu không chứng minh địa bàn không có tin.

## Provenance và lấy mẫu

Phase E2 **không** lấy 1.000 dòng đầu tiên và cũng không phải mẫu ngẫu nhiên
đơn giản. Downloader chọn 10 đoạn chỉ số, mỗi đoạn 100 dòng liên tiếp, với vị
trí tái lập trong 10 phần của dataset. Đây là mẫu dò trải đều theo row index.

E3 giữ nguyên toàn bộ 1.000 row identity E2, sau đó lấy thêm các đoạn không
chồng lấn để có đúng 100 hàng trong mỗi 100 strata bằng nhau trên chỉ số toàn
cục. Vị trí đoạn mới được seed từ revision; sample SHA-256 là
`5d3e9ca9a931465ed897efaff10e37192befee139e6d93ce646ef2d1d331247e`. Dataset
revision được kiểm tra trước và sau quá trình tải. Checkpoint ghi từng stratum;
lượt đầu dừng ở 70 strata do HTTP 429, lượt tiếp tục resume từ checkpoint và
hoàn tất 100 strata. Downloader tôn trọng `Retry-After` và giới hạn tần suất gọi
`/rows`.

Dataset Viewer báo 3.500.744 hàng trên 10 Parquet shards. Downloader chỉ đọc
footer qua HTTP byte-range để biết ranh giới shard, tổng cộng 655.360 byte; mỗi
shard có đúng 1.000 rows trong sample E3. Không tải nội dung shard hay toàn bộ
dataset. Hệ thống không dùng Gemini, Search API, crawler hoặc Task Scheduler.

Phân bố quan sát trong mẫu có 57 tên tỉnh/thành; Hồ Chí Minh và Hà Nội chiếm
7.165/10.000 rows (71,65%).

| Chiều | Phân bố |
|---|---|
| Parquet shard | 1.000 rows cho từng shard `0000.parquet`–`0009.parquet` |
| Tỉnh/thành nhiều nhất | Hồ Chí Minh 3.890; Hà Nội 3.275; Đà Nẵng 514; Bình Dương 452; Khánh Hòa 281 |
| Tháng đăng | 2025-06: 800; 2025-07: 1.000; 2025-08: 1.000; 2025-09: 1.000; 2025-10: 1.300; 2025-11: 1.100; 2025-12: 1.200; 2026-01: 800; 2026-02: 600; 2026-03: 1.200 |

Phân bố theo tỉnh và tháng không đồng đều. E3 chưa dựng được baseline theo tháng
cho toàn bộ 3,5 triệu rows. Vì vậy đây là **mẫu phi xác suất**, không được dùng
để ước lượng tỷ lệ toàn thị trường hoặc tuyên bố đại diện thống kê.

## Data quality

Kiểm toán 10.000 source rows ghi nhận:

| Kiểm tra | Số hàng |
|---|---:|
| Giá thiếu | 630 |
| Giá không hợp lệ | 154 |
| Diện tích thiếu / không hợp lệ | 0 / 0 |
| Ngày đăng thiếu / không hợp lệ | 0 / 0 |
| Tiêu đề thiếu | 1 |
| Có giá và diện tích dương hợp lệ | 9.216 |
| Khớp Top 50 | 1.258 |
| Ngoài Top 50 | 8.742 |
| Candidate bị quarantine vì thiếu/không hợp lệ giá trong Top 50 | 67 |

Trên 9.216 dòng có giá/diện tích hợp lệ, Tukey 1,5×IQR gắn cờ 403 giá/m² cực
trị trong kiểm tra toàn mẫu (Q25 53,20 triệu; Q75 187,50 triệu; upper fence
388,95 triệu VND/m²). Đây chỉ là chẩn đoán phân phối sample; không loại các hàng
này khỏi kho.

Địa bàn được so khớp bằng đủ tỉnh + quận/huyện cũ + phường/xã đã chuẩn hóa;
không chỉ dò tên phường. Không tự điền giá hoặc diện tích. Loại nguồn `Đất`
không được gán `DAT_O`; `Biệt thự/Nhà liền kề` và `Shophouse` giữ ở nhóm cần
review. Dataset không có URL tin riêng, listing ID hoặc trường transaction type.
Tất cả record đều là `HISTORICAL_DATASET_UNVERIFIED`; link dataset không chứng
minh một tin cụ thể.

## Phân loại giao dịch, loại tài sản và rà soát thủ công

Trong 1.190 candidate được lưu:

| `deal_type` / `deal_classification` | Ý nghĩa | Số candidate |
|---|---|---:|
| `EXPLICIT_SALE` / `SALE_CONFIRMED_BY_TEXT` | Tiêu đề có tín hiệu bán rõ | 547 |
| `EXPLICIT_RENT` / `RENT_CONFIRMED_BY_TEXT` | Tiêu đề có tín hiệu cho thuê rõ | 13 |
| `UNCLASSIFIED` / `AMBIGUOUS` | Không đủ dấu hiệu để xác định ý định giao dịch | 627 |
| `AMBIGUOUS` / `CONFLICT` | Có dấu hiệu bán và thuê cùng lúc | 3 |

Phân bố property type lưu trong kho: `NHA_RIENG` 690, `CHUNG_CU` 291, loại
chưa map/needs review 209; `DAT_O` là 0. Trong 547 tiêu đề được rule đánh dấu
bán, 468 vừa có nhóm được hỗ trợ (`NHA_RIENG` hoặc `CHUNG_CU`) vừa đủ điều kiện
thống kê. 79 tiêu đề bán còn lại không vào thống kê vì nhóm tài sản chưa map.

Đã tạo gói rà soát 100 tiêu đề, phân tầng theo địa bàn và nhóm phân loại tại
`outputs/historical_quality/tinix-e3-10000-ca3fedcbb089_title_review.csv`.
Các cột `human_label` và `review_notes` để trống. Chưa có ground truth nên không
tính precision, recall hoặc confusion matrix. Gói rà soát không tự thay đổi nhãn
trong database.

## Dedupe và resume

Source row identity là dataset ID + revision + global row index; shard và vị trí
trong shard được tính từ manifest footer. Identity này chỉ giúp resume và provenance,
không chứng minh hai dòng là cùng một listing.

Trong mẫu E3 có một exact normalized-content duplicate, không có possible duplicate.
Không tạo thêm candidate/observation cho duplicate đó. Re-import mẫu 10.000 rows
lần thứ hai nhận diện lại đủ 10.000 source rows là đã xử lý; candidate và
observation giữ ở 1.190/1.190, thống kê giữ 315 nhóm. Unit tests bổ sung bao phủ
resume, re-import, cross-batch exact/possible duplicate và phân loại `NEEDS_REVIEW`.

## Thống kê lịch sử

Giá/m² được tính bằng Python (`price / area`). Các chỉ số tính riêng theo target,
property type và tháng đăng. Với 315 nhóm tháng:

- 310 nhóm có `n < 5` (443 candidate observations): chỉ tham khảo, có cờ mẫu nhỏ.
- 5 nhóm có `n = 5` (25 observations): cờ độ tin cậy thấp.
- Không có nhóm tháng nào có `n >= 10`.
- 3 nhóm có outlier theo Tukey 1,5×IQR; outlier chỉ được gắn cờ, không xóa.

Tổng hợp mô tả trên 468 candidate đủ điều kiện, vẫn là dữ liệu giá rao lịch sử
phi xác minh:

| Loại | n | Mean (triệu VND/m²) | Mean bỏ IQR (sens.) | Median | P25 | P75 | Min | Max | Outlier chẩn đoán |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `NHA_RIENG` | 312 | 172,96 | 167,97 | 125,91 | 87,26 | 247,57 | 14,16 | 642,86 | 4 |
| `CHUNG_CU` | 156 | 72,45 | 72,91 | 73,25 | 57,40 | 87,67 | 1,35 | 129,57 | 1 |
| `DAT_O` | 0 | — | — | — | — | — | — | — | — |

Các tổng hợp trên gom các tháng để mô tả sample, không phải giá hiện hành. Mean
sensitivity sau khi bỏ outlier giảm khoảng 2,89% với `NHA_RIENG` và tăng khoảng
0,63% với `CHUNG_CU`; đây chỉ là chẩn đoán độ nhạy, không xóa row khỏi kho hoặc
thống kê chính.
Mỗi nhóm tháng giữ mean, mean sensitivity khi có outlier, median, P25, P75,
min/max, n, outlier count, phương pháp và quality flags.

Ví dụ lookup rank 2 `NHA_RIENG` cộng qua các tháng có 13 candidate đủ điều kiện:
mean 131,41 triệu VND/m²; median 126,00; P25 110,00; P75 145,80. Nhãn vẫn ghi
historical sample, asking price, không có URL tin riêng và không phải dữ liệu đã
xác minh.

## Pilot DB và UI/API

- Pilot DB riêng: `state/ward_prices.historical_pilot.sqlite3`.
- Backup trước migration/import: `state/backups/ward_prices.historical_pilot.pre_e3_20261014T181441Z.sqlite3`.
- Backup có `PRAGMA integrity_check=ok`, schema E2 (`user_version=0`) và giữ
  1.000 source rows, 106 candidates/observations, 40 nhóm thống kê, 7 quarantine.
- Sau import: `user_version=3`, 10.000 source rows, 1.190 candidates/observations,
  315 nhóm thống kê, 67 quarantine, hai batch.
- Production DB và demo DB không bị ghi; SHA-256 giữ nguyên lần lượt
  `aea91269621302fc1e9d6ff0889f32178b8b1135d48a6be504b2b2e2e10561f5` và
  `e8fac54ec19237a55a580ce5101903271c286394709ce23a5a85c3fef39e119b`.
- API TestClient trả HTTP 200 cho `/historical-pilot`, assets JS/CSS, overview,
  targets và lookup rank 2. Lookup trả 10.000 sample rows, candidate count,
  mean/median/percentiles và cờ `NOT_CURRENT_VERIFIED`.
- Overview xác nhận `current_verified=false`, `daily_new=false` và
  `ai_context_enabled=false`. UI hiển thị attribution TiniX AI, link dataset,
  CC BY-NC 4.0, revision, provenance, phân bố, coverage, khoảng P25–P75 và cảnh
  báo mẫu nhỏ.

Attribution hiển thị trong UI và tài liệu: TiniX AI, *Tinix Vietnam Real Estate
Listings 2025–2026*, Hugging Face, CC BY-NC 4.0. Dữ liệu chỉ dùng nghiên cứu/học
tập phi thương mại; không promote sang production, AI context hoặc thị trường
hiện hành.

## Kiểm thử

Kết quả chạy thực tế:

- Historical focused suite: **12 passed**, một Starlette/httpx deprecation warning.
- Full WardPriceDaily pytest: **132 passed, 1 failed**. Lỗi duy nhất là test
  collector cũ `tests/test_collectors.py::test_offline_transport_runs_end_to_end_and_is_idempotent`;
  lượt thu thứ hai nhận `candidates_found=1` thay vì 0. Lỗi được tái hiện khi
  chạy riêng và không nằm trong các file E3 thay đổi.
- `ruff check .`: **passed**; `compileall`: **passed**.
- Parent `mkdocs build --strict`: **passed** sau khi thêm ADR-0012 vào nav và
  sửa liên kết evidence. MkDocs vẫn liệt kê một số trang legacy không nằm trong
  nav như thông tin, không có warning strict.
- API/UI TestClient: route trang, JS/CSS, overview, targets và lookup đều HTTP
  200; rank 2 `NHA_RIENG` trả n=13, mean 131,41, median 126,00, P25 110,00 và
  P75 145,80 triệu VND/m².

Bộ kiểm thử historical bao gồm schema migration, import 10.000 rows dạng fixture,
resume sau gián đoạn, import lặp, exact/possible duplicates, whitelist,
deal/property classification, thống kê, outlier, quality review packet, UI API
và attribution. Xem experiment log tại `../../docs/experiments/experiment_log.md`.

## Giới hạn và quyết định mở rộng

Không nên tăng ngay lên 25.000–50.000 hàng trước khi người quản lý rà soát 100
tiêu đề, nhất là `AMBIGUOUS`, `CONFLICT` và các loại property chưa map. 315/315
nhóm target × loại × tháng vẫn có dưới 10 mẫu; dataset không có transaction type,
listing ID hay URL nguồn từng tin. Mở rộng thêm có thể tăng mật độ lịch sử nhưng
không giải quyết xác minh nguồn, bias, thay đổi giá theo thời gian hoặc quyền
khai thác nội dung. Sau khi hoàn thành rà soát nhãn và kiểm tra license/provenance,
có thể đề xuất batch 25.000 có giới hạn và kiểm toán trước khi cân nhắc 50.000.

## Tài liệu liên quan

- [Phase E2 pilot](historical_pilot_phase_e2.md)
- [Dataset card](datasets/tinixai_vietnam_real_estates.md)
- [Historical pilot dataset registry](../../catalogs/dataset_registry.yaml)
- [Experiment log](../../docs/experiments/experiment_log.md)
