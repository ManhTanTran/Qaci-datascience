# Hướng dẫn vận hành

Hướng dẫn Windows hiện hành nằm trong [README.md](../README.md). Các bước vận hành chính:

1. Có thể import registry Top 50 địa bàn gốc trực tiếp từ ZIP bằng `python -m wardprice import-targets --file <Top50 ZIP>`. Lệnh chỉ thêm/cập nhật `ward_target_legacy`; số lượng khách hàng không được đưa vào Gemini prompt.
2. Xem rank và trạng thái đối chiếu bằng `python -m wardprice targets`. Mã hành chính trống không được xem là hợp lệ; target registry không tự thay whitelist tìm kiếm.
3. Rà soát `config/wards.csv`; các cột chính là `ward_code,ward_name,province`, `district` tùy chọn để phân biệt địa bàn. Mã `TOP50-*` là mã nội bộ, không phải mã hành chính.
4. Chạy `python -m wardprice validate-registry`, sau đó `python -m wardprice import-wards --file config/wards.csv`.
5. Chạy `python -m wardprice run --wards <ma1>,<ma2>` để xem dry-run 2 phường.
6. Kiểm tra quota và chi phí trong Google AI Studio; chỉ sau khi chấp thuận mới chạy `--live`.
7. Xem `python -m wardprice listings`, `python -m wardprice status`, rồi xuất bằng `python -m wardprice export`.
8. Gmail và Task Scheduler đều cần cấu hình và thao tác bật riêng, không được kích hoạt tự động.

Không nhập dữ liệu ước tính AI cũ vào thống kê listing. Các valuation cũ được giữ trong SQLite và workbook ở sheet riêng.
