# Phase E4 — hardening chất lượng dữ liệu

**Ngày:** 2026-10-15. Phase này chỉ xử lý sample TiniX AI 10.000 dòng và pilot
SQLite riêng. Không tải thêm dữ liệu, không crawl, không gọi Gemini, không đổi
production/demo database và không bật lịch.

E4 sửa ngữ nghĩa metrics của collector để phân biệt candidate được phát hiện,
candidate mới, cập nhật và deduplicate; thêm CSV review thủ công nhưng giữ trống
toàn bộ nhãn con người; bổ sung quy tắc ánh xạ tiêu đề thận trọng; kiểm toán
đơn vị/outlier; và áp quality gate theo cỡ mẫu vào API/UI lịch sử.

Kết quả pilot sau E4: 1.190 candidate duy nhất trên 48/50 địa bàn; 18 loại đất
được ánh xạ `DAT_O` theo cụm tiêu đề chính xác, 191 vẫn `UNKNOWN`; 473 bản ghi
đủ điều kiện thống kê lịch sử (312 `NHA_RIENG`, 156 `CHUNG_CU`, 5 `DAT_O`). Tất
cả còn `HISTORICAL_DATASET_UNVERIFIED`, không vào `CURRENT_VERIFIED`, `DAILY_NEW`
hay AI context.

100 tiêu đề review có 25 dòng mỗi lớp rule-based. Chưa có nhãn người rà soát nên
không tính confusion matrix, precision, recall, F1, coverage hay abstention.
Trong 9.216 cặp giá/diện tích dương hợp lệ, Tukey toàn mẫu gắn cờ 403 dòng; đây
chỉ là tín hiệu rà soát. Không xóa bản ghi. 154 giá không hợp lệ nhưng không-null
đều là số 0, không phải lỗi parse chuỗi. Dataset không có URL tin riêng hoặc
trường phân biệt diện tích đất với diện tích sàn.

Quality levels: n<5 `INSUFFICIENT_SAMPLE`; 5≤n<10 `LOW_CONFIDENCE`; n≥10
`DESCRIPTIVE_SAMPLE`. Đây là phân loại cỡ mẫu, không chứng minh độ đại diện.

Backup pilot trước khi cập nhật mapping:
`state/backups/ward_prices.historical_pilot.pre_e4_property_mapping_20261014T184548_0fddd5Z.sqlite3`
(SQLite integrity check `ok`; schema vẫn `user_version=3`).

Xem [báo cáo kiểm toán chi tiết ở repository cha](../../docs/datasets/wardpricedaily_phase_e4_quality_report.md)
và [hướng dẫn review/audit trong README](../README.md#kiểm-toán-chất-lượng-phase-e4-offline).
