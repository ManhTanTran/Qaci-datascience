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

## Trạng thái áp dụng trong project

Đã triển khai stratified OOF runner, exactly-once validation và precomputed
fold fingerprint. Chưa có temporal/OOT artifact verified.
