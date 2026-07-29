# Credit bureau features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát credit bureau features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Quan hệ tín dụng và nghĩa vụ tại tổ chức khác.
- **Feature ví dụ:** active accounts, utilization, inquiries
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Nợ/utilization/inquiry cao có thể gắn rủi ro cao hơn.
- **Cách tính:** aggregate theo borrower và as-of bureau pull
- **Nguy cơ missing:** thin file/no hit
- **Nguy cơ outlier:** duplicate tradeline
- **Nguy cơ leakage:** bureau refresh sau decision
- **Thời điểm có sẵn:** bureau snapshot tại application

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Feature cần học từ nguồn công khai

- Active/closed account counts và open credit-line count.
- Secured/unsecured hoặc credit-type mix.
- Revolving utilization và aggregate balance/limit.
- Credit history length, newest/oldest account age và inquiry/delinquency recency.
- Maximum DPD, delinquency frequency/severity và status transition.
- Aggregate external scores chỉ sau khi xác minh source, meaning, licensing và availability.
- No-hit/thin-file flag phải phân biệt với lỗi lấy dữ liệu.

## Ví dụ trong credit scoring

Trước khi đăng ký `active accounts`, kiểm tra availability tại thời điểm application và stability theo thời gian.

## Điều cần kiểm tra trong project

- [ ] Xác nhận source column với schema thật.
- [ ] Kiểm tra expected direction và phi tuyến bằng dữ liệu.
- [ ] Review leakage, fairness và permitted_for_modeling.

## Tài liệu liên quan

- [Feature catalog](feature_catalog.md)
- [Feature groups](feature_groups.md)
- [Leakage](leakage_checklist.md)
- [Stability](feature_stability.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
