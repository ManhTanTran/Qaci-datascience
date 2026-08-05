# Classification metrics

## Mục tiêu

Giải thích Accuracy, Precision, Recall, F1, ROC-AUC, PR-AUC, Log Loss và Brier Score.

## Khái niệm chính

Accuracy phụ thuộc threshold/base rate; Precision là tỷ lệ bad trong predicted bad; Recall là tỷ lệ bad được bắt; F1 cân bằng precision/recall. ROC-AUC đo ranking; PR-AUC nhạy với prevalence; Log Loss phạt xác suất tự tin sai; Brier là mean squared probability error.

> Không dùng test set để chọn feature, tune hyperparameter, chọn threshold hoặc chọn model. Các lựa chọn này phải hoàn tất bằng training/validation trước khi mở test.

## ROC-AUC được chấm như thế nào?

Với bài toán default, model xuất ra một **score** hoặc xác suất `p(default)` cho mỗi hồ sơ. ROC-AUC không bắt model phải chọn một ngưỡng duy nhất. Thay vào đó, nó hỏi: *nếu lấy ngẫu nhiên một khách hàng default và một khách hàng không default, model có xếp score của khách hàng default cao hơn không?*

- `AUC = 1.0`: mọi cặp good/bad được xếp đúng thứ tự.
- `AUC = 0.5`: thứ tự không tốt hơn đoán ngẫu nhiên.
- `AUC < 0.5`: thứ tự bị đảo; cần kiểm tra lại chiều của score/target hoặc model.

Một cách diễn giải tương đương là AUC bằng tỷ lệ cặp `(bad, good)` mà `score_bad > score_good`; một cặp bằng điểm đóng góp một nửa. Ví dụ, có hai bad có score `0.90`, `0.60` và hai good có score `0.40`, `0.20`. Cả bốn cặp bad-good đều được xếp đúng, nên AUC là `4 / 4 = 1.0`. Nếu một good có score `0.70`, chỉ ba trong bốn cặp đúng, nên AUC là `0.75`.

Về đồ thị, ROC curve lặp qua nhiều threshold và vẽ:

- **TPR/recall** = tỷ lệ bad được nhận diện ở threshold đó;
- **FPR** = tỷ lệ good bị gán nhầm là bad ở threshold đó.

ROC-AUC là diện tích dưới đường cong này. Vì nó đo thứ tự trên nhiều threshold, đừng đọc AUC như xác suất default, approval rate hoặc lợi nhuận.

## Diễn giải AUC trong validation và benchmark

Khi đánh giá một mô hình phân loại, dùng các số sau cho các mục đích khác nhau:

| Chỉ số | Cách tính | Dùng để làm gì |
|---|---|---|
| Fold AUC | AUC trên validation của một fold | Phát hiện fold bất thường |
| Mean ± std fold AUC | Trung bình/độ lệch chuẩn các fold | Ước lượng độ ổn định giữa folds |
| OOF AUC | AUC trên toàn bộ OOF predictions | So sánh các thử nghiệm trên cùng cross-validation setup |
| Test/benchmark AUC | AUC trên tập đánh giá độc lập | Đánh giá sau khi đã khóa lựa chọn model |

Một thay đổi chỉ đáng tin hơn baseline khi AUC tăng trên **cùng folds, cùng seed và cùng population**, đồng thời fold AUC không trở nên biến động rõ rệt. Chênh lệch rất nhỏ có thể chỉ là nhiễu của split; cần chạy lại hoặc dùng confidence interval trước khi kết luận.

## AUC không trả lời điều gì?

AUC không kiểm tra calibration. Hai model có AUC gần nhau có thể cho xác suất rất khác nhau; model dùng cho pricing, expected loss hoặc quyết định theo xác suất cần kiểm tra thêm calibration/Brier score. AUC cũng không chọn threshold; threshold phải được chọn từ chi phí, approval rate và ràng buộc nghiệp vụ trên validation phù hợp.

## Ví dụ trong credit scoring

Không chọn model chỉ bằng Accuracy trên dataset mất cân bằng. So sánh ROC-AUC trên validation phù hợp trước; sau đó báo PR curve và calibration nếu mục tiêu là ra quyết định credit thực tế.

## Điều cần kiểm tra trong project

- [ ] Gắn metric với population, split và confidence interval.
- [ ] Khóa test set cho đánh giá cuối.
- [ ] Báo discrimination, calibration và business impact cùng nhau.

## Tài liệu liên quan

- [Credit risk metrics](credit_risk_metrics.md)
- [Validation](validation_strategy.md)
- [Threshold](threshold_selection.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
