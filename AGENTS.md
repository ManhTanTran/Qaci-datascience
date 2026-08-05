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

Source `src/credit_scoring/` chỉ chứa code dùng chung giữa nhiều dataset: model
factory, cross-validation, metric, tuning, artifact writer, reproducibility và
numeric helper. Mọi thứ ở đây phải có test. Không được để logic generic chỉ nằm
trong notebook.

Notebook chứa mọi thứ gắn với một dataset cụ thể: đọc dữ liệu, làm sạch, feature
engineering, ghép bảng và aggregation. Lý do là schema, grain và quan hệ giữa các
bảng khác nhau ở từng dataset, nên trừu tượng hóa sớm sinh ra abstraction sai.

Notebook gọi source; source không được import hay giả định gì về notebook.

Vì feature logic của dataset không được pytest bảo vệ, notebook phải bù lại:

- Viết feature engineering thành hàm, không phải code thủ tục rải rác, để phần
  kiểm tra chạy đúng đoạn code mà lượt chạy thật dùng.
- Có một cell synthetic assertion dùng fixture nhỏ tự dựng, chạy **trước** khi
  đọc dữ liệu thật và chạy trong mọi lượt. Không được comment out.
- Kiểm cardinality và số dòng sau mỗi bước ghép bảng hoặc aggregate.

Các module dataset-specific đã tồn tại trong `src/credit_scoring/features/` và
`src/credit_scoring/experiments/` được giữ nguyên và tiếp tục dùng vì chúng là
nền của baseline đã khóa. Không thêm module dataset-specific mới cho công việc
research; ngoại lệ duy nhất là promote feature lên production, xem mục dưới.

Feature xây trong notebook là **research candidate**, không phải feature
production. Muốn promote lên production thì phải chuyển sang implementation nằm
trong source, có test và được review riêng; lúc đó mới áp các yêu cầu về source,
formula và owner.

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
