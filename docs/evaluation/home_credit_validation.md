# Home Credit validation

## Mục tiêu

Đảm bảo application-only baseline tạo OOF prediction đúng cách và không dùng
test set trong lựa chọn model.

## Khái niệm chính

Validation mặc định là `StratifiedKFold(n_splits=5, shuffle=True,
random_state=42)`. Mỗi fold fit riêng, early stopping trên validation fold,
ghi prediction vào đúng vị trí OOF, tính ROC-AUC và lưu best iteration.

So sánh E01/E02 tạo danh sách fold đúng một lần rồi truyền chính các index đó
cho cả hai lượt chạy. Runner xác minh mỗi sample nằm trong validation đúng một
lần và lưu SHA-256 fingerprint của fold assignment. Experiment phải dừng nếu
hai fingerprint khác nhau. E02 giữ nguyên target, ROC-AUC, seed, số fold,
early stopping và cấu hình LightGBM của E01; tuning bị loại khỏi experiment.

Đây là baseline competition validation. Temporal/OOT validation vẫn cần được
đánh giá riêng nếu chuyển sang use case có calendar time và performance window
được xác nhận.

## Ví dụ trong credit scoring

OOF AUC dùng cho diagnostics và ablation. Public/private leaderboard không
được dùng thay cho validation evidence.

## Điều cần kiểm tra trong project

- [ ] OOF coverage đúng một prediction cho mỗi hàng train.
- [ ] Train/test feature columns giống nhau.
- [ ] Chỉ target train xuất hiện trong metric calculation.
- [ ] Báo cáo fold mean, std và OOF AUC cùng runtime.
- [x] Có fold fingerprint để chứng minh E01/E02 dùng cùng split.
- [ ] Tạo decision record nếu thay đổi validation strategy.

## Tài liệu liên quan

- [Validation strategy](validation_strategy.md)
- [Cross-validation](cross_validation.md)
- [Credit risk metrics](credit_risk_metrics.md)
- Source: `src/credit_scoring/evaluation/cross_validation.py`
- Comparison runner: `src/credit_scoring/experiments/home_credit_application.py`
- Credit/amount factorial helpers:
  `src/credit_scoring/experiments/home_credit_credit_amount_factorial.py`

## Trạng thái áp dụng trong project

Đã triển khai stratified OOF runner, exactly-once validation và precomputed
fold fingerprint. Chưa có temporal/OOT artifact verified.

## Hợp đồng validation cho factorial ablation

Notebook factorial tạo fold list một lần rồi truyền cùng object này cho cả tám
experiment `E01_LOCKED`, `E02-N`, `E02-R`, `E02-D`, `E02-RD`, `E02-NR`,
`E02-ND` và `E02-NRD`. Mỗi result phải có cùng fold fingerprint và
`VALIDATION_COUNT == 1` cho mọi hàng train.

Chỉ baseline mode 5-fold đầy đủ mới được phép chọn `E02-FINAL`.
Candidate phải có global OOF AUC cao hơn E01, delta dương ít nhất 4/5 fold
và fold standard deviation không tăng quá `0.0005`. Trong tolerance
`1e-5`, quy tắc tie-break ưu tiên ít feature hơn và ít ghi đè E01 hơn.
Smoke mode không tạo `E02-FINAL`, không tạo submission và không được ghi
metric vào experiment log.
