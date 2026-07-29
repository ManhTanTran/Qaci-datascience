# Temporal features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát temporal features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Độ dài, recency và seasonality hợp lệ theo cut-off.
- **Feature ví dụ:** credit history length, months since event
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Lịch sử dài có thể gắn ổn định hơn; recency xấu có thể tăng rủi ro.
- **Cách tính:** difference giữa cut-off và event date
- **Nguy cơ missing:** ngày không đầy đủ
- **Nguy cơ outlier:** future/placeholder dates
- **Nguy cơ leakage:** tính bằng ngày extract tương lai
- **Thời điểm có sẵn:** tại cut-off

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Feature cần học từ nguồn công khai

- Credit history length tại cut-off.
- Days/months since latest valid credit, payment, delinquency hoặc application event.
- Record count và active-month coverage trong lookback window.
- Rolling count/mean/max theo các window đã khóa.
- Trend/slope chỉ khi event time đủ dày và không nhìn qua decision time.
- Cohort/week/month index dùng cho validation/monitoring; không mặc định là predictor production.
- Không dùng ngày chạy pipeline làm mốc thay cho observation/as-of date.

## Ví dụ trong credit scoring

Trước khi đăng ký `credit history length`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
