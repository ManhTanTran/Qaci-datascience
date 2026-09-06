# ADR-0005: Validation và báo cáo cho pipeline DC5

## Mục tiêu

Ghi nhận cách so sánh M0-M4 khi chuyển experiment DC5 từ notebook sang pipeline,
đồng thời phân biệt rõ chế độ kiểm tra nhanh với run dùng để báo cáo.

## Khái niệm chính

Notebook cũ dùng một holdout 80/20. Target Telco monetary cao hiếm, nên kết quả từ
một split dễ thay đổi theo mẫu validation. Pipeline dùng `StratifiedKFold` với
cùng fold assignments cho mọi model variant và cả hai setting có/không City.

Quyết định:

- `full` mặc định dùng 5 folds, shuffle và seed 42.
- `quick` giới hạn tối đa 3 folds và chỉ dùng cho phản hồi phát triển.
- ROC-AUC và PR-AUC đều được ghi; PR-AUC luôn đi cùng prevalence và PR lift.
- So sánh M0-M4 phải dùng cùng population và fold assignments.
- UI/report chỉ hiển thị aggregate; không xuất identifier hoặc prediction cấp dòng.

Phương án giữ một holdout nhanh hơn nhưng có độ biến thiên cao. Phương án nested
CV/tuning đầy đủ chưa cần thiết cho research candidate hiện tại và tốn thời gian
vận hành đáng kể.

## Ví dụ trong credit scoring

Nếu positive rate khoảng 3,4%, ROC-AUC có thể vẫn nhìn cao trong khi khả năng tìm
positive yếu. Vì vậy report hiển thị cả PR-AUC, random PR baseline bằng prevalence
và tỷ lệ lift. Không dùng kết quả `quick` để chọn production feature.

## Điều cần kiểm tra trong project

- [x] Fold được tạo một lần và tái sử dụng giữa model variants.
- [x] Mỗi dòng nhận đúng một OOF prediction trong mỗi experiment.
- [x] Report ghi prevalence cạnh PR-AUC.
- [x] Quick/full được phân biệt trong config và metadata.
- [ ] Xác nhận validation phù hợp observation/performance window nội bộ.
- [ ] Chỉ ghi experiment log sau khi có artifact của run thật.

## Tài liệu liên quan

- [Decision index](README.md)
- [DC5 pipeline](../pipelines/dc5_customer_analysis.md)
- [Validation strategy](../evaluation/validation_strategy.md)
- [Classification metrics](../evaluation/classification_metrics.md)

## Trạng thái áp dụng trong project

Proposed ngày 2026-08-21 cho research pipeline. Chưa thay đổi production metric
hoặc validation strategy của một model production. TODO(FPT): cần xác nhận với mentor hoặc data owner.
