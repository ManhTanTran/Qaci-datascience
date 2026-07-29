# Repayment behavior features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát repayment behavior features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Hành vi thanh toán lịch sử trước hồ sơ hiện tại.
- **Feature ví dụ:** paid-to-due ratio, late payment frequency
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Trả chậm lịch sử thường gắn với rủi ro cao hơn.
- **Cách tính:** aggregate event có timestamp trước cut-off
- **Nguy cơ missing:** lịch sử không phủ đủ
- **Nguy cơ outlier:** payment reversal/correction
- **Nguy cơ leakage:** payment sau decision
- **Thời điểm có sẵn:** chỉ phần lịch sử trước cut-off

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Ví dụ trong credit scoring

Trước khi đăng ký `paid-to-due ratio`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
