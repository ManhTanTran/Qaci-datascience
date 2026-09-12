# Credit Scoring Knowledge Base

Repository này hiện tập trung vào knowledge base tiếng Việt cho credit scoring: domain, dataset, feature, modeling, evaluation, monitoring và governance. Không lưu dữ liệu khách hàng, PII hoặc kết quả thực nghiệm chưa được xác minh.

## Bắt đầu

Yêu cầu Python 3.10+.

```bash
python -m pip install -e ".[dev,modeling,notebook,reasoning]"
mkdocs serve
mkdocs build --strict
```

Mở trang chủ tại `docs/index.md`. Registry máy đọc nằm trong `catalogs/`.

## Quy trình đóng góp

- Dataset mới: cập nhật dataset registry và dataset card.
- Feature mới: cập nhật feature registry và tài liệu lineage/công thức.
- Experiment: cập nhật experiment log; không ghi metric không có artifact.
- Thay đổi validation hoặc metric: tạo decision record.
- Dùng `TODO(FPT): cần xác nhận với mentor hoặc data owner.` cho thông tin nội bộ chưa được xác nhận.

## Tài liệu liên quan

- [Trang chủ knowledge base](docs/index.md)
- [Lộ trình học](docs/roadmap/learning_path.md)
- [Governance](docs/governance/model_approval_checklist.md)
- [FPT Credit Reasoning PoC](docs/pipelines/fpt_credit_reasoning_poc.md)

## Hai luồng được tách riêng

- `src/credit_scoring/research/fpt_reasoning_poc/`: research/evaluation trên
  synthetic cases; không dùng cho request người dùng.
- `src/credit_scoring/application/`: boundary cho user-facing flow; không đọc
  research output.

Chạy research pipeline:

```powershell
python -m credit_scoring.research.fpt_reasoning_poc.pipeline
```

Kiểm tra application boundary:

```powershell
python -m pytest tests/test_application_boundary.py -q
```

## Trạng thái áp dụng trong project

Bộ khung tài liệu đã được tạo; target, schema, feature permission, validation và production metric của FPT chưa được xác nhận.
