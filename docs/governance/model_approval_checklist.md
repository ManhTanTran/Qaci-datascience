# Model approval checklist

## Mục tiêu

Định nghĩa bằng chứng tối thiểu trước production.

## Khái niệm chính

Cần approved target/population, data/feature lineage, validation độc lập, performance/calibration/stability/fairness, implementation tests, model card, monitoring và rollback.

## Quy tắc bắt buộc

- Không commit dữ liệu khách hàng; không đưa PII hoặc dữ liệu tín dụng thật vào prompt; không log thông tin định danh.
- Không dùng feature sau thời điểm quyết định cho vay và không tự ý dùng thuộc tính nhạy cảm.
- Không tự ý thay đổi target. Mọi feature production phải có nguồn, công thức và owner.
- Mọi model production phải có model card. Thay đổi metric hoặc validation phải có decision record.

## Ví dụ trong credit scoring

Model chưa có owner, OOT result hoặc monitoring plan không đạt approval readiness.

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
