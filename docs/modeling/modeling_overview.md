# Tổng quan modeling

## Mục tiêu

Đặt thứ tự học và tiêu chuẩn so sánh model.

## Khái niệm chính

Thứ tự: Dummy → Logistic → Decision Tree → Random Forest → LightGBM/CatBoost → WOE Logistic Scorecard → Calibration → Ensemble khi có lý do.

## Ma trận học và lựa chọn mô hình

| Mô hình | Ý tưởng, input/output | Tiền xử lý | Ưu điểm | Hạn chế, giải thích, calibration và overfit | Khi nên dùng |
|---|---|---|---|---|---|
| Dummy Classifier | Bỏ qua feature; trả class hoặc xác suất theo chiến lược cố định/tỷ lệ lớp | Chỉ cần target và split đúng | Sanity check cho metric và pipeline | Không học tín hiệu, không có giá trị quyết định; calibration chỉ phản ánh prior của sample | Luôn chạy đầu tiên |
| Logistic Regression | Tuyến tính trong log-odds; input numeric/encoded, output probability | Imputation, encoding và scaling khi cần | Nhanh, coefficient dễ kiểm tra, regularization rõ | Không tự học interaction/phi tuyến; giải thích tốt nếu feature ổn định; vẫn phải kiểm tra calibration; overfit khi nhiều feature/selection | Baseline chính và bài toán ưu tiên governance |
| Decision Tree | Rule split tuần tự; output class/probability theo leaf | Encoding tùy implementation; xử lý missing rõ ràng | Trực quan, học phi tuyến/interaction | Rất dễ overfit và không ổn định; leaf probability thường cần calibration | Học rule, baseline phi tuyến nhỏ |
| Random Forest | Bagging nhiều cây trên sample/feature khác nhau | Như cây; khóa schema/category | Robust hơn một cây, ít tuning hơn boosting | Model lớn, giải thích qua importance/SHAP không phải causal; probability có thể lệch; overfit khi leaf quá nhỏ | Challenger tabular mạnh, cần baseline ensemble |
| LightGBM/CatBoost | Boosting cây theo gradient; output raw score/probability | Quản lý categorical, missing và validation theo thư viện | Ranking mạnh, học interaction | Nhạy tuning/leakage; giải thích phức tạp; thường cần calibration; early stopping phải dùng validation | Challenger khi lợi ích vượt chi phí governance |
| WOE Logistic Scorecard | Binning → WOE → Logistic → points | Supervised binning fit trên train, special/missing bins | Reason code và auditability tốt | Mất chi tiết; binning dễ overfit; calibration phụ thuộc population | Chính sách cần scorecard minh bạch |
| Calibration | Ánh xạ score sang probability bằng Platt/isotonic hoặc phương pháp đã phê duyệt | Calibration split/cross-fitting độc lập | Cải thiện probability cho pricing/threshold | Có thể overfit, đặc biệt isotonic trên sample nhỏ; không sửa ranking | Khi probability quan trọng và curve cho thấy lệch |
| Ensemble | Kết hợp predictions của model bổ trợ | Đồng bộ fold, scale và calibration | Có thể tăng robustness/ranking | Tăng complexity, latency và governance; chỉ dùng khi uplift ổn định có bằng chứng | Sau khi từng model và lý do kết hợp đã rõ |



## Ví dụ trong credit scoring

Mọi challenger phải thắng baseline trên validation phù hợp và được so sánh về calibration, stability, explainability, latency.

## Điều cần kiểm tra trong project

- [ ] So sánh với Dummy và Logistic baseline.
- [ ] Tách train/validation/test trước feature selection và tuning.
- [ ] Đánh giá explainability, calibration, overfit và trường hợp sử dụng.

## Tài liệu liên quan

- [Tổng quan](modeling_overview.md)
- [Model selection](model_selection.md)
- [Calibration](calibration.md)
- [Validation](../evaluation/validation_strategy.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
