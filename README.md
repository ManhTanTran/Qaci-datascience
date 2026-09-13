# Credit Scoring Knowledge Base

Repository này hiện tập trung vào knowledge base tiếng Việt cho credit scoring: domain, dataset, feature, modeling, evaluation, monitoring và governance. Ngoài ra có FPT Credit Reasoning PoC research để kiểm thử raw → profile → rule → AI explanation trên dữ liệu synthetic. Không lưu dữ liệu khách hàng, PII hoặc kết quả thực nghiệm chưa được xác minh.

## Bắt đầu

Yêu cầu Python 3.10+.

```bash
python -m pip install -e ".[dev,modeling,notebook]"
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

## FPT Credit Reasoning PoC

Application dùng `credit_scoring.application.fpt_reasoning_poc` cho một file upload;
research dùng `credit_scoring.research.fpt_reasoning_poc` cho scenario, ablation và
repeated runs. `Synthetic_Customers` là source of truth; `Prompt_View` không tham gia
pipeline. Rule engine deterministic là source of truth cho `PASS`/`FAIL`/`UNKNOWN`,
AI chỉ giải thích và đánh dấu `rule_conflict`.

```powershell
python -m credit_scoring.research.fpt_reasoning_poc.pipeline
fpt-reasoning-ui
python -m pytest
mkdocs build --strict
```

Workbook synthetic đặt tại `data/raw/research/fpt_reasoning_poc/` và bị ignore; có
thể chuẩn bị từ archive bằng `python -m credit_scoring.research.fpt_reasoning_poc.prepare_data --zip <path>`.
LLM research chỉ đọc secret từ `OPENROUTER_API_KEY`, không ghi secret vào code,
notebook hay output.

## Tài liệu liên quan

- [Trang chủ knowledge base](docs/index.md)
- [Lộ trình học](docs/roadmap/learning_path.md)
- [Governance](docs/governance/model_approval_checklist.md)

## Trạng thái áp dụng trong project

FPT reasoning PoC đã có shared data pipeline và Streamlit UI cho research candidate;
target, schema, feature permission, đơn vị dữ liệu và production metric của FPT vẫn
chưa được xác nhận.
