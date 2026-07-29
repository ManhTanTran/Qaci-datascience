# Stage 06 — WOE và credit scorecard

## Mục tiêu

Xây chuỗi có thể kiểm toán từ binning đến score, score band và reason code.

## Khái niệm chính

Thứ tự: binning → good/bad distribution → WOE → IV → Logistic Regression → PD/calibration → score scaling → score bands → reason codes.

## Kiến thức và điều kiện hoàn thành

- Fit bin edges/merges trên training data và khóa trước validation/OOT.
- Xử lý missing/special values bằng bin riêng có lý do.
- Kiểm tra minimum bin size, monotonicity, stability và outlier policy.
- Không dùng IV đơn biến như bằng chứng đủ để chọn feature; kiểm tra correlation/redundancy và validation.
- Chuyển log-odds thành score bằng base score, base odds và PDO đã tài liệu hóa.
- Reason code phải phản ánh contribution có thể tái tạo, không suy diễn nguyên nhân.

Artifact đề xuất: binning/WOE/IV module, scorecard, validation report và model card.

## Ví dụ trong credit scoring

Một bin có WOE cực lớn do rất ít bad phải được gộp hoặc regularize theo policy đã khóa, không giữ chỉ vì IV tăng.

## Điều cần kiểm tra trong project

- [ ] Hoàn thành [stage 04 checklist](../checklists/stage_04_scorecard.md).
- [ ] Ghi mọi experiment thật vào experiment log.
- [ ] Không dùng notebook WOE ngoài chưa truy cập/xác minh làm nguồn chuẩn.

## Tài liệu liên quan

- [WOE/IV/binning](../modeling/woe_iv_binning.md)
- [Logistic Regression](../modeling/logistic_regression.md)
- [Credit scorecard](../modeling/credit_scorecard.md)
- [Calibration](../modeling/calibration.md)

## Trạng thái áp dụng trong project

Tham số score scaling và policy binning cho FPT là `TODO(FPT): cần xác nhận với mentor hoặc data owner.`
