# AGENTS.md

## Phạm vi

Các quy tắc này áp dụng cho toàn repository.

## Đồng bộ code, registry và tài liệu

- Khi thêm dataset, phải cập nhật `catalogs/dataset_registry.yaml` và dataset card tương ứng.
- Khi thêm feature, phải cập nhật `catalogs/feature_registry.yaml`. Feature có
  thể đăng ký theo family nếu `documentation_path` liệt kê đầy đủ từng feature,
  source column, formula và missing policy.
- Khi chạy experiment, phải cập nhật `docs/experiments/experiment_log.md`.
- Khi thay đổi metric hoặc validation, phải tạo decision record trong `docs/decisions/`.
- Khi code thay đổi làm tài liệu không còn đúng, phải cập nhật docs trong cùng thay đổi.

## Ranh giới source và notebook

**Hàm dùng lại được thì nằm trong `src/credit_scoring/`, và phải có test.** Tiêu
chí là tính tái sử dụng, không phải dataset. Một hàm gắn cứng với Home Credit vẫn
thuộc source nếu nhiều notebook hoặc nhiều experiment gọi nó. Không được để logic
dùng lại chỉ tồn tại trong notebook, vì code trong notebook không được pytest bảo
vệ và không tái lập được giữa các lượt chạy.

Notebook giữ phần dùng một lần: đọc dữ liệu, EDA, chọn cấu hình experiment, đọc
kết quả và diễn giải. Khi một đoạn trong notebook được copy sang notebook thứ
hai, đó là dấu hiệu nó phải chuyển vào source.

Notebook gọi source; source không được import hay giả định gì về notebook.

Code trong notebook vẫn phải viết thành hàm, kèm một cell synthetic assertion
dùng fixture nhỏ tự dựng, chạy **trước** khi đọc dữ liệu thật và chạy trong mọi
lượt. Không được comment out.

## Yêu cầu với feature code trong source

- **Schema là hàm của code, không phải của dữ liệu.** Danh sách cột đầu ra phải
  giống nhau khi chạy trên mẫu nhỏ và trên full data. Không lấy category từ dữ
  liệu, không lọc cột theo tần suất, không dựng danh sách aggregate bằng cách
  duyệt xem cột nào đang là numeric. Phải có test so schema giữa hai tập con.
- **Missing khác zero.** Tổng amount dùng `sum(min_count=1)` để nhóm không quan
  sát được giá trị nào giữ `NaN`. Chỉ count được fill 0, vì "không có bản ghi
  nào" là sự thật chứ không phải thiếu dữ liệu.
- **Kiểm cardinality sau mỗi bước ghép bảng hoặc aggregate.** Ghép one-to-one
  phải kiểm số dòng không đổi; kết quả ở grain khách hàng phải kiểm khóa duy nhất.
- **Nhãn family khai cùng chỗ với giá trị.** Mỗi feature mang một family
  (`counts`, `amounts`, `recency`, `delinquency`) sinh ra từ cùng khai báo tạo ra
  giá trị, để nhãn không trôi khỏi dữ liệu.
- **Tên feature không chứa ký tự LightGBM từ chối:** `" \ [ ] { } : ,`

## Lưu dữ liệu trung gian

**Feature đã tính lưu thành Parquet, không phải CSV.** Parquet giữ nguyên dtype
và `NaN`, nhỏ hơn khoảng ba lần và đọc nhanh hơn khoảng hai mươi lần; CSV làm mất
dtype nên `category` phải cast lại tay mỗi lần và `int32` phình thành `int64`.

Dùng `credit_scoring.feature_store`: mỗi block là một Parquet kèm manifest ghi
key column, thứ tự cột, family từng feature và `builder_version`.

- **Đổi `builder_version` mỗi khi sửa công thức feature.** Cache cũ trả về số của
  công thức cũ mà không báo lỗi gì; đây là kiểu sai nguy hiểm nhất vì không có
  dấu hiệu nào. Luôn truyền `expected_builder_version` khi load.
- **Chia block theo bảng nguồn, nhóm ngữ nghĩa là nhãn trong manifest.** Một
  feature thuộc một bảng nhưng một nhóm ngữ nghĩa có thể trải nhiều bảng.
- **Khai `dtype` ngay trong `read_csv`**, không đọc xong rồi mới downcast: đỉnh
  bộ nhớ nằm ở lúc đọc. Cột chuỗi ít giá trị khai `category`.
- Dữ liệu và block nằm ngoài git; không commit.

## Research candidate và production

Feature mới là **research candidate**, kể cả khi đã nằm trong source có test.
Muốn promote lên production thì phải được review riêng và áp đủ yêu cầu về
source, formula và owner. Không mô tả research candidate là feature production.

Không thêm feature vào một experiment đang khóa pre-registration; mở experiment
mới với pre-registration riêng.

## Tính trung thực và an toàn

- Không tạo metric, biểu đồ, kết quả hoặc kết luận giả.
- Không commit dữ liệu khách hàng; không ghi PII hoặc dữ liệu tín dụng thật vào prompt, log hay docs.
- Không dùng feature sau thời điểm quyết định cho vay hoặc thuộc tính nhạy cảm khi chưa được phê duyệt.
- Không tự ý thay đổi target, production metric hoặc validation strategy.
- Mọi feature production cần source, formula, owner và implementation có test
  trong source; mọi model production cần model card. Feature còn nằm trong
  notebook là research candidate và không được mô tả là production.
- Dùng chính xác marker `TODO(FPT): cần xác nhận với mentor hoặc data owner.` khi thông tin nội bộ chưa được xác nhận.

## Kiểm tra trước khi bàn giao

Chạy `ruff check .`, `pytest` và `mkdocs build --strict`; kiểm tra internal links và bảo đảm không có dữ liệu nhạy cảm.
