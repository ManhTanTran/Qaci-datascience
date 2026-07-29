# Temporal validation và OOT

## Mục tiêu

Mô phỏng mô hình được học từ quá khứ và dùng trong tương lai.

## Khái niệm chính

Chọn cut-off theo business time, giữ gap khi label maturity đòi hỏi, kiểm tra feature availability và cohort shift. OOT không phải tập tuning lặp đi lặp lại.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Train trên các cohort cũ, validate cohort kế tiếp và khóa một cohort tương lai làm OOT.

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
