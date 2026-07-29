# Credit Scoring Knowledge Base

## Mục tiêu

Tạo một điểm vào duy nhất cho kiến thức miền, dữ liệu, feature, mô hình, đánh giá, giám sát và quản trị của project credit scoring.

## Khái niệm chính

Knowledge base này tách **kiến thức chuẩn** khỏi **quyết định riêng của project**. Nội dung có tính hướng dẫn không thay thế chính sách tín dụng, phê duyệt pháp lý hay xác nhận của data owner. Mọi giả định nội bộ chưa được xác nhận phải mang marker `TODO(FPT)`.



## Ví dụ trong credit scoring

Một thay đổi từ random split sang out-of-time validation phải cập nhật decision record, tài liệu validation và registry của model liên quan.

## Điều cần kiểm tra trong project

- [ ] Xác nhận chủ sở hữu cho dataset, feature và model production.
- [ ] Không đưa dữ liệu khách hàng, PII hoặc bí mật nội bộ vào repository.
- [ ] Giữ registry, card, experiment log và decision record đồng bộ.

## Tài liệu liên quan

- [Lộ trình học](roadmap/learning_path.md)
- [Tổng quan credit scoring](domain/credit_scoring_overview.md)
- [Danh mục dataset](datasets/dataset_catalog.md)
- [Danh mục feature](features/feature_catalog.md)
- [Tổng quan modeling](modeling/modeling_overview.md)
- [Kế hoạch monitoring](monitoring/monitoring_plan.md)
- [Checklist phê duyệt](governance/model_approval_checklist.md)

## Trạng thái áp dụng trong project

Bộ khung knowledge base đã được khởi tạo. Trạng thái nghiệp vụ và production vẫn cần xác nhận theo từng trang.
