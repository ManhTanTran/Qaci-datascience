# Câu hỏi cho mentor hoặc data owner

## Mục tiêu

Tập trung các câu hỏi nội bộ cần xác nhận mà không đưa PII hoặc dữ liệu khách hàng vào tài liệu.

## Khái niệm chính

Mỗi câu hỏi cần owner, ngày hỏi, quyết định và tài liệu/ADR cập nhật sau khi trả lời.

## Câu hỏi mở

- TODO(FPT): cần xác nhận với mentor hoặc data owner.
  Target event, DPD threshold, cure và indeterminate class là gì?
- TODO(FPT): cần xác nhận với mentor hoặc data owner.
  Observation point và performance window được khóa như thế nào?
- TODO(FPT): cần xác nhận với mentor hoặc data owner.
  Grain, key, source owner và refresh cadence của từng bảng là gì?
- TODO(FPT): cần xác nhận với mentor hoặc data owner.
  Feature/thuộc tính nào bị cấm hoặc cần phê duyệt fairness?
- TODO(FPT): cần xác nhận với mentor hoặc data owner.
  Production metric, validation và business threshold đã được phê duyệt là gì?

## Ví dụ trong credit scoring

Sau khi mentor xác nhận target, cập nhật target definition và tạo decision record nếu metric/validation thay đổi.

## Điều cần kiểm tra trong project

- [ ] Không ghi tên, ID, số hợp đồng hoặc dữ liệu tín dụng thật.
- [ ] Đóng câu hỏi bằng link tới quyết định/tài liệu đã cập nhật.
- [ ] Không biến câu trả lời miệng thành policy nếu chưa có owner/version.

## Tài liệu liên quan

- [FPT application stage](../learning/08_fpt_dataset_application.md)
- [Decision records](../decisions/README.md)
- [Data privacy](../governance/data_privacy.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
