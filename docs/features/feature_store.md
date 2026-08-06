# Feature store

## Mục tiêu

Mô tả cách lưu và đọc lại feature đã tính bằng `credit_scoring.feature_store`,
để một lần tính dùng được nhiều lần và nhóm feature không bị trôi khỏi dữ liệu.

## Khái niệm chính

Một **block** là một ma trận feature ở một grain, lưu thành một file Parquet kèm
một manifest JSON. Manifest ghi key column, thứ tự cột, family của từng feature
và `builder_version` của code đã sinh ra chúng.

```python
from credit_scoring.feature_store import load_block, merge_blocks, save_block

save_block(frame, "bureau", root=STORE,
           builder_version=BUILDER_VERSION, families=families)

block = load_block("bureau", root=STORE,
                   expected_builder_version=BUILDER_VERSION)

merge_blocks(application, blocks)                                # tất cả
merge_blocks(application, blocks, families={"bureau": "recency"})  # một nhóm
```

### Vì sao Parquet, không phải CSV

Đo trên block `bureau` thật, 305.811 dòng và 61 feature:

| | CSV | Parquet |
|---|---|---|
| Kích thước | 83,2 MB | 27,5 MB |
| Đọc | 5,84s | 0,31s |
| Ghi | 28,70s | gần như tức thì |
| Kiểu dữ liệu | Mất, pandas đoán lại | Ghi trong file |

Chỗ mất kiểu mới là vấn đề dài hạn: qua CSV một vòng, `int32` thành `int64` và
`category` thành `object`, nên `categorical_features` của LightGBM phải cast lại
tay mỗi lần. `NaN` thì cả hai định dạng đều giữ đúng.

### Block chia theo bảng nguồn, family là nhãn

Một feature thuộc đúng một bảng nguồn, nhưng một nhóm ngữ nghĩa có thể trải
nhiều bảng: `recency` xuất hiện ở cả `bureau` lẫn `installments`. Nếu chia file
theo nhóm ngữ nghĩa thì mỗi lần thêm bảng phải sửa lại mọi file nhóm. Chia theo
bảng và để nhóm làm nhãn thì thêm bảng chỉ là thêm một block, và vẫn cắt được
theo nhóm xuyên bảng.

Family được khai cùng chỗ với giá trị, trong `Aggregation`, nên nhãn không thể
lệch khỏi cột nó mô tả.

### `builder_version`

Feature code đổi thường xuyên hơn dữ liệu thô. Một cache trả về giá trị của công
thức cũ không làm gì hỏng theo cách nhìn thấy được: không exception, không cảnh
báo, chỉ là những con số sai. `load_block` từ chối block có version khác
`expected_builder_version`, nên sửa công thức mà quên build lại sẽ dừng ngay.

Bốn chốt kiểm tra khi load: version khớp, tập và thứ tự cột khớp manifest, số
dòng khớp, khóa duy nhất.

## Ví dụ trong credit scoring

Build năm block từ CSV thô mất 1.098 giây; đọc lại cả năm từ Parquet mất 0,70
giây — **nhanh hơn khoảng 1.560 lần**. Nếu lưu chính năm block đó bằng CSV thì
đọc mất 9,30 giây và chiếm 355,0 MB, tức Parquet nhanh hơn 13 lần và nhỏ hơn 3,3
lần trên cùng dữ liệu.

Khi thử một cấu hình model khác, chi phí feature engineering gần như bằng không.

## Điều cần kiểm tra trong project

- [x] Round-trip giữ nguyên giá trị, dtype và `NaN`, có test bảo vệ.
- [x] Load phát hiện version cũ, cột lệch, số dòng lệch và khóa trùng.
- [x] Nhãn family cho cột không tồn tại bị từ chối ngay lúc ghi.
- [x] `merge_blocks` từ chối tên cột trùng thay vì thêm hậu tố `_x`/`_y`.
- [ ] Truyền `expected_builder_version` ở mọi chỗ gọi `load_block`.
- [ ] Block và dữ liệu không được commit vào git.

## Tài liệu liên quan

- [Home Credit auxiliary features](home_credit_auxiliary_features.md)
- [Feature engineering](feature_engineering.md)
- [ADR-0004](../decisions/0004-auxiliary-feature-modules-in-source.md)

## Trạng thái áp dụng trong project

Đang dùng cho năm block Home Credit. Block lưu ngoài git tại thư mục do tham số
`root` quyết định; đường dẫn không hardcode trong source. Chưa dùng cho dataset
khác và chưa áp cho feature production.
