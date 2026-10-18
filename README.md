# WardPriceDaily

WardPriceDaily là project Python độc lập chạy trên Windows, gồm hai luồng tách biệt:

- **National Knowledge Base:** tra cứu danh mục hành chính hiện hành toàn quốc; tiếp nhận listing toàn quốc; giới hạn tối đa 500 listing observations/ngày; chỉ thống kê nguồn đã được người vận hành xác minh.
- **Whitelist collector cũ:** quy trình Gemini theo danh sách phường import, vẫn giữ giới hạn tổng 500 tin của luồng cũ.

Gemini chỉ tìm và trích xuất từng tin rao. Gemini không được hỏi để tạo giá trung bình hoặc giá ước tính. Các valuation `AI_ESTIMATE` cũ vẫn được giữ trong bảng legacy, nhưng không tham gia listing statistics.

## Cấu trúc

```text
WardPriceDaily/
├── .venv/                         # virtual environment riêng
├── .streamlit/config.toml         # giao diện sáng, chỉ bind localhost
├── config/wards.csv               # whitelist phường hiện hành
├── data/administrative/           # snapshot NSO gốc và CSV đã chuẩn hóa
├── outputs/                       # CSV, Excel, JSON, daily report
├── scripts/                       # Windows Task Scheduler scripts
├── state/ward_prices.sqlite3      # SQLite riêng, giữ cả dữ liệu legacy
├── tests/
├── wardprice/                     # registry, warehouse, API, pipeline và UI
└── wardprice_webpilot/            # Gemini Web adapter, audit riêng có prefix
```

## Cài đặt trên Windows

Từ PowerShell:

```powershell
cd "D:\Work\FPT\Data science\WardPriceDaily"
& .\.venv\Scripts\Activate.ps1
```

Nếu cần tạo lại môi trường trên máy khác:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## UI theo dõi pipeline

UI chạy cục bộ trên máy này và chỉ bind vào `127.0.0.1`. Cài thêm Streamlit một lần:

```powershell
& .\.venv\Scripts\python.exe -m pip install -e ".[ui]"
```

Mở dashboard:

```powershell
& .\.venv\Scripts\python.exe -m wardprice ui
```

Mở địa chỉ `http://127.0.0.1:8501` nếu trình duyệt không tự mở. Dừng server bằng `Ctrl+C` trong cửa sổ PowerShell. Đổi cổng khi cần:

```powershell
& .\.venv\Scripts\python.exe -m wardprice ui --ui-port 8502
```

Mặc định ứng dụng mở **Sổ tay giá** cho người sử dụng. Tra cứu nhận tên phường/xã hoặc câu hỏi ngắn, cho phép lọc theo tỉnh/thành, loại bất động sản và cơ sở diện tích. Người dùng phải chọn đúng địa bàn nếu tên trùng. Giá và mẫu tin chỉ xuất hiện khi có listing đã xác minh; nếu chưa đủ nguồn, trang nêu rõ chưa có dữ liệu thay vì tự ước tính.

Khu vực Quản trị gồm Tổng quan, Độ phủ, Pipeline, Gemini Web pilot, Tin rao & thống kê và Xuất dữ liệu. Để hiện lựa chọn **Quản trị** ở thanh trên cùng, đặt biến môi trường WARDPRICE_ADMIN_VIEW thành 1 trước khi chạy ứng dụng.

Trong PowerShell, nhập `$env:WARDPRICE_ADMIN_VIEW = '1'` trước lệnh mở dashboard ở trên.

Cờ WARDPRICE_ADMIN_VIEW chỉ điều khiển các trang nào được hiển thị; nó không phải đăng nhập hay phân quyền. Ứng dụng hiện chỉ bind vào 127.0.0.1. Không bật cờ này cho một bản triển khai chia sẻ với người dùng cuối nếu chưa bổ sung xác thực.

## Demo E2E với 500 listing giả lập

Gói `WardPriceDaily_Demo500.zip` được giữ trong `tests\fixtures\demo500`. Đây là dữ liệu giả lập, không phải kết quả Gemini hay giá thị trường. Importer demo dùng các bảng `demo_*` riêng trong `state\ward_prices.demo.sqlite3`; không ghi vào `state\ward_prices.sqlite3`. Tin demo luôn có `source_website=DEMO_SYNTHETIC`, `evidence_status=UNVERIFIED`, không có URL nguồn và bị chặn khỏi canonical listing importer.

Trong một PowerShell riêng, bật mode cho phiên hiện tại rồi khởi tạo, nhập 10 batch, kiểm tra thống kê và chạy kiểm tra chống trùng:

```powershell
Set-Location 'D:\Work\FPT\Data science\WardPriceDaily'
$env:WARDPRICE_DEMO_MODE = '1'
& .\.venv\Scripts\python.exe -m wardprice.demo init
& .\.venv\Scripts\python.exe -m wardprice.demo import-all
& .\.venv\Scripts\python.exe -m wardprice.demo verify
& .\.venv\Scripts\python.exe -m wardprice.demo replay --file .\tests\fixtures\demo500\batches\demo_group_01_50.json
& .\.venv\Scripts\python.exe -m wardprice.demo replay --file .\tests\fixtures\demo500\replay_rank01_duplicate_test.json
```

`verify` đối chiếu 150 mean/median nhóm với `expected_statistics_DEMO_ONLY.json`. Xem coverage hoặc tra cứu:

```powershell
& .\.venv\Scripts\python.exe -m wardprice.demo status
& .\.venv\Scripts\python.exe -m wardprice.demo lookup --query 'Phường Bình Hưng Hòa'
& .\.venv\Scripts\python.exe -m wardprice.demo lookup --query 'Phường Đại Kim' --property-type DAT_O
```

Mở dashboard web đã nối với API và SQLite demo trên cổng 8765. Trang mặc định là giao diện tra cứu; mục **Độ phủ dữ liệu** dành cho quản lý.

```powershell
$env:WARDPRICE_DEMO_MODE = "1"
& .\.venv\Scripts\python.exe -m wardprice api --api-port 8765
```

Mở `http://127.0.0.1:8765/`. Dashboard phục vụ trực tiếp từ FastAPI, đọc `state\ward_prices.demo.sqlite3` khi `WARDPRICE_DEMO_MODE=1`, hiện nhãn dữ liệu minh họa và không gọi Gemini, Gmail hay scheduler thật. Endpoint độ phủ, tra cứu, danh sách Top 50 và lịch sử đều đọc cùng SQLite demo. Dashboard không dùng các giá mẫu tĩnh của prototype cũ.

Tab **Ngữ cảnh AI** trình bày luồng đề xuất: đối chiếu nơi sống với địa bàn, đọc thống kê riêng theo loại bất động sản, rồi đóng gói dữ liệu thành tham chiếu `R1`. Tab này chỉ đọc database minh họa tại chỗ; nó không gọi Gemini và chưa gửi dữ liệu sang ứng dụng đánh giá khoản vay. Có thể mở màn hình mẫu trực tiếp bằng `http://127.0.0.1:8765/?view=aiContext&rank=1`.

Ở màn hình tra cứu, chọn tỉnh/thành trước để mở gợi ý phường/xã thuộc tỉnh/thành đó trong danh sách Top 50. Khi đổi tỉnh/thành, địa bàn và kết quả cũ được xóa để tránh tra nhầm vùng.

Để mở riêng API mà không dùng dashboard:

```powershell
$env:WARDPRICE_DEMO_MODE = "1"
& .\.venv\Scripts\python.exe -m wardprice api --api-port 8768
Invoke-RestMethod 'http://127.0.0.1:8768/api/v1/demo/coverage'
Invoke-RestMethod 'http://127.0.0.1:8768/api/v1/demo/lookup?q=Ph%C6%B0%E1%BB%9Dng%20B%C3%ACnh%20H%C6%B0ng%20H%C3%B2a'
```

Mô phỏng lỗi sau batch 5 rồi resume cùng `schedule-id`:

```powershell
& .\.venv\Scripts\python.exe -m wardprice.demo scheduler-mock --schedule-id pilot-day-01 --fail-after-batch 5
& .\.venv\Scripts\python.exe -m wardprice.demo scheduler-mock --schedule-id pilot-day-01
```

Kết thúc phiên demo bằng `Remove-Item Env:WARDPRICE_DEMO_MODE`. Khi mở project trong PowerShell mới, mode không tự bật trừ khi bạn chủ động đặt biến đó. Lệnh chạy UI production thông thường vẫn dùng database `state\ward_prices.sqlite3`. Không xóa demo database nếu muốn giữ lại fixture đã import.

Tab Pipeline dùng Gemini API khi người vận hành chủ động xác nhận. Tab Gemini Web pilot cho chọn một target Top 50, xem prompt, nhập cookie dạng password và gửi đúng một request với tối đa 10 tin. Mỗi lần chạy cần xác nhận trong form; giới hạn nội bộ là 3 request/ngày. Cookie chỉ tồn tại tạm trong bộ nhớ của phiên Streamlit, được xóa khỏi widget state sau khi gửi, và không ghi vào log, file hay SQLite. Không dán cookie vào chat. Adapter `gemini_webapi` là wrapper không chính thức; dừng nếu Google từ chối hoặc yêu cầu xác minh. Kết quả được lưu riêng trong `state\wardprice_webpilot.sqlite3`, giữ `UNVERIFIED` và không cập nhật thống kê tra cứu. Tab Xuất dữ liệu tạo CSV/Excel, báo cáo ngày và Gmail preview; preview không kết nối SMTP, không gửi thư. UI không đăng ký hoặc bật Windows Task Scheduler; các lệnh bật lịch vẫn nằm ở mục bên dưới và phải được chạy thủ công.

## Kho hành chính và giá toàn quốc

Snapshot NSO ngày **2026-10-13** đã được nhập vào SQLite: 34 tỉnh/thành và 3.321 đơn vị cấp xã (phường, xã, đặc khu). Mã hành chính giữ dạng TEXT. Snapshot lịch sử, tên cũ và Top 50 không được tự động ghép chỉ dựa trên tên; quan hệ nhiều-nhiều hoặc thiếu căn cứ vẫn giữ trạng thái chưa xác minh. Raw snapshot và CSV chuẩn hóa nằm trong `data\administrative\`; ghi chú chất lượng và nguồn ở `data\administrative\README.md`.

Sau import, 50 target cũ vẫn giữ nguyên trong `ward_target_legacy`; lớp registry ưu tiên có 5 target đã liên kết theo mapping review sẵn có và 45 target vẫn chờ rà soát. Database hiện chưa có listing đủ điều kiện hoặc price statistics toàn quốc, nên tra cứu đơn vị đã nhận diện trả `NO_PRICE_DATA` cho tới khi có dữ liệu nguồn được kiểm tra.

Migration chỉ bổ sung schema: tái sử dụng `listings`, `listing_sources`, `listing_history`, `ward_target_legacy` và `ward_registry`; thêm `data_sources`, `administrative_dataset_versions`, `administrative_units`, `administrative_aliases`, `administrative_relationships`, `priority_targets`, `priority_target_mappings`, `listing_observations`, `ward_price_statistics`, `listing_quarantine` và `provider_fetch_state`. Mã hành chính lưu dạng TEXT. Valuation `AI_ESTIMATE` cũ vẫn ở bảng riêng và không được dùng làm listing hay thống kê.

Importer không gọi mạng; nó đọc XML/CSV đã lưu. Dịch vụ danh mục và mã đơn vị hành chính của NSO được mô tả tại [trang Web Service NSO](https://danhmuchanhchinh.nso.gov.vn/WebService.aspx). 

```powershell
# Xem trạng thái coverage
& .\.venv\Scripts\python.exe -m wardprice coverage

# Tra cứu tên/mã, hỗ trợ không dấu và tên Top 50 cũ
& .\.venv\Scripts\python.exe -m wardprice admin-search --query "Binh Tri Dong" --province "Thành phố Hồ Chí Minh" --include-historical

# Tra cứu giá nội bộ; kết quả thiếu giá không tự tạo dữ liệu
& .\.venv\Scripts\python.exe -m wardprice lookup --query "27448" --property-type NHA_RIENG --area-basis FLOOR_AREA

# Xem hàng đợi P0/P1/P2; mapping Top50 chưa rõ được liệt kê riêng
& .\.venv\Scripts\python.exe -m wardprice collection-priorities

# Import lại snapshot đã lưu (chạy lại an toàn, không tải dữ liệu)
& .\.venv\Scripts\python.exe -m wardprice admin-import --file .\data\administrative\sources\nso_communes_as_of_2026-10-13.xml --as-of-date 2026-10-13 --current
```

### API và OpenAPI

FastAPI đọc cùng SQLite cục bộ. API fallback bên ngoài đang tắt; `refresh=true` chỉ trả `EXTERNAL_PROVIDER_NOT_CONFIGURED`. Khởi động:

```powershell
& .\.venv\Scripts\python.exe -m wardprice api --api-host 127.0.0.1 --api-port 8765
```

Mở `http://127.0.0.1:8765/docs` để xem OpenAPI. Các đường dẫn chính là `/api/v1/administrative-units/search`, `/api/v1/ward-prices/lookup`, `/api/v1/ward-prices/history`, `/api/v1/coverage`, `/api/v1/priority-targets` và `/api/v1/collection-priorities`. API priority không xuất `n_customers` hoặc `pct`.

Kế hoạch thu thập có thể xem bằng lệnh `collection-priorities`. P0 gồm các đơn vị hiện hành có mapping Top 50 đã review; P1 gồm đơn vị khác đang có listing active cần làm mới hoặc rà soát; P2 gồm đơn vị chưa có listing. Candidate chưa xác minh có thể được đưa vào hàng đợi P1 để làm mới, nhưng không được tính vào thống kê giá. Top 50 chưa map được liệt kê riêng, không ghép tự động theo tên.

### Nhập listing JSON offline

`ingest-listings` nhận JSON (`listings[]` hoặc array), CSV UTF-8, hoặc XLSX. Với bảng tính, hàng đầu là header; sheet tên `Listings` được ưu tiên, nếu không có thì dùng sheet active. Dùng các trường `administrative_code` (hoặc tên phường chính xác cùng tỉnh), `title`, `address`, `property_type`, `price_vnd`, `area_m2`, `area_basis`, `source_url` và các trường evidence. Mã loại BĐS: `DAT_O`, `NHA_RIENG`, `CHUNG_CU`; area basis: `LAND_AREA`, `FLOOR_AREA`, `USABLE_AREA`, `OTHER`. Preview là mặc định, không ghi DB. Import thật giới hạn 500 observations/ngày; cùng listing import lại trong một ngày chỉ cập nhật cùng observation. Sai địa bàn/URL hoặc record không hợp lệ được đưa vào `listing_quarantine`.

Candidate mặc định được lưu `UNVERIFIED` và không tham gia thống kê. JSON tự khai `SOURCE_PAGE_CONFIRMED` không được tin. Chỉ cờ review ở CLI cùng người xác minh, reference và đủ evidence mới đưa record vào số liệu đã xác minh:

```powershell
# Chỉ validate và xem thống kê dự kiến
& .\.venv\Scripts\python.exe -m wardprice ingest-listings --file .\inbox\listings.json

# Sau khi người vận hành đã đối chiếu trang nguồn, giá, diện tích và địa bàn
& .\.venv\Scripts\python.exe -m wardprice ingest-listings --file .\inbox\listings.json --apply --operator-verified --verified-by "Tên người review" --verification-reference "review ticket/local note"

# Xem lại thống kê và dữ liệu đã nhập
& .\.venv\Scripts\python.exe -m wardprice lookup --query "27448" --property-type NHA_RIENG --area-basis FLOOR_AREA
& .\.venv\Scripts\python.exe -m wardprice export
```

Mean/median/min/max được tính bằng Python và tách riêng theo loại BĐS **và** cơ sở diện tích. `SOURCE_PAGE_CONFIRMED` yêu cầu review độc lập; trạng thái Gemini không phải bằng chứng. Provider interface có timeout, cooldown và negative cache nhưng provider mặc định không gọi mạng.

## Danh sách phường

Chuẩn bị CSV UTF-8 với các cột bắt buộc `ward_code,ward_name,province`; `district` và `admin_source` là các cột tùy chọn. Mỗi mã phường chỉ xuất hiện một lần. Có thể import tối đa 100 phường; import danh sách mới sẽ thay whitelist active hiện tại nhưng không xóa listing, lịch sử hoặc valuation cũ. `ward_code` có thể là mã nội bộ ổn định nếu chưa có mã hành chính; đừng ghi mã nội bộ như thể là mã chính thức.

```powershell
& .\.venv\Scripts\python.exe -m wardprice validate-registry --registry .\config\wards.csv
& .\.venv\Scripts\python.exe -m wardprice import-wards --file .\config\wards.csv
```

`config\wards.csv` hiện được tạo từ bảng “TOP 50 PHƯỜNG” trong `top_50.txt`. Mã `TOP50-001`–`TOP50-050` là mã nội bộ theo thứ tự nguồn, không phải mã hành chính; tên, thành phố và quận/huyện được giữ nguyên từ tệp. Quận/huyện được đưa vào prompt chỉ để phân biệt địa bàn. Danh sách này chưa được đối chiếu với địa giới hành chính hiện hành. `config\wards.example.csv` chỉ chứa dữ liệu demo và không được tự động import.

## Registry Top 50 địa bàn gốc

Gói `WardPriceDaily_Top50_Package.zip` có thể được import trực tiếp, không cần giải nén. Lệnh tạo hoặc cập nhật bảng `ward_target_legacy` trong SQLite; thao tác này không thay whitelist đang hoạt động, không tạo tin rao, không xóa lịch sử và không gửi Gemini. Bảng giữ rank, địa bàn gốc, loại phường/xã và trạng thái đối chiếu. Mã `current_ward_code` để trống được lưu thành `NULL`, không được coi là mã hành chính.

Các trường `n_customers` và `pct` chỉ được lưu nội bộ trong SQLite để giữ nguyên registry nguồn. Chúng không xuất hiện trong lệnh `targets`, Gemini prompts hoặc bảng `listings`.

```powershell
& .\.venv\Scripts\python.exe -m wardprice import-targets --file "D:\Downloads\WardPriceDaily_Top50_Package.zip"
& .\.venv\Scripts\python.exe -m wardprice targets
```

File ZIP được đọc trực tiếp từ member `top50_targets_with_mapping_review.csv`; không có file nào được giải nén vào project. Import yêu cầu đủ rank 1–50 và có thể chạy lại an toàn. Trạng thái mapping chưa xác nhận vẫn được giữ nguyên; import registry không tự biến target thành whitelist tìm kiếm.

## Gemini Web pilot (không chính thức, tùy chọn)

Module `wardprice_webpilot` được tích hợp như một adapter thử nghiệm. Nó đọc đúng 50 target từ `ward_target_legacy` trong `state\ward_prices.sqlite3` ở chế độ chỉ đọc; không dùng CSV Top50 thứ hai và không đọc các trường `n_customers`/`pct`. Audit của adapter dùng `webpilot_runs` và `webpilot_candidates` trong sidecar `state\wardprice_webpilot.sqlite3`, không thay đổi bảng listing chuẩn.

Trong lệnh `collect` thông thường, candidate mặc định là `UNVERIFIED`. Citation URL và trích đoạn do Gemini tự khai không xác minh độc lập nội dung trang; tuyên bố `source_page_read` không đủ để gắn `SOURCE_PAGE_CONFIRMED`. Địa bàn sai/không rõ và tin nghi trùng bị cách ly. Với fixture đã cung cấp, handoff có 0 listing đủ điều kiện. Xem [hướng dẫn Gemini Web pilot](docs/gemini_webpilot_integration.md).

Kiểm tra cục bộ và dry-run rank 11, tối đa 5 tin:

```powershell
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 doctor
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 collect --rank 11 --count 5
```

Dry-run chỉ in prompt; nó không gọi mạng hoặc ghi database. Mỗi lệnh live cần xác nhận tường minh; adapter không tự retry ở tầng ứng dụng. Giới hạn nội bộ mặc định tối đa 3 lần thử mỗi ngày theo giờ Việt Nam; lần thất bại cũng tính vào giới hạn. Có thể hạ giới hạn bằng `--max-daily-calls 1` hoặc `2`. Giới hạn này không làm tăng quota của Google/Gemini và không bảo đảm tài khoản cho phép đủ số lần gọi. Adapter dùng wrapper `gemini_webapi` không chính thức, không dùng `GEMINI_API_KEY`, không cài dependency đó mặc định và không tự lấy cookie. Chỉ chạy live khi tài khoản và cách truy cập được phép:

```powershell
& .\.venv\Scripts\python.exe -m pip install -U gemini_webapi
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 collect --rank 11 --count 5 --live --confirm-single-live-call
```

Muốn thử thêm trong ngày, chạy lại một lệnh live riêng cho từng lần và giữ nguyên cùng file sidecar `--db` để giới hạn được theo dõi. Mỗi lần gọi cần xác nhận riêng; dừng nếu Google từ chối, báo quota hoặc yêu cầu xác minh tài khoản. Không đổi tài khoản, proxy hay cách truy cập để né giới hạn.

Không dán cookie vào chat, source, file log hoặc repository. Adapter đặt cache cookie của wrapper trong thư mục tạm riêng cho lượt gọi và xóa thư mục đó khi đóng client. Lệnh live chỉ lưu prompt, response và audit metadata vào sidecar/inbox; nó không ghi vào `listings`, không gửi Gmail và không đăng ký Task Scheduler.

Khi có handoff đủ điều kiện, lệnh `wardprice import-gemini-web` chạy preview mặc định. Chỉ thêm `--apply` sau khi đã xem dữ liệu và muốn ghi vào listing canonical. Lệnh import sử dụng validator/listing history hiện tại, ghi `grounding_used=0` vì citation của wrapper không phải Google Search grounding API, và lưu citation trong raw payload. Không dùng `--apply` trong smoke test.

Để import/kiểm tra fixture offline bằng một sidecar tạm, không dùng database sản xuất làm đích ghi:

```powershell
$trial = Join-Path $env:TEMP "wardprice-webpilot-offline"
New-Item -ItemType Directory -Force -Path $trial | Out-Null
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db (Join-Path $trial "audit.sqlite3") --output (Join-Path $trial "outputs") import-json --file .\tests\fixtures\gemini_batch50_as_received.txt
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db (Join-Path $trial "audit.sqlite3") status
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db (Join-Path $trial "audit.sqlite3") --output (Join-Path $trial "outputs") export
```

Chạy lại `import-json` với cùng nội dung để kiểm tra idempotency. CLI sẽ ghi run audit mới, còn số candidate duy nhất không tăng.

### Deep Research source audit (Phase E1)

`collect` gọi ordinary chat; lệnh `research` chạy API Deep Research theo ba bước plan, start, poll và đọc `result.document` cùng `result.document.sources`. Dry-run không gọi mạng và không ghi DB. Candidate source URL chỉ đến từ citation object; URL do model viết trong JSON không được dùng làm bằng chứng. `SOURCE_VERIFIED` yêu cầu source detail và page text độc lập khớp giá, diện tích, phường cùng quận/tỉnh. Page retrieval chưa tự động; không có page text thì detail URL chỉ là `SOURCE_PARTIAL`, URL danh mục là `CATEGORY_ONLY`.

```powershell
# Kiểm tra API có trong package và xem prompt rank 11; cả hai offline
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 doctor
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 research --rank 11 --count 5

# Chạy tối đa một Deep Research workflow/ngày, chỉ sau khi đã kiểm tra quyền tài khoản và xác nhận
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 research --rank 11 --count 5 --live --confirm-single-live-deep-research

# Xem audit; hoặc nạp lại file report/source đã lưu, hoàn toàn offline
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 research-status
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 research-import --rank 11 --count 5 --file .\inbox\webpilot\deep_research\report.md --sources-file .\inbox\webpilot\deep_research\sources.json
```

Live Deep Research uses a single workflow guard in the sidecar, not the
ordinary collect counter. The wrapper itself may make multiple plan/start/poll
operations and internal recovery requests. Raw report, sources, plan metadata,
and candidates remain in the sidecar/inbox; canonical listing tables are not
modified. No live research was run as part of Phase E1.

## Kiểm tra cấu hình Gemini

Offline check không dùng mạng và không gọi Gemini:

```powershell
& .\.venv\Scripts\python.exe -m wardprice gemini-check
```

Sau khi tự cấu hình `GEMINI_API_KEY`, có thể kiểm tra endpoint metadata để xác nhận model truy cập được. Lệnh này có kết nối mạng nhưng không tạo nội dung hoặc gọi Search:

```powershell
& .\.venv\Scripts\python.exe -m wardprice gemini-check --live
```

Lệnh không đọc được quota hoặc cấu hình billing riêng của Google AI project. Trước lần chạy tìm kiếm đầu tiên, kiểm tra model/quota tại [Google AI Studio](https://aistudio.google.com/) và đối chiếu [model docs](https://ai.google.dev/gemini-api/docs/models) cùng [giá Gemini API và Search grounding](https://ai.google.dev/gemini-api/docs/pricing). Một request có thể phát sinh nhiều truy vấn Search; `MAX_CALLS_PER_MONTH` chỉ giới hạn số prompt nội bộ, không phải dự toán hóa đơn. Project không tự chuyển tài khoản sang Paid Tier.

Theo bảng giá hiện hành, Google Search grounding trên Gemini 3 không có ở Free Tier; Paid Tier có 5.000 Search requests miễn phí dùng chung mỗi tháng, sau đó là 14 USD/1.000 search requests. Mỗi prompt có thể gọi nhiều search query và token generation vẫn có thể tính riêng. Hãy xác nhận tier của project trước pilot; project này không tự bật billing hoặc nâng tier.

## Chạy thử hai phường

Sau khi import whitelist, chạy dry-run để xem hai phường dự kiến được chọn. Không có Gemini API call:

```powershell
& .\.venv\Scripts\python.exe -m wardprice run --wards WARD_CODE_1,WARD_CODE_2
```

Mặc định tối đa hai phường mỗi lượt. Khi chủ động chấp thuận gọi API, đã kiểm tra quota/chi phí và đã cấu hình key, chạy:

```powershell
& .\.venv\Scripts\python.exe -m wardprice run --wards WARD_CODE_1,WARD_CODE_2 --live
```

Mọi mã đưa qua `--wards` phải nằm trong whitelist đã import. Nếu API trả response rỗng, pipeline ghi nhận không có listing và tiếp tục; không tạo giá ước tính. Nếu Gemini trả HTTP 429 (quota/rate limit), pipeline ghi lỗi cho phường hiện tại rồi dừng các request còn lại trong lượt đó. Các phường chưa gọi vẫn được ưu tiên ở lượt sau. Request bị 429 vẫn được tính vào cap nội bộ vì prompt đã được gửi; cap này không đồng nghĩa quota Google.

## Thu thập, kiểm tra và thống kê

- Gemini tìm tin rao cụ thể có giá bán tổng, diện tích, loại BĐS, địa chỉ và URL nguồn.
- Chỉ nhận loại `DAT_O`, `NHA_RIENG`, `CHUNG_CU`; mỗi loại được tổng hợp riêng.
- URL phải là HTTPS và được liên kết tới grounding chunk qua `grounding_supports`. Tin thiếu URL được grounding, địa chỉ, giá, diện tích hoặc trích dẫn bị loại khỏi thống kê.
- `SEARCH_SNIPPET_ONLY` được giữ nhãn riêng. `SOURCE_PAGE_CONFIRMED` chỉ được chấp nhận khi response báo đã đọc trang và URL có trong grounding metadata. Google grounding metadata tự nó không chứng minh trang đầy đủ đã được tải/đọc.
- Python tính `price_per_m2 = price_vnd / area_m2`, mean, median, min, max và `listing_count` trên listing đủ điều kiện. `listing_count` là sample count của nhóm.
- `listing_history` append mỗi lần quan sát; tin đang theo dõi được cập nhật, không tạo thêm dòng mỗi ngày. Từ 500 listing trở đi, tìm kiếm chỉ được dùng để làm mới tin đang theo dõi.
- Các listing cũ, source URL, evidence label và payload vẫn được lưu trong SQLite. Whitelist mới không xóa lịch sử.

Xem trạng thái và dữ liệu:

```powershell
& .\.venv\Scripts\python.exe -m wardprice status
& .\.venv\Scripts\python.exe -m wardprice listings
```

Xuất CSV/Excel và báo cáo hằng ngày:

```powershell
& .\.venv\Scripts\python.exe -m wardprice export
```

Các file chính trong `outputs\` gồm `national_listings_latest.csv/.json`, `national_price_statistics.csv`, `ward_prices_latest.xlsx` và `daily_report_YYYY-MM-DD.html/.json`. Workbook giữ sheet riêng cho national listings, national stats, whitelist listing và legacy valuation.

Có thể đọc trực tiếp SQLite bằng Python có sẵn:

```powershell
& .\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'state\ward_prices.sqlite3'); print(*c.execute('SELECT ward_code,property_type,COUNT(*),ROUND(AVG(price_per_m2)) FROM listings WHERE active=1 AND included_in_stats=1 GROUP BY ward_code,property_type'), sep='\n')"
```

## Gmail

Tạo `.env` từ `.env.example`, rồi cấu hình `ENABLE_EMAIL=true`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` và `REPORT_TO`. Gmail dùng Google App Password khi tài khoản bật 2-Step Verification. Tạo báo cáo email nhưng không kết nối SMTP:

```powershell
& .\.venv\Scripts\python.exe -m wardprice email-dry-run
```

Chỉ gửi sau khi đã chạy collection live và chủ động xác nhận bằng cờ `--send-email`:

```powershell
& .\.venv\Scripts\python.exe -m wardprice run --live --send-email
```

## Windows Task Scheduler — pipeline Gemini API cũ

`scripts/register_task.ps1` lập lịch cho lệnh `wardprice run` dùng Gemini API; nó
không chạy crawler HTML công khai mới. Không dùng các lệnh trong mục này để bật
collector. Hướng dẫn crawler 08:00 nằm ở [Thu thập listing công khai hằng ngày](docs/daily_collection.md).

Không task nào được đăng ký tự động trong quá trình cài đặt. Sau khi pilot hoàn tất và đã đồng ý bật lịch, đăng ký daily task ở chế độ dry-run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_task.ps1 -Time "08:17"
```

Để lịch gọi Gemini hàng ngày, cấu hình key và xác nhận quota/chi phí trước, sau đó đăng ký task live:

```powershell
.\scripts\register_task.ps1 -Time "08:17" -Live
```

Thêm `-SendEmail` chỉ khi đã bật và kiểm tra đủ cấu hình Gmail:

```powershell
.\scripts\register_task.ps1 -Time "08:17" -Live -SendEmail
```

Tác vụ chạy dưới user Windows hiện tại khi user đăng nhập. Không chạy các lệnh trên cho đến khi đã đồng ý bật Task Scheduler. Gỡ task do project này tạo:

```powershell
.\scripts\remove_task.ps1
```

## Biến môi trường

| Biến | Mặc định | Mục đích |
|---|---:|---|
| `GEMINI_API_KEY` | rỗng | Key Gemini; chỉ dùng với `--live`. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model phải được bật và hỗ trợ Google Search grounding trong project. |
| `MAX_WARDS_PER_RUN` | `2` | Giới hạn số phường/API calls cho một lượt. |
| `MAX_TOTAL_WARDS` | `100` | Giới hạn tương thích cho pipeline valuation legacy; không tham gia listing pipeline. |
| `MAX_TOTAL_LISTINGS` | `500` | Giới hạn tổng tin trong whitelist collector cũ. Importer national có giới hạn riêng tối đa 500 observations/ngày. |
| `MAX_NEW_LISTINGS_PER_WARD` | `10` | Giới hạn đề xuất tin mới cho một phường trong một lượt. |
| `MAX_CALLS_PER_MONTH` | `2` | Cap pilot cho số prompt/tháng; không phải quota tài khoản hay số Search query. |
| `REFRESH_DAYS` | `30` | Legacy setting cho collector cũ. |
| `RETRY_DAYS` | `7` | Legacy setting cho pipeline valuation cũ. |
| `MAX_ATTEMPTS_PER_WARD` | `3` | Legacy setting cho pipeline valuation cũ. |
| `ENABLE_EMAIL` | `false` | Bật gửi Gmail; cần đủ ba biến bên dưới. |
| `GMAIL_ADDRESS` | rỗng | Địa chỉ Gmail gửi. |
| `GMAIL_APP_PASSWORD` | rỗng | App Password, không phải mật khẩu đăng nhập thường. |
| `REPORT_TO` | rỗng | Địa chỉ nhận báo cáo. |
| `WARDPRICE_DB_PATH` | `state/ward_prices.sqlite3` | Override SQLite cho UI/test cục bộ. |
| `WARDPRICE_OUTPUT_DIR` | `outputs` | Override thư mục output cho UI/test cục bộ. |
| `WARDPRICE_WEBPILOT_DB_PATH` | `state/wardprice_webpilot.sqlite3` | Override sidecar audit của Gemini Web UI pilot. |
| `WARDPRICE_DEMO_MODE` | `false` | Khi bằng `1`, dùng duy nhất `state/ward_prices.demo.sqlite3`, khóa live Gemini/Gmail trong CLI và bật UI/API demo. Hỗ trợ alias `DEMO_MODE`. |

## Tests

```powershell
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\ruff.exe check .
```

Tests dùng fake researcher và dữ liệu mock. Không test nào gọi Gemini có phí, Gmail thật hoặc Task Scheduler.

## Thu thập listing công khai hằng ngày

Pipeline crawler có Source Registry, robots-aware HTTP client, JSON-LD/HTML parser,
Candidate Warehouse và trang **Thu thập web** trong dashboard quản trị. Các website
đã khảo sát đều đang tắt cho tới khi quyền thu thập listing tự động được xác nhận;
vì vậy mặc định chỉ chạy dry-run và không gửi request web. Xem
[hướng dẫn collector](docs/daily_collection.md) và
[audit quyền nguồn](docs/collection_sources_audit.md) trước khi cấu hình live.

### Phase F1 — nhập dữ liệu hiện hành vào pilot riêng

Phase F1 bổ sung intake dùng chung cho JSON, CSV, XLSX và adapter tương lai vào
`state\ward_prices.ingestion_pilot.sqlite3`. Pilot đọc registry Top 50 ở chế độ
read-only, nhưng không chép listing từ production, demo, lịch sử TiniX hoặc
Gemini Web. Các nguồn hiện vẫn `REVIEW_REQUIRED`; không có API/crawler live được
bật. Candidate không có bằng chứng trực tiếp vẫn nằm ngoài thống kê verified.

```powershell
Set-Location 'D:\Work\FPT\Data science\WardPriceDaily'
$Python = '.\.venv\Scripts\python.exe'

# Khởi tạo pilot và xem quyền nguồn/độ phủ.
& $Python -m wardprice.ingestion_pilot init
& $Python -m wardprice.ingestion_pilot sources
& $Python -m wardprice.ingestion_pilot status

# Preview luôn là mặc định; chỉ thêm --apply sau khi nguồn đã được cấp quyền.
& $Python -m wardprice.ingestion_pilot ingest `
  --file '.\inbox\partner_batch.json' --source-id 'partner-json-template'
& $Python -m wardprice.ingestion_pilot ingest `
  --file '.\inbox\partner_batch.json' --source-id 'partner-json-template' --apply

# Xem trước luồng scheduler; lệnh này không đăng ký Windows Task Scheduler.
& .\scripts\run_ingestion_scheduler_dry_run.ps1

# Synthetic benchmark chỉ ghi vào SQLite tạm.
& $Python -m wardprice.ingestion_pilot benchmark --count 500

# UI/API pipeline local: http://127.0.0.1:8768/ingestion-pilot
& $Python -m wardprice api --api-host 127.0.0.1 --api-port 8768
```

Xem [hướng dẫn Phase F1](docs/daily_ingestion_phase_f1.md),
[các nguồn cần cấp quyền](docs/live_source_onboarding.md),
[quyết định cách ly dữ liệu](docs/decisions/0003-phase-f1-source-agnostic-ingestion.md)
và [log benchmark](docs/experiments/experiment_log.md). Không bật nguồn,
Gmail hoặc Task Scheduler bằng các lệnh trên.

## Pilot dữ liệu lịch sử TiniX AI (phi thương mại)

Phase E2 đã lưu mẫu 1.000 hàng. Phase E3 mở rộng mẫu khảo sát lên tối đa
10.000 hàng từ dataset
[TiniX AI Vietnam Real Estate Listings](https://huggingface.co/datasets/tinixai/vietnam-real-estates),
giấy phép CC BY-NC 4.0. Không tải toàn bộ Parquet. Mẫu và SQLite pilot được
giữ ngoài Git; dữ liệu chỉ dành cho nghiên cứu/học tập phi thương mại.

```powershell
Set-Location 'D:\Work\FPT\Data science\WardPriceDaily'

# Phase E3 đã tạo mẫu 10.000 dòng bằng Dataset Viewer /rows, lấy 100 dòng ở
# mỗi strata chỉ số toàn cục và tái sử dụng 1.000 dòng E2. Không tải Parquet.
# Để resume nếu cần, chạy lại lệnh mở rộng dưới đây với cùng revision/đường dẫn.
& .\.venv\Scripts\python.exe scripts\download_tinix_historical_sample.py `
  --extend-existing --total-sample-rows 10000 `
  --existing-sample .\data\historical_pilot\tinix_sample.jsonl `
  --existing-metadata .\data\historical_pilot\tinix_sample.metadata.json `
  --output .\data\historical_pilot\tinix_sample_10000

# Audit chất lượng và tạo gói review tiêu đề; không sửa dữ liệu nguồn.
& .\.venv\Scripts\python.exe -m wardprice.historical_dataset quality-audit `
  --sample .\data\historical_pilot\tinix_sample_10000.jsonl `
  --metadata .\data\historical_pilot\tinix_sample_10000.metadata.json

# Xem trước số lượng và lý do loại; không ghi database.
& .\.venv\Scripts\python.exe -m wardprice.historical_dataset dry-run `
  --sample .\data\historical_pilot\tinix_sample_10000.jsonl `
  --metadata .\data\historical_pilot\tinix_sample_10000.metadata.json

# Import vào state\ward_prices.historical_pilot.sqlite3; database Top50 chỉ đọc.
& .\.venv\Scripts\python.exe -m wardprice.historical_dataset import `
  --sample .\data\historical_pilot\tinix_sample_10000.jsonl `
  --metadata .\data\historical_pilot\tinix_sample_10000.metadata.json

# Xem batch, chất lượng và coverage sau import.
& .\.venv\Scripts\python.exe -m wardprice.historical_dataset overview

# Chạy tra cứu Top 50; mở http://127.0.0.1:8768/
& .\.venv\Scripts\python.exe -m uvicorn wardprice.api:app --host 127.0.0.1 --port 8768
```

Trong chế độ thường, `/` mở giao diện tra cứu Top 50 và `/historical-pilot` là
đường dẫn tương đương. Giao diện đọc trực tiếp `state\ward_prices.historical_pilot.sqlite3`;
không sao chép dữ liệu sang production. Khi importer thêm batch vào database này,
tra cứu sẽ dùng revision mới nhất ở lần tải kế tiếp. Các số lịch sử không đi vào
`CURRENT_VERIFIED`, `DAILY_NEW` hoặc ngữ cảnh AI. Tiêu đề không đủ căn cứ bán/thuê
được giữ `UNCLASSIFIED`; loại `Đất` chung không tự chuyển thành `DAT_O`. Mỗi
listing không có URL nguồn riêng trong dataset; giao diện chỉ dẫn về dataset gốc.
Lấy mẫu theo strata chỉ số toàn cục giúp phủ vị trí ở nhiều phần của dữ liệu,
nhưng không phải mẫu xác suất và không chứng minh độ đại diện theo địa phương
hay thời gian. Xem [báo cáo Phase E2](docs/historical_pilot_phase_e2.md),
[báo cáo Phase E3](docs/historical_pilot_phase_e3.md) và
[data card](docs/datasets/tinixai_vietnam_real_estates.md).

Màn tra cứu chọn tỉnh/thành trước, sau đó chỉ gợi ý các địa bàn Top 50 thuộc tỉnh
đó. Đây là lớp tra cứu nghiên cứu cho bộ historical; khi có dữ liệu hiện hành đã
xác minh, chúng vẫn phải được trình bày và tính riêng. Trong kết quả Top 50, R1
là bản xem trước câu dẫn và payload được ghép từ thống kê lịch sử; không gọi AI,
không gửi dữ liệu sang AI hay luồng đánh giá. Payload giữ nhãn
`HISTORICAL_RESEARCH_ONLY`, attribution, revision, giấy phép và giới hạn dữ liệu.
Tab Ngữ cảnh AI không nhận các số từ bộ historical này. Trong 10.000 dòng đã lấy
mẫu, 8.742 dòng không khớp Top 50; chúng không thành ứng viên của danh sách mục
tiêu. Dataset nguồn công bố 3.500.744 dòng, nhưng pilot chỉ lấy mẫu 10.000 dòng.

### Kiểm toán chất lượng Phase E4 (offline)

Phase E4 không tải thêm dữ liệu và không gọi API. Báo cáo JSON được tạo từ sample
10.000 dòng và hai ảnh chụp pilot DB; backup baseline trước khi đổi mapping được
lưu trong `state/backups/`.

```powershell
Set-Location 'D:\Work\FPT\Data science\WardPriceDaily'

# Xem phân bố 100 tiêu đề và trạng thái nhãn thủ công (chưa có nhãn ground truth).
& .\.venv\Scripts\python.exe scripts\review_historical_titles.py

# Gắn nhãn thủ công; Enter để bỏ qua, nhãn hiện có được giữ lại.
& .\.venv\Scripts\python.exe scripts\review_historical_titles.py --interactive

# Tạo lại audit offline từ E3 baseline và pilot hiện tại.
& .\.venv\Scripts\python.exe scripts\audit_historical_e4.py `
  --before-db .\state\backups\ward_prices.historical_pilot.pre_e4_property_mapping_20261014T184548_0fddd5Z.sqlite3 `
  --after-db .\state\ward_prices.historical_pilot.sqlite3

# Reapply quy tắc mapping theo tiêu đề; lệnh tự tạo backup pilot trước khi ghi.
& .\.venv\Scripts\python.exe scripts\refresh_historical_property_mapping.py
```

Xem [báo cáo Phase E4](docs/historical_pilot_phase_e4.md). Chỉ tiêu thống kê
trong đó là lịch sử phi xác minh; không đại diện thị trường, không bật AI context
và không thay thế kiểm chứng nguồn từng tin.

### Human review và đánh giá Phase E5 (offline)

Phase E5 tạo phiếu CSV riêng cho 100 tiêu đề và các candidate cần rà soát loại
BĐS. Lệnh đọc pilot database ở chế độ read-only; không gọi mạng và không sửa
production, demo hoặc pilot DB. Lệnh từ chối ghi đè file E5 đã tồn tại để giữ nhãn
người review.

```powershell
Set-Location 'D:\Work\FPT\Data science\WardPriceDaily'

# Tạo phiếu CSV trống và sensitivity audit; không tạo human labels.
& .\.venv\Scripts\python.exe scripts\prepare_historical_e5_review.py

# Mở hai CSV trong outputs\historical_quality để review theo hướng dẫn.
# Không chỉnh các cột e4_* hoặc rule_*; chỉ điền nhãn, reviewer_notes và status.
# Hướng dẫn: docs\historical_review_guide.md

# Kiểm tra trạng thái/nội dung của phiếu tiêu đề; chưa có nhãn thì metrics=null.
& .\.venv\Scripts\python.exe scripts\review_historical_titles.py `
  --csv .\outputs\historical_quality\tinix-e5-title-review.csv

# Review tương tác trong terminal, nếu muốn; Enter giữ dòng chưa review.
& .\.venv\Scripts\python.exe scripts\review_historical_titles.py `
  --csv .\outputs\historical_quality\tinix-e5-title-review.csv --interactive

# Validate phiếu property type sau khi review.
& .\.venv\Scripts\python.exe scripts\review_historical_properties.py `
  --csv .\outputs\historical_quality\tinix-e5-property-review.csv
```

Chỉ các dòng có nhãn hợp lệ và `review_status=REVIEWED` mới vào confusion matrix,
precision/recall/F1, coverage, abstention và error analysis. Mẫu 100 dòng chia đều
25 theo mỗi dự đoán E4, không đại diện cho toàn bộ candidate; không suy rộng metric
sang population và không tính trọng số khi chưa có thiết kế lấy mẫu phù hợp. Nhãn
loại BĐS của con người cũng không xác minh nguồn web hoặc pháp lý. Xem [báo cáo
chuẩn bị Phase E5](docs/historical_pilot_phase_e5.md), [hướng dẫn review E5](docs/historical_review_guide.md), [quyết định evaluation E5](docs/decisions/0002-e5-human-review-evaluation-protocol.md)
và audit được tạo trong `outputs\historical_quality\tinix-e5-historical-sensitivity.json`.
