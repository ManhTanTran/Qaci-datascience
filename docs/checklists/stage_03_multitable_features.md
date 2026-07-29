# Checklist stage 03 — Multi-table features

## Mục tiêu

Kiểm soát grain, key, aggregation và point-in-time logic trong data mart nhiều bảng.

## Khái niệm chính

Mỗi bảng phụ phải được aggregate về grain của base table trước join; mọi feature có lineage và cut-off.

## Checklist hoàn thành

- [ ] Lập data model với primary/foreign key và cardinality.
- [ ] Assert uniqueness ở base grain trước/sau từng join.
- [ ] Xác định event time và cut-off cho mỗi bảng.
- [ ] Tách missing “không có lịch sử” khỏi missing “không biết”.
- [ ] Tạo count, recency, frequency, severity và trend aggregates.
- [ ] Kiểm tra duplicate tradeline/payment/event.
- [ ] Viết unit test cho boundary time và aggregation.
- [ ] Đăng ký feature candidate trong feature registry.

## Ví dụ trong credit scoring

Join trực tiếp installments vào application làm một application xuất hiện nhiều lần; cần aggregate trước join.

## Điều cần kiểm tra trong project

- [ ] Không dùng sự kiện sau decision time.
- [ ] Không fit aggregation policy bằng test set.
- [ ] Theo dõi compute cost và reproducibility.

## Tài liệu liên quan

- [Stage 04](../learning/04_home_credit_default_risk.md)
- [Feature engineering](../features/feature_engineering.md)
- [Leakage](../features/leakage_checklist.md)
- [Reproducibility](../governance/reproducibility.md)

## Trạng thái áp dụng trong project

Mapping source tables của FPT là `TODO(FPT): cần xác nhận với mentor hoặc data owner.`
