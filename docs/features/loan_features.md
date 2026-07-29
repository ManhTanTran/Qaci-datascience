# Loan application features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát loan application features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Đặc điểm khoản vay được yêu cầu.
- **Feature ví dụ:** amount, annuity, term, product type
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Khoản vay/gánh nặng lớn có thể tăng rủi ro, phụ thuộc pricing và selection.
- **Cách tính:** lấy từ offer/application version đúng thời điểm
- **Nguy cơ missing:** sản phẩm không có annuity
- **Nguy cơ outlier:** amount/term bất thường
- **Nguy cơ leakage:** dùng final outcome hoặc renegotiated terms
- **Thời điểm có sẵn:** trước quyết định

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Ví dụ trong credit scoring

Trước khi đăng ký `amount`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
