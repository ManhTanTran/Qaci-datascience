# Thu thập listing hằng ngày

## Trạng thái hiện tại

Pipeline đọc 50 target từ SQLite hiện tại, sắp thứ tự theo số listing đã xác minh
ít nhất rồi theo lần thử cũ nhất. Mỗi target nhận tối đa 10 candidate/lượt; toàn
lượt tối đa 500 request và 500 observation/ngày. Đây là giới hạn, không phải cam
kết tìm đủ tin mới. Tin đã thấy lại cập nhật candidate và observation ngày, không
được tuyên bố là listing mới.

Các nguồn khảo sát đang ở `REVIEW_REQUIRED`, tắt trong
`config/collector_sources.json`, và `global_live_enabled=false`. `robots.txt`
không thay thế quyền sử dụng nội dung. Vì vậy live hiện dừng trước request tìm
kiếm cho tới khi có quyền truy cập được ghi nhận. Xem
[đánh giá nguồn Phase E1](phase_e_source_assessment.md) và
[ghi nhận rà soát ban đầu](collection_sources_audit.md). Không có Gemini, Search API, API
trả phí, đăng nhập, CAPTCHA, paywall, proxy hoặc kỹ thuật né chặn trong collector.

## Khởi tạo schema có backup

Lệnh sau tạo snapshot SQLite đã kiểm tra integrity trong `state/backups/` trước
khi thêm các bảng thu thập, rồi đồng bộ source registry tắt mặc định:

```powershell
Set-Location 'D:\Work\FPT\Data science\WardPriceDaily'
& .\.venv\Scripts\python.exe -m wardprice collection-init
```

Không tạo hoặc thay database khác. `ward_target_legacy`, 50 target, candidate,
listing, observation và lịch sử hiện có được giữ lại. Lệnh này không gọi mạng.
Lần migration ban đầu đã có snapshot trước đó trong `state/`; `collection-init`
tạo thêm snapshot mới ngay trước khi chạy.

## Dry-run và audit

Dry-run là mặc định, chỉ đọc SQLite:

```powershell
& .\.venv\Scripts\python.exe -m wardprice collect-daily --dry-run
& .\.venv\Scripts\python.exe -m wardprice collect-daily --rank 1 --dry-run
& .\.venv\Scripts\python.exe -m wardprice collect-daily --ranks 1-5 --dry-run
& .\.venv\Scripts\python.exe -m wardprice collect-daily --batch 1 --dry-run
```

Không đưa lựa chọn target thì collector chọn toàn bộ 50 target. Có 10 batch, mỗi
batch 5 target. Xem nguồn, readiness, trạng thái và báo cáo JSON:

```powershell
& .\.venv\Scripts\python.exe -m wardprice collection-sources
& .\.venv\Scripts\python.exe -m wardprice collection-status
& .\.venv\Scripts\python.exe -m wardprice collection-report
```

API giám sát read-only: `GET /api/v1/collection/monitoring`. Tab **Thu thập dữ liệu**
hiển thị summary và form chọn tỉnh để chạy lượt có cổng kiểm soát.

## Tìm kiếm và thu thập trên hai tab riêng

Tab **Tìm kiếm dữ liệu** giữ phần tra cứu mẫu TiniX AI. Tab **Thu thập dữ liệu**
có hai nút: **Thu thập toàn bộ Top 50** và **Thu thập tỉnh này trên 4 nguồn**.
Nút theo tỉnh chọn toàn bộ địa bàn Top 50 thuộc tỉnh đang chọn; nút còn lại chọn cả
50 địa bàn. Cả hai chỉ chạy qua các source đã đủ quyền, được bật và đồng bộ trong
database collection. Mỗi lượt UI giới hạn tối đa 20 request; lượt toàn Top 50 có
thể cần nhiều lượt để rà hết địa bàn,
không gọi Gemini/Gmail, không tạo lịch chạy, và luôn đặt `allow_auto_ingest=false`;
candidate nằm trong kho collection riêng, không được nhập vào thống kê giá hiện
hành. Kết quả UI chỉ hiện trường địa bàn, loại BĐS, giá, diện tích, giá/m², nguồn
và trạng thái bằng chứng; không hiện URL tin.

`GET /api/v1/collection/province-search/readiness?province=<tên tỉnh>` chỉ đọc
Top 50 và source registry cục bộ, không gọi mạng. `POST
/api/v1/collection/province-search` kiểm tra lại cả config lẫn source registry
SQLite trước khi gọi collector. `GET /api/v1/collection/top50-search/readiness`
và `POST /api/v1/collection/top50-search` áp dụng cùng cổng cho cả 50 địa bàn.
Nếu thiếu phê duyệt, cấu hình, đồng bộ hoặc schema, request bị dừng trước website
và phản hồi có `network_attempted=false`.

Hiện bốn nguồn đang `REVIEW_REQUIRED`/tắt và
`global_live_enabled=false`, vì vậy nút Search sẽ báo bị khóa, không thu thập tin
live. Việc có kết quả theo địa bàn không tự mở cổng quyền nguồn.

## Candidate, bằng chứng và thống kê

HTML parser lấy JSON-LD, meta fields và text hiển thị. Candidate phải đến từ URL
chi tiết cùng domain đã cấu hình; URL danh mục chỉ được lưu trong bảng
`collection_discovered_urls`, không trở thành listing và không làm unique key.
Giá/diện tích có đối chiếu giữa structured data và text hiển thị. Địa bàn đối
chiếu theo ward, quận/huyện gốc và tỉnh/thành. Mismatch, hết hạn, target chưa map
hoặc duplicate xuyên nguồn được giữ ở Candidate Warehouse với trạng thái review.

Các bảng audit chính gồm:

- `collection_sources`, `collection_settings`: source permission, budgets và cổng live.
- `collection_runs`, `collection_target_attempts`, `collection_http_attempts`: run,
  checkpoint theo địa bàn và từng request.
- `collection_discovered_urls`: URL danh mục / tin chi tiết và kết quả nhận diện.
- `collection_candidates`, `collection_candidate_observations`: candidate và lịch
  sử quan sát riêng khỏi bảng listing production.
- `collection_rejections`, `collection_daily_statistics`: cách ly và báo cáo ngày.

Chỉ trang chi tiết được tải trực tiếp, qua robots, khớp ward/giá/diện tích và có
target hành chính đã map mới có thể vào listing chuẩn. Cổng tự động nhập còn cần
cả `collection_settings.auto_ingest_verified=1` và
`collection_sources.auto_ingest_verified=1`. `SEARCH_SNIPPET_ONLY`, URL danh mục,
target chưa map, `SOURCE_PARTIAL`, `SOURCE_CONFLICT`, `GEO_MISMATCH` và candidate
cần review không được tính vào statistics chuẩn. Python hiện có tính mean/median
qua importer/warehouse sau khi promotion hợp lệ.

## Điều kiện bật một nguồn

Không bật source chỉ dựa trên `robots.txt`. Trước tiên cần điều khoản cho phép rõ
ràng hoặc văn bản chấp thuận của nhà cung cấp. Khi đã có căn cứ, người vận hành
cập nhật source cụ thể trong `config/collector_sources.json`: `policy_status`,
`permission_reference`, `enabled`, `search_url_template`, `detail_path_regex`,
request budget, crawl delay và mapping trường. `global_live_enabled` phải được bật
riêng. Chạy lại `collection-init` để đồng bộ; xem `collection-sources`, rồi review
dry-run. Source readiness yêu cầu đủ các cổng này.

Sau khi có quyền nguồn và người vận hành chấp thuận một pilot nhỏ, lệnh live theo
mặc định vẫn chỉ đi qua robots-aware HTTPS client, không retry 403/429, obeys
`Retry-After`, giới hạn host/port, response size, source/day request budget và cap
500. Ví dụ lệnh chuẩn bị pilot (chưa chạy):

```powershell
& .\.venv\Scripts\python.exe -m wardprice collect-daily --rank 1 --limit 3 --max-requests 20 --source <source_id> --live
```

Hiện chưa có `source_id` đủ điều kiện; lệnh này sẽ bị chặn trước network. Không
chạy thử bằng cách sửa permission status giả.

## Windows Task Scheduler

`scripts/run_daily_collection.ps1` chạy 50 target lúc được gọi và ghi log vào
`outputs/collector/`, sau lượt chạy thành công gọi exporter hiện có để làm mới
CSV/Excel và daily report. `collection-report` cũng ghi summary JSON vào
`outputs/collection_report_YYYY-MM-DD.json`. Không có email được gửi.
`scripts/register_collector_task.ps1` chuẩn bị lịch 08:00
hằng ngày theo giờ local của Windows; lịch bắt đầu trễ khi máy bật lại, còn dữ
liệu vẫn giới hạn theo ngày chạy thực tế và các observation idempotent. Không có
task nào được đăng ký trong lượt triển khai này.

Chỉ sau khi nguồn đã được phép, pilot đạt yêu cầu và có chấp thuận riêng mới gọi:

```powershell
.\scripts\register_collector_task.ps1 -PilotPassed -Register
```

Script từ chối chạy nếu thiếu một trong hai cờ, không ghi đè task cùng tên và
không chạy task ngay sau khi đăng ký. Nếu máy cần chạy lúc 08:00 giờ Việt Nam,
Windows phải dùng múi giờ `SE Asia Standard Time`.

## Biến cấu hình

Collector không cần `GEMINI_API_KEY`, cookie Gemini, Gmail hoặc Search API. Quyền
thu thập và giới hạn truy cập được khai báo trong source registry; không lưu
credential truy cập trang trong config, raw payload hoặc log.
