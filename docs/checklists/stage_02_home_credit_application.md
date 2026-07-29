# Checklist stage 02 — Home Credit application

## Mục tiêu

Xác nhận đã tái tạo baseline application-table bằng code hiện hành và có kiểm soát.

## Khái niệm chính

Notebook ngoài là nguồn học; source module, test và validation của project mới là bằng chứng.

## Checklist hoàn thành

- [ ] Đọc competition overview, data dictionary và dataset card.
- [ ] Kiểm tra train/test schema và category alignment.
- [ ] Profile `DAYS_EMPLOYED` sentinel và missingness.
- [ ] Kiểm tra `EXT_SOURCE` availability/semantics.
- [ ] Tạo ratio features với zero-denominator policy.
- [ ] Tái tạo Logistic baseline bằng pipeline.
- [ ] So sánh model/feature trên local validation.
- [ ] Thay mọi API notebook đã lỗi thời.

## Ví dụ trong credit scoring

Một cờ anomaly có thể giữ thông tin quy trình trong khi giá trị sentinel gốc được chuyển thành missing.

## Điều cần kiểm tra trong project

- [ ] Transform chỉ fit trên training fold.
- [ ] Không dùng leaderboard để chọn feature cuối.
- [ ] Không kết luận causality từ correlation/importance.

## Tài liệu liên quan

- [Stage 02](../learning/02_home_credit_gentle_introduction.md)
- [Notebook review](../references/kaggle_notebooks.md)
- [Missing/outlier](../features/missing_and_outliers.md)
- [Ratio features](../features/ratio_features.md)

## Trạng thái áp dụng trong project

Nguồn công khai được rà soát ngày 2026-07-29.
