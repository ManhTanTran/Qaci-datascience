# Home Credit Bureau Spark parity candidate

## Mục tiêu

Mô tả implementation Spark của block research candidate `bureau-v1`. Spark đọc
`bureau.csv` và `bureau_balance.csv`, thực hiện đầy đủ hai tầng aggregation rồi
ghi một candidate Parquet riêng. Mục tiêu là chứng minh parity với pandas, không
thay đổi feature, model hay experiment E03.

## Khái niệm chính

Reference pandas nằm tại
`src/credit_scoring/features/home_credit_bureau.py`, builder version `bureau-v1`.
Candidate Spark nằm tại
`src/credit_scoring/features/home_credit_bureau_spark.py`, builder version
`bureau-v1-spark-smoke`. Hai implementation dùng cùng 61 tên feature, cùng thứ
tự và cùng mapping `counts`, `amounts`, `recency`, `delinquency`.

Luồng Spark là raw CSV → tạo `STATUS_SEVERITY`, `IS_OBSERVED`, `IS_DPD` → aggregate
theo `SK_ID_BUREAU` → join one-to-one với Bureau → tạo active/closed/overdue và
ratio → aggregate theo `SK_ID_CURR` → ghi candidate Parquet cùng manifest JSON.
`STATUS="X"` là unobserved; amount sum của nhóm toàn null giữ null; denominator
zero/null trả null; giá trị âm không bị clip.

Candidate mặc định được ghi thành
`bureau_spark_candidate.parquet` và
`bureau_spark_candidate.manifest.json`. Writer dùng chế độ không overwrite và
không bao giờ dùng tên block reference `bureau`.

## Ví dụ trong credit scoring

Một loan có status `0, 1, 3, X` có bốn tháng lịch sử nhưng chỉ ba tháng observed.
DPD share bằng `2/3`, không phải `2/4`, vì `X` không mang bằng chứng rằng khách
hàng không delinquent. Spark và pandas phải trả cùng null policy và cùng giá trị
trong tolerance `rtol=1e-5`, `atol=1e-6`.

## Điều cần kiểm tra trong project

- [x] Output schema và family mapping khai báo cố định trong source.
- [x] Unit test không cần Spark vẫn đối chiếu contract với pandas.
- [x] Spark runtime và full raw-data Kaggle smoke hoàn tất trên Spark `4.0.2`.
- [x] Candidate có 305.811 row/unique key; application merge giữ 356.255 row.
- [x] Fixture parity: 17 exact columns và 44 float columns có 0 mismatch;
  null mismatch bằng 0, max absolute difference `7,95e-08`.
- [x] Full parity local với block pandas `bureau-v1`: 305.811 rows, 61 feature,
  key set/schema/order/family mapping/null mask đều khớp; 0 value mismatch và
  0 infinity với `rtol=1e-5`, `atol=1e-6`.
- [ ] Full candidate được so với reference `bureau-v1` khi reference path có sẵn.
- [ ] Chỉ promote builder version mới sau khi full-block parity PASS.

## Tài liệu liên quan

- [Home Credit auxiliary features](home_credit_auxiliary_features.md)
- [Feature store](feature_store.md)
- [Bureau feature concepts](bureau_features.md)
- Notebook: `notebooks/03_home_credit_multitable/00_spark_bureau_parity_smoke.ipynb`

## Trạng thái áp dụng trong project

Đây là Spark research candidate, chưa thay thế pandas reference và chưa được
promote. Kaggle smoke version 3 PASS cho fixture và full Spark structural checks.
Ngày 2026-08-09, candidate tải từ Kaggle đã được full-compare local với block
pandas `bureau-v1` và PASS. Promotion vẫn là quyết định review riêng; Parquet,
manifest và diagnostics nằm ngoài Git.
