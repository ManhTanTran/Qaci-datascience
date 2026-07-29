# Prohibited features

## Mục tiêu

Ngăn feature không được phép hoặc không sẵn có đi vào model.

## Khái niệm chính

Cấm mặc định: post-decision/outcome leakage, identifier thuần, PII không cần thiết và thuộc tính nhạy cảm chưa được phê duyệt. Danh sách chính thức phải do governance xác nhận.

## Quy tắc bắt buộc

- Không commit dữ liệu khách hàng; không đưa PII hoặc dữ liệu tín dụng thật vào prompt; không log thông tin định danh.
- Không dùng feature sau thời điểm quyết định cho vay và không tự ý dùng thuộc tính nhạy cảm.
- Không tự ý thay đổi target. Mọi feature production phải có nguồn, công thức và owner.
- Mọi model production phải có model card. Thay đổi metric hoặc validation phải có decision record.

## Mẫu outcome leakage cần nhận diện

Với application scoring, các trường chỉ hình thành sau giải ngân hoặc sau khi outcome xảy ra mặc định bị cấm cho đến khi chứng minh được availability hợp lệ. Ví dụ thường gặp:

- recoveries, collection amount hoặc debt-settlement outcome;
- principal/interest/late fee đã thu;
- outstanding principal đo sau observation point;
- last payment amount/date hoặc next payment date;
- trạng thái charged-off/default phát sinh trong performance window;
- feature dùng ngày chạy notebook thay cho decision/as-of date.

Các trường này có thể hợp lệ cho một use case behavioral/collections khác, nhưng phải định nghĩa lại population, observation point và target; không được tái sử dụng mặc định.

## Ví dụ trong credit scoring

Tên/ID khách hàng không phải predictor; collection status sau giải ngân là leakage cho application model.

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
