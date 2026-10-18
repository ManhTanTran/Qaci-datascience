# Phase E1 — đánh giá nguồn dữ liệu thật

**Ngày kiểm tra:** 2026-10-14  
**Phạm vi:** đọc source registry, rà soát tài liệu chính thức, GET công khai một lần tới `robots.txt` của bốn website và một GET trang chủ Alonhadat để tìm liên kết chính sách. Không tải trang tin rao, không đăng nhập, không gọi API, không thử CAPTCHA và không ghi dữ liệu vào database.

## Kết luận

Không nguồn nào trong bốn website được chứng minh là cho phép collector thu thập listing tự động theo lịch. Cả bốn tiếp tục ở `REVIEW_REQUIRED`, `enabled=false`; `global_live_enabled=false` không đổi. Không có `APPROVED_FOR_PILOT`.

Các sitemap công khai chỉ giúp biết URL, không phải giấy phép trích xuất, lưu trữ hoặc tái sử dụng nội dung. Không tìm thấy tài liệu API/RSS/feed chính thức cho phép dùng tin rao của bốn website trong pipeline này. Vì vậy chưa có cơ sở để triển khai adapter live hoặc chạy thử lấy listing.

## Bốn nguồn hiện có

| source_name | robots_status | terms_status | permitted_methods | listing_detail_support | data_access_requirements | decision | evidence_urls |
|---|---|---|---|---|---|---|---|
| Batdongsan.com.vn | `User-agent: *` cho phép `/`; cấm một số đường dẫn nội bộ. Các nhóm bot được nêu tên có `Crawl-delay: 10`. | Điều khoản cấm gây tải không hợp lý; cho phép một số bản sao hợp lý để xem/dùng nội bộ, nhưng không cấp rõ quyền thu thập có hệ thống. | Chưa xác định được phương thức tự động nào được cấp phép. Cần chấp thuận/API/feed bằng văn bản cho mục đích, tần suất, trường dữ liệu và lưu trữ cụ thể. | Website có các trang tin; chưa tải trang tin để kiểm chứng khả năng truy xuất/đủ trường. | Xin quyền PropertyGuru Việt Nam; chỉ kết nối feed/API được cấp và theo đúng scope/giới hạn. | `REVIEW_REQUIRED` | [robots.txt](https://batdongsan.com.vn/robots.txt), [Điều khoản thỏa thuận](https://batdongsan.com.vn/dieu-khoan-thoa-thuan) |
| Alonhadat.com.vn | `User-agent: *`; chặn `/publish/handler/*`, `/publish/form/*`, `can-mua`, `can-thue` và các biến thể dưới `/nha-dat/`; có sitemap. | Không tìm thấy trang điều khoản/chính sách chính thức qua trang chủ và rà soát web công khai. Đây không phải bằng chứng rằng trang không có điều khoản. | Chưa có phương thức tự động được cấp phép. Sitemap không thay thế quyền sử dụng. | Có URL trang tin trong chỉ mục công khai; chưa tải trang chi tiết trong Phase E1. | Yêu cầu chủ website xác nhận quyền, API/feed, quy tắc tốc độ, retention và việc sử dụng nội bộ cho ngữ cảnh AI. | `REVIEW_REQUIRED` | [robots.txt](https://alonhadat.com.vn/robots.txt), [Trang chủ](https://alonhadat.com.vn/), [sitemap được khai trong robots.txt](https://alonhadat.com.vn/sitemap.xml) |
| Nhà Tốt (Nhatot.com) | `User-agent: *` cho phép `/`, có nhiều đường dẫn/tham số bị chặn và chặn `/feed`; `Content-Signal: search=yes, ai-input=yes, ai-train=no`. Nhóm crawler AI có tên bị chặn toàn bộ. | Điều khoản bảo vệ nội dung/cơ sở dữ liệu; việc đưa nội dung vào hệ thống truy tìm thông tin cho mục đích ngoài sử dụng cá nhân và sử dụng thương mại cần được cho phép bằng văn bản. `ai-input=yes` không phải giấy phép cho collector này. | Chưa có API/feed được công bố với quyền truy cập phù hợp. Cần văn bản chấp thuận/API partner và scope rõ ràng. | Website có tin chi tiết; không truy xuất trang tin trong audit này. | Chấp thuận bằng văn bản của Công ty TNHH Chợ Tốt, kể cả quyền lưu trữ/hiển thị và dùng các trường trong database/AI context. | `REVIEW_REQUIRED` | [robots.txt](https://www.nhatot.com/robots.txt), [Điều khoản sử dụng](https://trogiup.chotot.com/nguoi-ban/dieu-khoan-su-dung-cua-nhatot-com/) |
| Homedy.com | `User-agent: *` cho phép `/`; chặn một số path và nhóm bot có tên; có sitemap. | Quy chế nêu nội dung thuộc quyền của Homedy và cấm sao chép/sử dụng/phổ biến bất hợp pháp; không cấp quyền crawl listing tự động. | Chưa xác định phương thức tự động được cấp phép; cần chấp thuận/API/feed từ Homedy. | Website có trang tin/dự án; chưa truy xuất trang chi tiết trong audit này. | Xin quyền ghi rõ mục đích, tần suất, loại tin/trường, thời hạn lưu, quyền đưa vào kho nội bộ và attribution. | `REVIEW_REQUIRED` | [robots.txt](https://homedy.com/robots.txt), [Quy chế hoạt động](https://homedy.com/quy-che-hoat-dong), [sitemap](https://homedy.com/sitemap) |

### Diễn giải robots

Robots là chỉ dẫn máy đọc cho bot, không thay thế điều khoản, hợp đồng hay quyền đối với nội dung. `Allow: /`, sitemap công khai hay `ai-input=yes` không tự cấp quyền tải lặp lại, lưu candidate, tính thống kê hoặc gửi dữ liệu vào hệ thống AI. Collector giữ nguyên các cổng fail-closed; không đổi User-Agent để giả danh bot được phép.

## Nguồn thay thế được khảo sát

### Hệ thống thông tin về nhà ở và thị trường bất động sản của Bộ Xây dựng

Nghị định 94/2024/NĐ-CP mô tả dữ liệu ở cấp thị trường, địa phương và dự án, trong đó có số lượng/giá trị giao dịch, diện tích, tồn kho và tình hình giao dịch dự án. Nghị định nêu các cách khai thác gồm cổng thông tin, dịch vụ chia sẻ dữ liệu, phiếu/văn bản yêu cầu hoặc hợp đồng; dữ liệu chuyên sâu có thể phải được cấp quyền và trả chi phí. Căn cứ này **không chứng minh có API công khai hoặc quyền tải tin rao cá nhân**.

| source_name | robots_status | terms_status | permitted_methods | listing_detail_support | data_access_requirements | decision | evidence_urls |
|---|---|---|---|---|---|---|---|
| CSDL nhà ở và thị trường BĐS — Bộ Xây dựng | Chưa gọi endpoint robots hoặc API. Không phát sinh request tới cổng dữ liệu. | Cơ chế khai thác/cấp quyền được quy định trong Nghị định 94/2024/NĐ-CP. | Cổng, dịch vụ chia sẻ dữ liệu, phiếu yêu cầu hoặc hợp đồng; cấp quyền dữ liệu chuyên sâu theo hồ sơ. | Nội dung pháp quy tập trung vào số liệu thị trường/dự án và giao dịch; không xác nhận nguồn này cung cấp listing cá nhân có URL trang tin. | Gửi yêu cầu tới đơn vị quản lý để xác nhận schema, phạm vi, phí, độ chi tiết, cập nhật và quyền dùng nội bộ/AI. | `REVIEW_REQUIRED` cho listing pilot; là ứng viên phù hợp hơn cho dữ liệu giao dịch/tổng quan sau khi được cấp quyền. | [Nghị định 94/2024/NĐ-CP — CSDL văn bản pháp luật](https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID=169707), [Bộ Xây dựng: cách khai thác dữ liệu](https://xaydung.gov.vn/vn/_layouts/15/NCS.Webpart.MOC/mt_poup/Intrangweb.aspx?IdNews=72690) |

Đây là đường xin cấp quyền chính thức, nhưng **không thay thế** nguồn tin rao theo từng căn/đất cho yêu cầu `title + price + area + address + direct listing URL`. Nếu mục tiêu trước mắt là 3 listing thật, đường khả thi nhất là yêu cầu một cổng/nhà cung cấp cấp feed/API có license, hoặc nhận file export từ chính người đăng/đơn vị sở hữu dữ liệu kèm quyền sử dụng. Chưa tìm được public feed miễn phí có đủ quyền và đủ trường để tự bật.

### Housing Market Group — ứng viên API thương mại, chưa được duyệt

Tài liệu của nhà cung cấp tự mô tả Housing Market API là dịch vụ subscription, có thị trường Việt Nam và dữ liệu listing; tài liệu tích hợp nói REST JSON/XML, còn tài liệu kỹ thuật, authentication và rate limit được thỏa thuận theo từng integration. Đây là hướng **đáng yêu cầu báo giá và điều khoản**, không phải API công khai có thể tự gọi. Tài liệu công khai chưa xác nhận độ phủ đến từng phường, trường diện tích/ngày đăng/URL detail, quyền lưu lâu dài hoặc quyền dùng trong AI context. Chưa có credential, hợp đồng hay request nào được thực hiện; vì vậy trạng thái vẫn là `REVIEW_REQUIRED`.

| source_name | robots_status | terms_status | permitted_methods | listing_detail_support | data_access_requirements | decision | evidence_urls |
|---|---|---|---|---|---|---|---|
| Housing Market Group / Housing Market API | Chưa kiểm tra robots vì chưa gọi endpoint. | Nhà cung cấp mô tả dịch vụ subscription và tích hợp đối tác; chưa xem hợp đồng áp dụng cho WardPriceDaily. | Chỉ xem xét API/feed sau khi nhà cung cấp cấp quyền, scope, tài liệu và hạn mức bằng văn bản. | Nhà cung cấp nói API có listing details, nhưng chưa xác nhận URL tin gốc, giá, diện tích, ward, ngày đăng và khả năng đối chiếu từng record. | Cần báo giá; xác nhận coverage tại Việt Nam/cấp phường, schema, provenance, retention, attribution, quyền dùng nội bộ/AI và giới hạn request. | `REVIEW_REQUIRED` — ứng viên thương mại, chưa phải nguồn pilot. | [Mô tả Housing Market API](https://housingmarketgroup.com/housing-market-api-real-time-real-estate-data-across-17-countries), [thị trường hỗ trợ](https://faq.housingmarketgroup.com/vi/faq/what-countries-are-currently-supported), [API & XML integrations](https://housingmarketgroup.com/products/api-xml-sync) |

Tài liệu nhà cung cấp xác nhận Việt Nam nằm trong danh sách thị trường và mô tả API listing dạng subscription; trang tích hợp cho biết authentication/rate limits được thống nhất theo từng integration. Những phát biểu này là mô tả của nhà cung cấp, chưa phải kiểm chứng độc lập về coverage hoặc license cho dự án. Không gọi API và không phát sinh chi phí trong Phase E1.

## Adapter hiện có và điều kiện mở pilot

`ConfiguredHTMLCollector` đã có `discover()`, `extract()`, parser JSON-LD/HTML, gán provenance, request timeout, robots check, giới hạn tốc độ và dừng khi bị từ chối. Các test dùng fixture tổng hợp/offline. Đây **không phải** bằng chứng trang thật được phép truy cập hay adapter đã được xác nhận với schema của một nguồn.

Chỉ phát triển adapter nguồn cụ thể sau khi có tài liệu endpoint/format và quyền sử dụng. Pilot rank 1 cần:

1. Xác nhận nguồn cho phép lấy tối đa 3 tin, các trường cần thiết, lưu SQLite và sử dụng trong AI context.
2. Tài liệu API/feed hoặc pattern URL được nguồn xác nhận; quy tắc tốc độ/retention và attribution.
3. Cập nhật `config/collector_sources.json` với `permission_reference`, status, endpoint và limits; giữ các cổng live tắt cho tới khi người vận hành đồng ý.
4. Chạy dry-run; sau đó xin xác nhận riêng trước đúng một pilot live.
5. Lưu thử vào SQLite pilot độc lập, đối chiếu chính trang tin, kiểm duplicate và UI; không import production tự động.

Không dùng Google Search/Gemini Web, headless stealth, proxy, tài khoản/cookie, CAPTCHA bypass hoặc URL bị cấm làm đường thay thế.

## Request budget và khả năng mở rộng

Hiện `collection_http_attempts.purpose` phân biệt được `robots`, `search` và `listing_detail`, nhưng giới hạn **không tách riêng theo purpose**:

- `max_requests` là trần HTTP tổng của một lượt.
- `global_daily_request_budget` và `source.daily_request_budget` đếm toàn bộ HTTP attempt của nguồn/ngày, gồm robots, search và trang chi tiết.
- `requests_made` đếm HTTP requests; `candidates_found`, `source_verified`, `new_listings` và observation được lưu là các chỉ số riêng.
- Giới hạn 500 observation/ngày không có nghĩa là 500 listing mới. Listing trùng, bị loại hoặc đã biết vẫn dùng request và có thể không thành listing mới.
- Lịch sử ghi purpose riêng để phân tích, nhưng code chưa đặt trần riêng cho search và detail.

Các số đếm có grain khác nhau:

| Chỉ số | Nghĩa trong code hiện tại |
|---|---|
| HTTP request | Một lần GET thực tới robots, URL tìm kiếm hoặc trang chi tiết; mọi loại cùng tiêu thụ budget tổng. |
| Discovered URL | URL canonical được phân loại `CATEGORY`, `DIRECT_LISTING` hoặc `UNKNOWN`, duy nhất theo `(run, source, canonical_url)`. URL danh mục không thành candidate. |
| Candidate listing | Một trang detail đã parse và ghi/refresh trong Candidate Warehouse. `candidates_found` là số lần xử lý trong lượt, có thể gồm candidate lặp lại; không đồng nghĩa số listing mới. |
| Verified | Các trường nguồn/địa bàn vượt validation nội dung trang. Duplicate, target chưa map hoặc cờ review vẫn có thể chặn promotion. |
| Unique new listing | Listing canonical lần đầu được promote vào warehouse production sau các cổng xác minh và cấu hình. Listing đã có được tính là refresh, không phải listing mới. |
| Daily observation | Candidate có giá + diện tích được upsert theo candidate/ngày; quota vận hành còn cộng observation production không do crawler tạo. Observation có thể là unverified và không đồng nghĩa listing mới. |

`collection_http_attempts` lưu `purpose`, nên có thể tổng hợp riêng số robots/search/detail sau lượt chạy; hiện chưa có cột/cap budget riêng cho từng loại. `duplicates` trong run counter gồm cả candidate cùng nguồn đã từng thấy và duplicate tiềm năng xuyên nguồn.

Ước lượng một nguồn, một robots fetch cho mỗi run: một ward có thể phát sinh tối đa 3 request tìm kiếm (mỗi property type) cộng tối đa 3 request trang chi tiết để đạt cap 3, tức khoảng 7 HTTP requests tính cả robots. Năm ward, cap 10/ward: tối đa khoảng 15 search + 50 detail + robots ≈ 66 requests. Năm mươi ward, cap 10/ward: khoảng 150 search + 500 detail + robots ≈ 651 requests; con số thực tế có thể cao hơn nếu cần nhiều ứng viên do trùng/thiếu dữ liệu, hoặc thấp hơn nếu tìm ít tin. Vì vậy trần tổng 500 requests không thể đảm bảo 500 listing/observation đã xác minh.

Chưa nên nâng budget khi chưa có quyền và pilot. Với nguồn được phép sau này, đề xuất pilot giới hạn 1 ward, tối đa 3 listing, 10 HTTP requests tổng trong ngày (bao gồm robots/search/detail), một request mỗi 10 giây trừ khi nhà cung cấp quy định chặt hơn, không retry 403/429 và dừng ngay khi nhận từ chối. Chỉ điều chỉnh theo hạn mức văn bản của nguồn và số liệu pilot. Trước khi mở rộng, nên thêm dashboard/cap riêng `robots`, `search`, `listing_detail`, cùng trần tổng để người vận hành nhìn thấy request của từng giai đoạn.

## Trạng thái thực thi

- Không có request tới trang tin hoặc API nguồn listing.
- Không gọi Gemini/Search API.
- Không ghi candidate vào SQLite production/pilot; demo DB không bị đụng tới.
- Không bật Gmail hoặc Task Scheduler.
- Không có nguồn `APPROVED_FOR_PILOT`; yêu cầu xác nhận live chưa đến bước thực hiện.
