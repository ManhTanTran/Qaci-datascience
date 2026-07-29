# Income and employment features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát income and employment features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Khả năng tạo thu nhập và độ ổn định nghề nghiệp.
- **Feature ví dụ:** income, employment tenure, income type
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Thu nhập/tenure cao có thể gắn rủi ro thấp hơn nhưng không phải quan hệ nhân quả.
- **Cách tính:** đơn vị tiền tệ nhất quán; tenure từ ngày hợp lệ
- **Nguy cơ missing:** self-employed/không khai báo
- **Nguy cơ outlier:** income cực lớn hoặc tenure âm
- **Nguy cơ leakage:** dùng ngày cập nhật sau quyết định
- **Thời điểm có sẵn:** application time nếu đã xác minh

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Ví dụ trong credit scoring

Trước khi đăng ký `income`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
