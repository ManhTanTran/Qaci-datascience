# Demographic features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát demographic features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Thông tin mô tả cá nhân/hộ gia đình tại application time.
- **Feature ví dụ:** tuổi theo bucket hoặc household size
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Quan hệ kỳ vọng tùy population; dễ là proxy cho thuộc tính nhạy cảm.
- **Cách tính:** chuẩn hóa từ application record, ưu tiên bucket có lý do
- **Nguy cơ missing:** không khai báo
- **Nguy cơ outlier:** giá trị phi thực tế
- **Nguy cơ leakage:** fairness/proxy leakage
- **Thời điểm có sẵn:** application time nếu được phép

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Ví dụ trong credit scoring

Trước khi đăng ký `tuổi theo bucket hoặc household size`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
