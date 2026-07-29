# Fairness và bias

## Mục tiêu

Đánh giá tác động bất lợi và proxy risk theo khung pháp lý/chính sách được phê duyệt.

## Khái niệm chính

Fairness metric phụ thuộc use case, protected groups, labels và policy. Không tự truy cập/derive thuộc tính nhạy cảm; cần review pháp lý và governance.

## Quy tắc bắt buộc

- Không commit dữ liệu khách hàng; không đưa PII hoặc dữ liệu tín dụng thật vào prompt; không log thông tin định danh.
- Không dùng feature sau thời điểm quyết định cho vay và không tự ý dùng thuộc tính nhạy cảm.
- Không tự ý thay đổi target. Mọi feature production phải có nguồn, công thức và owner.
- Mọi model production phải có model card. Thay đổi metric hoặc validation phải có decision record.

## Ví dụ trong credit scoring

So sánh error/approval outcomes chỉ khi thuộc tính, phương pháp và mục đích đã được phép.

## Điều cần kiểm tra trong project

- [ ] Xác nhận owner và approver.
- [ ] Lưu evidence/exception có thời hạn.
- [ ] Escalate khi policy, pháp lý hoặc dữ liệu chưa rõ.

## Tài liệu liên quan

- [Data privacy](data_privacy.md)
- [Model risks](model_risks.md)
- [Fairness](fairness_and_bias.md)
- [Approval](model_approval_checklist.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
