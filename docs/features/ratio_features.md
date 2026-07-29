# Ratio features

## Mục tiêu

Chuẩn hóa cách hiểu và kiểm soát ratio features.

## Khái niệm chính

Mọi feature cần provenance, công thức, cut-off time, missing/outlier policy, owner và permitted flag.

## Hồ sơ nhóm feature

- **Ý nghĩa nghiệp vụ:** Chuẩn hóa nghĩa vụ theo năng lực hoặc limit.
- **Feature ví dụ:** debt-to-income, loan-to-income, utilization
- **Hướng ảnh hưởng rủi ro kỳ vọng:** Ratio cao thường gắn rủi ro cao hơn nhưng có thể phi tuyến.
- **Cách tính:** tử/mẫu cùng đơn vị; policy cho mẫu 0
- **Nguy cơ missing:** thiếu tử hoặc mẫu
- **Nguy cơ outlier:** mẫu gần 0 tạo cực trị
- **Nguy cơ leakage:** thành phần sau decision
- **Thời điểm có sẵn:** khi mọi thành phần có sẵn

> Expected direction là giả thuyết liên hệ, không phải quan hệ nhân quả và phải được kiểm tra bằng dữ liệu theo cohort.

## Feature cần học từ nguồn công khai

| Feature | Công thức học tập | Kiểm soát chính |
| --- | --- | --- |
| Debt-to-income/debt ratio | debt obligations / income hoặc công thức dataset cung cấp | Đồng nhất kỳ/đơn vị, income missing/zero và cực trị do mẫu số. |
| Credit-to-income | requested/granted credit / income | Xác minh amount dùng tại application time. |
| Annuity-to-income | periodic annuity / periodic income | Đồng nhất tần suất và xử lý income bằng 0. |
| Credit-to-annuity | credit / annuity | Chỉ là proxy cho term khi schedule/interest chưa được biết. |
| Employment-to-age | employment duration / age | Sentinel `DAYS_EMPLOYED`, đơn vị ngày và fairness review. |
| Revolving utilization | balance / limit | Giá trị vượt 1, zero limit và snapshot time. |

## Ví dụ trong credit scoring

Trước khi đăng ký `debt-to-income`, kiểm tra availability tại thời điểm application và stability theo thời gian.

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
