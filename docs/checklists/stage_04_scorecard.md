# Checklist stage 04 — Scorecard

## Mục tiêu

Xác nhận scorecard có binning, scaling, validation và governance có thể kiểm toán.

## Khái niệm chính

WOE/IV và score scaling phải được fit/khóa đúng split; interpretability không thay thế validation.

## Checklist hoàn thành

- [ ] Định nghĩa good/bad/indeterminate và sample.
- [ ] Fit binning trên training data.
- [ ] Có missing/special-value bins và minimum bin size.
- [ ] Báo WOE, IV, event count và non-event count.
- [ ] Kiểm tra monotonicity và bin stability trên validation/OOT.
- [ ] Fit Logistic Regression và kiểm tra multicollinearity.
- [ ] Tài liệu hóa base score, base odds và PDO.
- [ ] Kiểm tra calibration, score bands và reason codes.

## Ví dụ trong credit scoring

Không gộp bin dựa trên bad rate của OOT vì làm mất vai trò đánh giá độc lập.

## Điều cần kiểm tra trong project

- [ ] Không chọn feature chỉ vì IV cao.
- [ ] Reason code không được diễn giải thành nguyên nhân.
- [ ] Model production cần model card.

## Tài liệu liên quan

- [Stage 06](../learning/06_woe_credit_scorecard.md)
- [WOE/IV](../modeling/woe_iv_binning.md)
- [Scorecard](../modeling/credit_scorecard.md)
- [Model card template](../templates/model_card_template.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
