# E02-D robustness pre-registration

## Mục tiêu

Khóa trước quy tắc quyết định cho robustness check của một feature ứng viên duy
nhất, `CREDIT_GOODS_DIFF`, và chốt `E03-BASE` trước khi bắt đầu E03 bureau.

Tài liệu này được viết và commit **trước khi chạy**. Nó không chứa kết quả. Mọi
số đo sẽ được ghi trong experiment log và report sau khi có artifact.

## Khái niệm chính

### Vì sao cần bước này

E02 đã chạy factorial ablation trên 18 feature application-level. Mọi delta đo
được đều nhỏ hơn `+0.0006` OOF AUC, trong khi độ lệch chuẩn giữa fold là
`0.0043`. Không có cấu hình nào tách được khỏi nhiễu.

Rà soát `src/credit_scoring/features/home_credit_application.py` cho thấy phần
lớn 18 feature là mã hóa lại feature đã có trong E01: biến đổi đơn điệu, trùng
công thức, hoặc bù tuyến tính.

Cần phát biểu chính xác điều này. Một cột dư thừa **vẫn làm đổi kết quả**: nó
đổi biên bin của histogram, đổi tập cột được lấy mẫu tại mỗi node khi
`feature_fraction` nhỏ hơn 1, và đổi cạnh tranh giữa các split. Cái nó không
làm là **thêm thông tin**. Vì vậy các delta nhỏ đã đo nên hiểu là hệ quả phụ
của việc thêm cột, không phải bằng chứng của tín hiệu mới.

### Phân loại ứng viên

| | `CREDIT_ANNUITY_RATIO` | `CREDIT_GOODS_DIFF` |
|---|---|---|
| Công thức | `AMT_CREDIT / AMT_ANNUITY` | `AMT_CREDIT - AMT_GOODS_PRICE` |
| Quan hệ với E01 | Nghịch đảo của `ANNUITY_CREDIT_RATIO` | Hiệu của hai cột đã có trong matrix |
| Thông tin mới | Không | Không |
| Representation mới | Không. Cả hai mẫu số đều dương nên đây là biến đổi đơn điệu một biến; thứ tự quan sát không đổi, không mở ra ranh giới nào mà split theo trục chưa đạt được | Có. Ranh giới `AMT_CREDIT - AMT_GOODS_PRICE = c` là một đường chéo trong không gian hai cột gốc; tree chỉ xấp xỉ được bằng nhiều split bậc thang, cấp thẳng cột thì một split là đủ |
| Quyết định | Loại | Ứng viên, phải qua robustness check |

`CREDIT_ANNUITY_RATIO` đo được `+0.00024` trong factorial. Mức tăng đó bị loại
trên cơ sở cấu trúc, và cơ chế của nó không được điều tra.

### Vì sao loại nhóm recompute

Nhóm feature tính lại các ratio E01 bằng `safe_divide` và float32 ghi đè bốn
cột E01. Bốn đối chiếu độc lập trong factorial đều cho khác biệt xấp xỉ không.
Ngoài lý do đó, `_legacy_safe_divide` tồn tại riêng để giữ nguyên công thức và
dtype của E01 cho việc replay locked baseline; ghi đè các cột đó làm hỏng khả
năng tái lập reference `0.768696`. Nhóm này bị loại độc lập với kết quả AUC.

### Protocol

Hai cấu hình, khác nhau đúng một cột:

```text
E01  = locked E01 feature matrix
D    = E01 + CREDIT_GOODS_DIFF
```

`CREDIT_GOODS_DIFF` được tính bằng đúng biểu thức của module, gồm cả ép float32
và đổi giá trị vô hạn thành `NaN`, để khớp bit-for-bit với cột đã dùng trong
factorial.

Ba validation seed: `42`, `52`, `62`. Trong mỗi seed:

- 5-fold `StratifiedKFold`, shuffle;
- E01 và D dùng **cùng một fold list**, xác nhận bằng `fold_fingerprint` trùng nhau;
- model random seed cố định `42`;
- LightGBM parameters giữ nguyên cấu hình đã khóa từ E01;
- không tuning, không đổi model, không dùng leaderboard.

Seed `42` được chạy lại trong cùng session với `52` và `62`. Artifact seed `42`
hiện có được tạo ở môi trường khác, và thay đổi phiên bản LightGBM có thể đổi
cách chia bin.

Feature matrix được dựng một lần và dùng lại cho cả ba seed; chỉ fold thay đổi.

### Quy tắc quyết định

`CREDIT_GOODS_DIFF` chỉ được đưa vào baseline nếu đạt **đồng thời** cả bốn:

1. Delta OOF dương ở ít nhất 2 trong 3 seed.
2. Ít nhất 10 trong 15 fold delta dương.
3. Mean delta qua ba seed dương.
4. Trimmed mean của 15 fold delta dương, sau khi bỏ một giá trị lớn nhất và một
   giá trị nhỏ nhất.

Tiêu chí 4 mã hóa yêu cầu "không một fold nào tạo phần lớn mức tăng": bỏ fold
tốt nhất đi mà kết quả vẫn dương. Cắt đối xứng nên không thiên lệch.

Bootstrap chỉ dùng để mô tả độ bất định. Nó không được đổi quy tắc sau khi thấy
kết quả.

Nếu ứng viên hoàn toàn không có tác dụng, xác suất nó vẫn qua tiêu chí 2 thuần
do ngẫu nhiên là khoảng 15 phần trăm, và thực tế cao hơn vì các fold không độc
lập với nhau. Quy tắc này thiên về giữ ứng viên. Điều đó được chấp nhận cho một
feature đã đăng ký trước và có chi phí tính toán bằng không, nhưng kết quả đạt
quy tắc không được mô tả là đã chứng minh ưu thế.

### Kết luận theo nhánh

```text
Đạt quy tắc   ->  E03-BASE = E01 + CREDIT_GOODS_DIFF
Không đạt     ->  E03-BASE = E01
```

`CREDIT_ANNUITY_RATIO` không sang E03 trong cả hai nhánh.

## Ví dụ trong credit scoring

Một feature ratio mới thường được giữ lại vì nó "có vẻ hợp lý về nghiệp vụ" và
vì lượt chạy đầu tiên cho AUC cao hơn. Với biên độ nhỏ hơn nhiễu giữa fold,
lượt chạy đầu tiên không phân biệt được với may rủi.

Ở đây, ngưỡng và quy tắc được cố định và commit trước khi có số. Nếu ứng viên
không đạt, baseline quay về E01 và feature bị loại, kể cả khi delta trung bình
dương. Điều đó ngăn việc nới tiêu chí sau khi nhìn thấy kết quả.

## Điều cần kiểm tra trong project

- [ ] Commit tài liệu này trước khi chạy cell đầu tiên; ghi commit SHA vào
      `run_metadata.json` của cả ba seed.
- [ ] `fold_fingerprint` của E01 bằng của D trong cùng seed, và khác nhau giữa
      ba seed.
- [ ] Mọi `VALIDATION_COUNT` bằng 1; OOF không thiếu hoặc trùng `SK_ID_CURR`.
- [ ] `| OOF AUC của E01 seed 42 - 0.768696 | <= 0.0005`; vượt ngưỡng thì dừng
      và điều tra, không chạy tiếp.
- [ ] Áp bốn tiêu chí đúng như đã commit, không diễn giải lại.
- [ ] Ghi kết quả vào experiment log với số lấy từ artifact, không làm tròn mô
      tả.

## Tài liệu liên quan

- [Experiment log](experiment_log.md)
- [E02 application feature diagnostic](e02_application_feature_diagnostic.md)
- [Home Credit application features](../features/home_credit_application_features.md)
- [Home Credit validation](../evaluation/home_credit_validation.md)
- [Home Credit LightGBM runner](../modeling/home_credit_lightgbm.md)

## Trạng thái áp dụng trong project

Completed. Kết quả được ghi tại
[E02-D robustness result](e02_d_robustness_result.md). Ứng viên chỉ đạt `9/15`
fold delta dương so với ngưỡng bắt buộc `10/15`, nên gate fail và
`E03-BASE = E01`.
