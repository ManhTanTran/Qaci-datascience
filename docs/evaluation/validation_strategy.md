# Validation strategy

## Mục tiêu

Thiết kế bằng chứng generalization phù hợp use case.

## Khái niệm chính

Random split ước lượng IID; stratified giữ class proportion; group split tách entity; temporal split huấn luyện quá khứ/đánh giá tương lai; out-of-time dùng giai đoạn tương lai bị giữ kín để mô phỏng triển khai.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Borrower có nhiều application phải group split hoặc kết hợp temporal/group controls để tránh cùng người ở hai tập.

## Điều cần kiểm tra trong project

- [ ] Gắn metric với population, split và confidence interval.
- [ ] Khóa test set cho đánh giá cuối.
- [ ] Báo discrimination, calibration và business impact cùng nhau.

## Tài liệu liên quan

- [Classification metrics](classification_metrics.md)
- [Credit risk metrics](credit_risk_metrics.md)
- [Validation](validation_strategy.md)
- [Threshold](threshold_selection.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
