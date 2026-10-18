# TiniX AI Vietnam Real Estate Listings — pilot lịch sử

## Tóm tắt

- **Dataset:** [tinixai/vietnam-real-estates](https://huggingface.co/datasets/tinixai/vietnam-real-estates)
- **Nhà cung cấp/attribution:** TiniX AI, *Tinix Vietnam Real Estate Listings 2025–2026*.
- **Giấy phép công bố:** [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- **Mục đích được xác nhận trong pilot:** nghiên cứu và học tập phi thương mại.
- **Revision được lấy mẫu:** `ca3fedcbb089bf65f7e4cfb03316cce4bd0d779f`.
- **Thời gian nguồn theo dataset card:** 2025-06-01 đến 2026-03-31.
- **Mẫu cục bộ E3:** 10.000 hàng, trong đó giữ lại 1.000 hàng E2 và lấy thêm 9.000 hàng qua Hugging Face Dataset Viewer `/rows`; không tải nội dung 10 shard Parquet hay toàn bộ dataset.
- **Batch:** `tinix-e3-10000-ca3fedcbb089`; SHA-256 `5d3e9ca9a931465ed897efaff10e37192befee139e6d93ce646ef2d1d331247e`.
- **Đường dẫn dữ liệu cục bộ:** `data/historical_pilot/tinix_sample_10000.jsonl`, metadata tương ứng và `state/ward_prices.historical_pilot.sqlite3`; các file này bị Git ignore.

## Provenance và attribution

Dataset card ghi TiniX AI thu thập và biên tập 3.500.744 tin đăng bán/cho thuê,
trong khoảng 2025-06 đến 2026-03. Card công bố giấy phép CC BY-NC 4.0, yêu cầu
ghi tác giả/nguồn và nêu rõ giới hạn phi thương mại. Pilot lưu tên TiniX AI,
dataset ID, URL dataset, revision, giấy phép, thời điểm lấy mẫu, phương pháp lấy
mẫu và SHA-256 của mẫu trong SQLite.

Attribution hiển thị trong UI:

> TiniX AI, *Tinix Vietnam Real Estate Listings 2025–2026*, Hugging Face, CC BY-NC 4.0.
> Mẫu 10.000 hàng; lọc theo danh sách Top 50, chuẩn hóa địa danh và tính giá/m² từ giá/diện tích.

CC BY-NC 4.0 không cấp quyền thương mại. Nội dung có thể còn quyền bên thứ ba;
giấy phép chỉ cấp quyền mà người cấp phép có thẩm quyền cấp. Không tái sử dụng
pilot này cho sản phẩm thương mại nếu chưa có quyền riêng bằng văn bản.

## Schema đã kiểm tra thực tế

Dataset Viewer trả về 19 cột:

`name`, `description`, `property_type_name`, `province_name`, `district_name`,
`ward_name`, `street_name`, `project_name`, `price`, `area`, `floor_count`,
`frontage_width`, `house_depth`, `road_width`, `bedroom_count`, `bathroom_count`,
`house_direction`, `balcony_direction`, `published_at`.

`price` và `area` là `float64`; card mô tả giá bằng VND và diện tích bằng m².
`published_at` là chuỗi ISO 8601. Schema không có `transaction_type`, `listing_type`,
URL tin riêng hay ID tin gốc. Vì vậy `name` chỉ được dùng để nhận diện tín hiệu
giao dịch rõ ràng; các tiêu đề không nói rõ vẫn là `UNCLASSIFIED`. Không suy luận
mọi hàng đều là bán chỉ vì dataset có lẫn tin bán/cho thuê.

### Ánh xạ loại tài sản

| Giá trị nguồn | Kết quả pilot | Thống kê chính |
|---|---|---|
| `Nhà` | `NHA_RIENG` | Có thể tính nếu tiêu đề nêu rõ bán và giá/diện tích hợp lệ |
| `Căn hộ chung cư` | `CHUNG_CU` | Có thể tính nếu tiêu đề nêu rõ bán và giá/diện tích hợp lệ |
| `Đất` | `LAND_UNSPECIFIED` theo mặc định; `DAT_O` nếu tiêu đề có cụm chính xác `đất ở` hoặc `đất thổ cư` và không có cue loại trừ | Chỉ phân loại theo tiêu đề; không xác minh quyền sử dụng đất |
| `Biệt thự/Nhà liền kề`, `Shophouse`, loại khác | `NEEDS_REVIEW` | Không tự gộp vào nhóm khác |

Không có URL trang tin riêng. `source_dataset_url` trỏ tới trang dataset ở cấp
nguồn; `source_row_index` chỉ là vị trí dòng trong revision, không phải mã tin
gốc hay bằng chứng tin còn tồn tại. Vì thế mọi record mang
`HISTORICAL_DATASET_UNVERIFIED`.

## Cách lấy mẫu và ranh giới địa bàn

E2 lấy 1.000 hàng bằng 10 đoạn chỉ số liên tiếp, mỗi đoạn 100 hàng, ở 10 phần
khác nhau của dataset; không phải lấy 1.000 dòng đầu hay mẫu xác suất đơn giản.
E3 giữ nguyên các row identity này rồi điền đúng 100 hàng trong từng 100 strata
chỉ số toàn cục bằng các đoạn `/rows` không chồng lấn, offset seed theo revision.
Downloader kiểm tra dataset ID, public/gated state, license, revision, schema,
số hàng, `partial=false` và revision trước/sau; đọc footer Parquet chỉ bằng
HTTP byte-range. Mỗi shard có 1.000 sample rows. Đây vẫn là mẫu phi xác suất,
không chứng minh tính đại diện và không cho phép suy luận tỷ lệ toàn thị trường.

Mỗi record chỉ khớp Top 50 khi **tỉnh/thành + quận/huyện cũ + phường/xã** cùng
khớp sau chuẩn hóa dấu tiếng Việt và tiền tố hành chính. Không dò theo ward name
đơn lẻ, không dùng tên đơn vị hiện tại để thay mapping lịch sử, và không tự tạo
crosswalk cho tên khác nhau.

## Quy tắc tính toán và cách dùng

- Giá/m² tính bằng Python: `price / area`.
- Chỉ giá rao bán có tín hiệu rõ trong tiêu đề và nhóm loại tài sản được ánh xạ
  mới vào thống kê lịch sử.
- Tin thuê không đưa vào thống kê giá bán vì schema không định nghĩa chu kỳ giá
  thuê. Tiêu đề mơ hồ/không rõ vẫn ở kho ứng viên, không tính.
- Mean, median, min, max và sample count tính riêng theo target, nhóm tài sản và
  tháng `published_at`; không gộp nhiều loại tài sản.
- Observations là ảnh chụp nhập dataset, không phải cập nhật tin hằng ngày.
- Các bảng này không phải `CURRENT_VERIFIED`/`DAILY_NEW`, không ghi vào canonical
  listing tables và không bật làm AI context.

Trong 10.000 source rows, có 1.258 hàng khớp exact địa bàn Top 50; 1.190 candidate
duy nhất được lưu, phủ 48/50 target. Sau E4, 18 trong 209 loại đất chưa rõ được
map theo tiêu đề với cờ `PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED`;
191 vẫn `UNKNOWN`. Có 473 candidate đủ điều kiện thống kê lịch sử riêng theo
loại và tháng (312 `NHA_RIENG`, 156 `CHUNG_CU`, 5 `DAT_O`). Không có nhãn ground
truth từ người rà soát cho 100 tiêu đề nên chưa thể đánh giá precision/recall.
67 rows thiếu/không hợp lệ giá và một duplicate nội dung được giữ khỏi thống kê;
xem [báo cáo Phase E3](../historical_pilot_phase_e3.md) và
[Phase E4](../historical_pilot_phase_e4.md). Báo cáo [Phase E2](../historical_pilot_phase_e2.md)
giữ kết quả batch 1.000 hàng ban đầu.
