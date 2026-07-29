# WOE, IV và binning

## Mục tiêu

Giải thích binning phục vụ scorecard có kiểm soát.

## Khái niệm chính

WOE mã hóa log tỷ lệ good/bad theo bin; IV tóm tắt separation. Binning phải fit trên train, xử lý zero count, missing/special values, monotonicity và stability. IV không chứng minh causal importance.



## Ví dụ trong credit scoring

Fit bin edges trên train, khóa edges và kiểm tra bad rate/order trên OOT.

## Điều cần kiểm tra trong project

- [ ] So sánh với Dummy và Logistic baseline.
- [ ] Tách train/validation/test trước feature selection và tuning.
- [ ] Đánh giá explainability, calibration, overfit và trường hợp sử dụng.

## Tài liệu liên quan

- [Tổng quan](modeling_overview.md)
- [Model selection](model_selection.md)
- [Calibration](calibration.md)
- [Validation](../evaluation/validation_strategy.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
