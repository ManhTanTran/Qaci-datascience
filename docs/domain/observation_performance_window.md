# Observation window và performance window

## Mục tiêu

Ngăn chặn việc trộn dữ liệu quá khứ dùng làm predictor với tương lai dùng làm outcome.

## Khái niệm chính

Observation window kết thúc tại as-of/decision time; performance window bắt đầu sau mốc đó. Cần thêm maturity rule để tránh right censoring.



## Ví dụ trong credit scoring

Lịch sử trả nợ trước application có thể tạo feature; hành vi sau application thuộc performance window và không phải feature application-time.

## Điều cần kiểm tra trong project

- [ ] Xác nhận thuật ngữ với business và risk.
- [ ] Gắn định nghĩa với population và thời điểm.
- [ ] Ghi rõ giả định, owner và version.

## Tài liệu liên quan

- [Trang chủ](../index.md)
- [Target](target_definition.md)
- [Window](observation_performance_window.md)
- [Business metrics](business_metrics.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
