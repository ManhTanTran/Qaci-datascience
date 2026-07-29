# Experiment log

## Mục tiêu

Lập chỉ mục experiment có thể tái lập mà không tạo kết quả giả.

## Khái niệm chính

Mỗi dòng cần ID, ngày, owner, hypothesis, dataset/feature/model version, validation, artifact path, trạng thái và link report.



## Ví dụ trong credit scoring

Chỉ thêm metric sau khi run artifact tồn tại và được kiểm tra; hiện chưa đăng ký kết quả thực nghiệm.

## Điều cần kiểm tra trong project

- [ ] Chỉ ghi kết quả từ artifact có thể truy vết.
- [ ] Không dùng test để lựa chọn.
- [ ] Cập nhật registry/decision record khi phù hợp.

## Tài liệu liên quan

- [Experiment template](experiment_template.md)
- [Baseline results](baseline_results.md)
- [Model selection](../modeling/model_selection.md)

## Trạng thái áp dụng trong project

Chưa có experiment artifact hoặc kết quả thực nghiệm được xác minh trong workspace.
