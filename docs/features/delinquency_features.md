# Delinquency features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát delinquency features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Mức độ và tần suất quá hạn lịch sử.
- **Feature ví dụ:** max DPD, count 30+ DPD, months since delinquency
- **Hướng ảnh hưởng rủi ro kỳ vọng:** DPD/tần suất cao thường gắn rủi ro cao hơn.
- **Cách tính:** max/count/recency trên observation window
- **Nguy cơ missing:** không có bureau/history
- **Nguy cơ outlier:** sentinel day values
- **Nguy cơ leakage:** DPD trong performance window
- **Thời điểm có sẵn:** trước cut-off

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Feature cần học từ nguồn công khai

- Tách count 30–59, 60–89 và 90+ DPD để học frequency/severity thay vì gộp sớm.
- Kiểm tra sentinel 96/98 trong Give Me Some Credit trước khi coi là số lần quá hạn thật.
- Với lịch sử nhiều bảng, học max DPD, count theo threshold, months since latest delinquency và trend theo observation window.
- Kiểm tra consistency giữa các ngưỡng: số lần 90+ DPD không nên được suy ra trực tiếp từ count nhẹ hơn nếu semantics là các bucket khác nhau.
- Không dùng DPD phát sinh trong performance window làm feature application-time.

## Ví dụ trong credit scoring

Trước khi đăng ký `max DPD`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
