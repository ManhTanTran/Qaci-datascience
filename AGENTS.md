# AGENTS.md

## Phạm vi

Các quy tắc này áp dụng cho toàn repository.

## Đồng bộ code, registry và tài liệu

- Khi thêm dataset, phải cập nhật `catalogs/dataset_registry.yaml` và dataset card tương ứng.
- Khi thêm feature, phải cập nhật `catalogs/feature_registry.yaml`.
- Khi chạy experiment, phải cập nhật `docs/experiments/experiment_log.md`.
- Khi thay đổi metric hoặc validation, phải tạo decision record trong `docs/decisions/`.
- Khi code thay đổi làm tài liệu không còn đúng, phải cập nhật docs trong cùng thay đổi.
- Không copy logic quan trọng chỉ vào notebook; logic tái sử dụng phải nằm trong source module và có test.

## Tính trung thực và an toàn

- Không tạo metric, biểu đồ, kết quả hoặc kết luận giả.
- Không commit dữ liệu khách hàng; không ghi PII hoặc dữ liệu tín dụng thật vào prompt, log hay docs.
- Không dùng feature sau thời điểm quyết định cho vay hoặc thuộc tính nhạy cảm khi chưa được phê duyệt.
- Không tự ý thay đổi target, production metric hoặc validation strategy.
- Mọi feature production cần source, formula, owner; mọi model production cần model card.
- Dùng chính xác marker `TODO(FPT): cần xác nhận với mentor hoặc data owner.` khi thông tin nội bộ chưa được xác nhận.

## Kiểm tra trước khi bàn giao

Chạy `ruff check .`, `pytest` và `mkdocs build --strict`; kiểm tra internal links và bảo đảm không có dữ liệu nhạy cảm.
