# Lộ trình học credit scoring

## Mục tiêu

Sắp xếp kiến thức theo thứ tự từ bài toán, dữ liệu, feature, baseline, validation đến governance và monitoring.

## Khái niệm chính

Lộ trình đề xuất: (1) hiểu lending/target/window; (2) đọc dataset card; (3) EDA và leakage; (4) Dummy → Logistic → Tree → boosting → scorecard; (5) calibration và threshold; (6) temporal validation; (7) model card và monitoring.

## Thứ tự dùng tài liệu thực hành

Thứ tự chi tiết, artifact và điều kiện hoàn thành đã được tách thành [Learning track](../learning/index.md). Tuyến chính là foundation → Give Me Some Credit → Home Credit application → complete EDA → multi-table → segment/trend → scorecard → model stability → FPT.

Trang roadmap này giữ bức tranh tổng thể; `docs/learning/` là nguồn chuẩn cho thứ tự học thực hành.



## Ví dụ trong credit scoring

Người mới bắt đầu với Give Me Some Credit, dựng Dummy và Logistic baseline, sau đó mới so sánh mô hình cây.

## Điều cần kiểm tra trong project

- [ ] Gắn owner và ngày review cho từng cột mốc.
- [ ] Đối chiếu trạng thái với artifact thực tế.
- [ ] Ghi blocker bằng TODO(FPT), không tự điền giả định.

## Tài liệu liên quan

- [Trang chủ](../index.md)
- [Đánh giá Kaggle notebooks](../references/kaggle_notebooks.md)
- [Experiment log](../experiments/experiment_log.md)
- [Checklist phê duyệt](../governance/model_approval_checklist.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
