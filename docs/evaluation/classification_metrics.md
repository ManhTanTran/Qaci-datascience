# Classification metrics

## Mục tiêu

Giải thích Accuracy, Precision, Recall, F1, ROC-AUC, PR-AUC, Log Loss và Brier Score.

## Khái niệm chính

Accuracy phụ thuộc threshold/base rate; Precision là tỷ lệ bad trong predicted bad; Recall là tỷ lệ bad được bắt; F1 cân bằng precision/recall. ROC-AUC đo ranking; PR-AUC nhạy với prevalence; Log Loss phạt xác suất tự tin sai; Brier là mean squared probability error.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## Ví dụ trong credit scoring

Không chọn model chỉ bằng Accuracy trên dataset mất cân bằng; báo PR curve và calibration.

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
