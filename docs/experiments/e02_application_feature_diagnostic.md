# E02 application feature diagnostic

## Mục tiêu

Ghi lại lượt chạy E01/E02 application-level đã thực hiện, gồm diagnostic local,
full Kaggle artifact, metric đo được và giới hạn xác minh.

## Khái niệm chính

### Phạm vi và trạng thái

Ngày chạy: 2026-08-03.

Đây là lượt chạy diagnostic trên toàn bộ 307.511 hàng
`application_train.csv`, không phải E02 completed. Workspace không có
`application_test.csv`; một DataFrame test rỗng có cùng schema train được dùng
chỉ để thực thi contract alignment. Vì vậy kết quả dưới đây xác minh OOF và
logic feature trên train, nhưng chưa xác minh category vocabulary hay schema
với test competition thật.

Không có bảng auxiliary, tuning, leaderboard selection hoặc target-derived
feature trong lượt chạy.

## Cấu hình khóa

- target: `TARGET`;
- metric: ROC-AUC;
- validation: 5-fold `StratifiedKFold`, shuffle, seed 42;
- early stopping: 200;
- LightGBM: learning rate 0,02; tối đa 5.000 trees; 31 leaves;
  `min_child_samples=80`; subsample 0,8; column sample 0,7; L1 0,1; L2 5;
- fold fingerprint:
  `9ad19c60ff41667bfc7e44a597cf8aa9a9b35caac2ad2cc14bd04d25a4684bdc`;
- train archive SHA-256:
  `64289b17dd316a4106a2e3fe8d37f17ca6e16729e45989e86944049b7fb9050f`;
- environment: Python 3.10.11, LightGBM 4.7.0, NumPy 2.2.6,
  pandas 2.3.3, scikit-learn 1.7.2.

File local mang tên `application_train.csv` thực tế là ZIP chứa CSV. Dữ liệu
raw được giữ trong thư mục git-ignored và không được thêm vào repository.

## Ví dụ trong credit scoring

### Kết quả đã đo

| Chỉ số | E01 diagnostic | E02 diagnostic | Delta E02 - E01 |
|---|---:|---:|---:|
| Số model features | 149 | 167 | +18 |
| Fold 1 AUC | 0.765182 | 0.765449 | +0.000267 |
| Fold 2 AUC | 0.775031 | 0.774970 | -0.000061 |
| Fold 3 AUC | 0.766180 | 0.766205 | +0.000025 |
| Fold 4 AUC | 0.771822 | 0.772393 | +0.000571 |
| Fold 5 AUC | 0.765474 | 0.766564 | +0.001090 |
| Mean fold AUC | 0.768738 | 0.769116 | +0.000379 |
| Fold AUC standard deviation | 0.004443 | 0.004285 | -0.000158 |
| Global OOF AUC | 0.768683 | 0.769071 | +0.000388 |
| LightGBM CV runtime | 309.63 s | 273.57 s | -36.06 s |
| Peak process RSS | Không đo | 1.289,35 MB | Không áp dụng |

Locked E01 reference là OOF AUC `0.768696`. E01 diagnostic thấp hơn reference
`0.000013`, có thể do thiếu test category vocabulary và khác phiên bản môi
trường. Không thay thế locked reference bằng diagnostic này.

E02 tăng ở 4/5 folds nhưng delta nhỏ; chưa đủ bằng chứng để gọi là cải thiện ổn
định. Full family ablation chưa chạy. Do đó chưa có căn cứ loại riêng ratios,
age/employment, external summaries, contact/document hay housing summaries.

### Kaggle follow-up

Người dùng đã cung cấp ảnh kết quả submission E02 ngày 2026-08-03. Kaggle hiển
thị trạng thái complete after deadline với private score `0.76330` và public
score `0.76708`.

| Leaderboard | E01 | E02 | Delta E02 - E01 |
|---|---:|---:|---:|
| Private / `Score` | 0.76312 | 0.76330 | +0.00018 |
| Public | 0.76634 | 0.76708 | +0.00074 |

Hai score đều tăng, nhưng leaderboard không được dùng để chọn feature family.

### Full Kaggle artifact follow-up

Người dùng sau đó cung cấp full output của run commit
`325338994c7b00a5114919fc21b101b885df16ac`. Artifact ghi Python 3.12.13,
LightGBM 4.6.0, pandas 2.3.3, NumPy 2.0.2 và scikit-learn 1.6.1. Kết quả được
tính lại trực tiếp từ `oof_predictions.csv` và khớp `run_metadata.json`:

| Chỉ số | E02 Kaggle run |
|---|---:|
| Số train / test | 307.511 / 48.744 |
| Số model features | 167 |
| Fold 1 AUC | 0.765248 |
| Fold 2 AUC | 0.774970 |
| Fold 3 AUC | 0.766205 |
| Fold 4 AUC | 0.772393 |
| Fold 5 AUC | 0.766564 |
| Mean fold AUC | 0.769076 |
| Fold AUC standard deviation | 0.004328 |
| Global OOF AUC | 0.769030 |
| Delta OOF so với locked E01 | +0.000334 |
| Runtime | 420,35 s |

OOF không thiếu hoặc trùng ID, mọi `VALIDATION_COUNT` bằng 1 và prediction hữu
hạn. `submission.csv` có 48.744 ID/prediction khớp chính xác
`test_predictions.csv`. Full artifact không lưu fold assignment theo từng ID,
vì vậy chưa thể làm paired E01/E02 comparison chỉ từ hai artifact đã có.

### 18 feature được thêm

- ratios/amount: `CREDIT_ANNUITY_RATIO`, `CREDIT_GOODS_DIFF`;
- age/employment: `AGE_YEARS`, `EMPLOYED_YEARS`, `EMPLOYED_AGE_RATIO`;
- external source: `EXT_SOURCE_COUNT`;
- application/contact: `DOCUMENT_COUNT`, `CONTACT_COUNT`,
  `PHONE_CHANGE_YEARS`;
- housing: mean/min/max cho từng suffix `AVG`, `MODE`, `MEDI` trên các base
  numeric có mapping đủ và rõ ràng (9 cột).

Các feature yêu cầu còn lại đã có trong E01 và được E02 giữ cùng tên, không tạo
cột trùng.

## Điều cần kiểm tra trong project

1. [x] Kiểm tra `run_metadata.json`, fold scores, OOF và submission của Kaggle
   E02 run.
2. Xác minh E01/E02 dùng cùng fold assignment và E01 tái lập locked reference.
3. Chạy notebook E02 family ablation trên cùng folds; chỉ giữ family có delta
   ổn định.
4. Khi các điều kiện trên đạt, cập nhật E02 thành fully verified; không
   dùng leaderboard để chọn family.

## Tài liệu liên quan

- [Experiment log](experiment_log.md)
- [Home Credit application features](../features/home_credit_application_features.md)
- [Home Credit validation](../evaluation/home_credit_validation.md)
- [Home Credit LightGBM runner](../modeling/home_credit_lightgbm.md)

## Trạng thái áp dụng trong project

E02 full run, OOF/test artifact và submission đã được xác minh. Mức tăng OOF so
với locked E01 là dương nhưng nhỏ. Experiment chưa có paired OOF evidence và
chưa chạy feature-family ablation.
