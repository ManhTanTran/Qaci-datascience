# E02-D robustness result

## Mục tiêu

Ghi lại kết quả robustness check đã đăng ký trước cho `CREDIT_GOODS_DIFF` và
khóa baseline dùng để bắt đầu E03.

## Kết luận

`CREDIT_GOODS_DIFF` **không vượt qua** robustness gate đã đăng ký trước. Có
`9/15` fold có delta AUC dương, thấp hơn điều kiện bắt buộc `10/15`. Vì bốn
tiêu chí phải đạt đồng thời, quyết định cuối cùng là:

```text
E03-BASE = E01
```

Kết quả này không chứng minh feature có hại. Nó cho thấy bằng chứng hiện tại
không đủ ổn định để promote feature vào baseline đã khóa.

## Khái niệm chính

Decision rule là một AND gate gồm bốn điều kiện. Feature chỉ được promote khi
đạt cả bốn; vì vậy một điều kiện fail là đủ để chốt nhánh không promote. Fold
delta là so sánh paired giữa D và E01 trên cùng validation split.

## Lineage

- Pre-registration và notebook được commit trước khi có kết quả tại
  `9d58b210d11eea239bf6203c0ee159f4bf7bdfa1`.
- Notebook: `notebooks/02_home_credit_application/06_home_credit_e02_d_robustness.ipynb`.
- Hai cấu hình: locked E01 và E01 + `CREDIT_GOODS_DIFF`.
- Validation seed: `42`, `52`, `62`; mỗi seed có 5 fold paired.
- Nguồn số liệu trong biên bản này: bảng fold metrics do người chạy Kaggle
  cung cấp ngày 2026-08-05, hiển thị đến 6 chữ số thập phân.
- Leaderboard không được dùng để đưa ra quyết định.

Biên bản không tự điền global OOF delta theo seed hoặc đường dẫn Kaggle artifact
vì các trường đó chưa được cung cấp trong workspace. Việc thiếu các trường này
không làm thay đổi quyết định: tiêu chí `10/15` đã fail và gate là phép AND.

## Fold metrics được cung cấp

| Seed | Fold | AUC E01 | AUC D | Delta AUC |
|---:|---:|---:|---:|---:|
| 42 | 1 | 0.765256 | 0.764782 | -0.000474 |
| 42 | 2 | 0.775031 | 0.774979 | -0.000052 |
| 42 | 3 | 0.766180 | 0.765695 | -0.000485 |
| 42 | 4 | 0.771822 | 0.772778 | +0.000956 |
| 42 | 5 | 0.765474 | 0.765968 | +0.000494 |
| 52 | 1 | 0.768212 | 0.768499 | +0.000287 |
| 52 | 2 | 0.768117 | 0.768036 | -0.000080 |
| 52 | 3 | 0.764302 | 0.764444 | +0.000142 |
| 52 | 4 | 0.767087 | 0.767240 | +0.000153 |
| 52 | 5 | 0.774896 | 0.775840 | +0.000944 |
| 62 | 1 | 0.772285 | 0.773016 | +0.000731 |
| 62 | 2 | 0.766306 | 0.766939 | +0.000632 |
| 62 | 3 | 0.774442 | 0.775180 | +0.000738 |
| 62 | 4 | 0.765290 | 0.764714 | -0.000576 |
| 62 | 5 | 0.764453 | 0.763952 | -0.000501 |

## Áp dụng decision rule

| Tiêu chí đã đăng ký | Kết quả có thể xác minh | Trạng thái |
|---|---:|---|
| Delta global OOF dương ở ít nhất 2/3 seed | Chưa có seed summary trong workspace | Không cần để chốt sau khi một điều kiện bắt buộc đã fail |
| Ít nhất 10/15 fold delta dương | `9/15` | **Fail** |
| Mean global OOF delta qua ba seed dương | Chưa có seed summary trong workspace | Không cần để chốt sau khi một điều kiện bắt buộc đã fail |
| Symmetric trimmed mean của 15 fold delta dương | Khoảng `+0.000195`, tính từ số hiển thị | Pass mô tả; không đảo quyết định |

Các thống kê mô tả tính từ delta đã hiển thị:

- Seed 42: `2/5` fold dương; mean fold delta khoảng `+0.000088`.
- Seed 52: `4/5` fold dương; mean fold delta khoảng `+0.000289`.
- Seed 62: `3/5` fold dương; mean fold delta khoảng `+0.000205`.
- Mean của 15 fold delta khoảng `+0.000194`.

Mean fold delta không được dùng thay cho global OOF delta, vì AUC không phân rã
thành trung bình AUC của các fold.

## Ví dụ trong credit scoring

Một feature có mean fold delta dương vẫn có thể không đủ ổn định để trở thành
baseline. Trường hợp này có mean mô tả hơi dương nhưng chỉ 9 fold cải thiện;
quy tắc đã khóa yêu cầu tối thiểu 10 fold nên feature không được promote.

## Quyết định chuyển phase

- Không promote `CREDIT_GOODS_DIFF`.
- Không đưa `CREDIT_ANNUITY_RATIO` sang E03 theo quyết định cấu trúc đã đăng ký.
- Khóa `E03-BASE` bằng E01 application-only.
- Giữ nguyên ngưỡng `10/15`; không nới thành `9/15` sau khi nhìn kết quả.

## Điều cần kiểm tra trong project

- [x] Pre-registration và code đã được commit trước lượt chạy.
- [x] Áp dụng nguyên ngưỡng `10/15` đã đăng ký.
- [x] Không dùng leaderboard để chọn feature.
- [x] Cập nhật experiment log và feature registry.
- [ ] Lưu `decision.json`, seed summary và đường dẫn Kaggle run nếu người chạy
      cung cấp artifact đầy đủ sau này.

## Trạng thái áp dụng trong project

Completed from user-supplied fold metrics. Robustness gate fail và
`E03-BASE = E01`. Global seed summary chưa có trong workspace và không được suy
diễn từ mean fold AUC.

## Tài liệu liên quan

- [E02-D robustness pre-registration](e02_d_robustness_preregistration.md)
- [Experiment log](experiment_log.md)
- [E02 application feature diagnostic](e02_application_feature_diagnostic.md)
