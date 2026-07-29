# Trạng thái hiện tại

## Mục tiêu

Tạo bảng điều khiển ngắn cho trạng thái tài liệu và các quyết định còn mở.

## Khái niệm chính

Trạng thái dùng các nhãn `not_started`, `in_progress`, `blocked`, `review` và `done`; không suy diễn tiến độ từ việc file đã tồn tại.



## Ví dụ trong credit scoring

Knowledge base có thể `done` về cấu trúc nhưng target definition vẫn `blocked` cho đến khi data owner xác nhận.

## Điều cần kiểm tra trong project

- [ ] Gắn owner và ngày review cho từng cột mốc.
- [ ] Đối chiếu trạng thái với artifact thực tế.
- [ ] Ghi blocker bằng TODO(FPT), không tự điền giả định.

## Tài liệu liên quan

- [Trang chủ](../index.md)
- [Experiment log](../experiments/experiment_log.md)
- [Checklist phê duyệt](../governance/model_approval_checklist.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
