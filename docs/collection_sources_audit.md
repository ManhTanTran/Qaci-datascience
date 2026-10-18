# Kiểm tra nguồn thu thập — 2026-10-14

Kết quả xác minh Phase E1 mới nhất, gồm robots GET trực tiếp, Terms và nguồn thay thế chính thức, được ghi tại [Phase E1 — đánh giá nguồn dữ liệu thật](phase_e_source_assessment.md). Tài liệu dưới đây là ghi nhận rà soát ban đầu; Phase E1 vẫn giữ tất cả nguồn ở `REVIEW_REQUIRED`.

## Kết luận

Chưa có nguồn nào được bật. `robots.txt` là tín hiệu điều phối crawler, không thay thế điều khoản sử dụng hoặc quyền khai thác dữ liệu. Chưa xác minh được nguồn nào cho phép thu thập listing tự động có hệ thống để lưu, tổng hợp và dùng trong cơ sở dữ liệu giá. Vì vậy `global_live_enabled=false`, từng nguồn `enabled=false`, `policy_status=REVIEW_REQUIRED`. Lệnh live phải dừng trước khi gửi request trang tìm kiếm nếu không có phê duyệt nguồn được ghi nhận.

## Kết quả rà soát

| Nguồn | Robots | Điều khoản / quyền thu thập | Trạng thái |
|---|---|---|---|
| Batdongsan.com.vn | `User-agent: *` cho phép `/`, có đường dẫn bị cấm; một số bot được ghi `Crawl-delay: 10`. | Điều khoản cho phép lưu một số lượng hợp lý bản sao để truy cập/xem và dùng nội bộ, đồng thời giới hạn khai thác nội dung. Chưa đủ căn cứ để coi việc lấy mẫu hàng ngày có hệ thống là được phép. | `REVIEW_REQUIRED`, tắt |
| Alonhadat.com.vn | Cho phép chung, cấm một số URL đăng tin/form và mục “cần mua/cần thuê”. | Chưa tìm thấy điều khoản chính thức mô tả quyền crawl tự động. | `REVIEW_REQUIRED`, tắt |
| Nhà Tốt | Nhóm chung cho phép `/`, nêu `search=yes, ai-input=yes, ai-train=no`; một số crawler AI có tên cụ thể bị cấm hoàn toàn. | Robots signals không xác nhận quyền truy cập tự động cho collector này. Không giả danh bot khác để né quy tắc. | `REVIEW_REQUIRED`, tắt |
| Homedy.com | Cho phép chung, cấm một số đường dẫn (`/js/`, `*amp*`, `*-bg*`) và một số bot có tên. | Quy chế hoạt động công khai tập trung vào hoạt động sàn và dữ liệu người dùng, không cấp quyền trích xuất listing tự động. | `REVIEW_REQUIRED`, tắt |

## URL chính thức đã kiểm tra

- [Batdongsan.com.vn robots.txt](https://batdongsan.com.vn/robots.txt)
- [Batdongsan.com.vn Điều khoản thỏa thuận](https://batdongsan.com.vn/dieu-khoan-thoa-thuan)
- [Alonhadat.com.vn robots.txt](https://alonhadat.com.vn/robots.txt)
- [Nhà Tốt robots.txt](https://www.nhatot.com/robots.txt)
- [Nhà Tốt trang bắt đầu / liên kết điều khoản](https://www.nhatot.com/start.php)
- [Homedy.com robots.txt](https://homedy.com/robots.txt)
- [Homedy.com Quy chế hoạt động](https://homedy.com/quy-che-hoat-dong)

## Cổng để bật một nguồn

Chỉ chuyển `policy_status` sang `APPROVED`, điền `permission_reference`, `search_url_template` và `detail_path_regex` trong `config/collector_sources.json` sau khi có điều khoản/quyền sử dụng phù hợp hoặc xác nhận bằng văn bản của đơn vị vận hành nguồn. Bật `enabled` cho riêng nguồn đó; `global_live_enabled` tiếp tục mặc định false cho tới khi pilot được chấp thuận. Collector vẫn kiểm tra robots trước từng URL, giới hạn tốc độ và dừng khi nhận 403/429. Không đăng nhập, không CAPTCHA, không paywall, không proxy/stealth.

Đây là ghi nhận kỹ thuật về trạng thái truy cập tại ngày kiểm tra, không phải kết luận pháp lý.
