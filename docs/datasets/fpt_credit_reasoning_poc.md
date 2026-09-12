# FPT Credit Reasoning PoC synthetic bundle

## Mục tiêu

Đây là bộ dữ liệu synthetic dùng để kiểm tra AI có giải thích đúng một kết quả
rule và nhận ra mâu thuẫn/dữ liệu thiếu hay không. Đây không phải dữ liệu xét
duyệt khoản vay thật và không có target default.

- Workbook: `FPT_credit_scoring_synthetic_10_cases.xlsx`
- Sheet chính: `Synthetic_Customers`
- Quy mô: 10 customer synthetic, 194 cột mỗi dòng
- Feature definitions: 166 feature thuộc 12 nhóm
- Fixture kiểm thử: `tests/fixtures/research/fpt_reasoning_poc/test_cases.jsonl`
- Bảng response: `outputs/research/fpt_reasoning_poc/experiment_results.csv`

## Khái niệm chính

Rule engine quyết định policy outcome; AI chỉ giải thích, phát hiện mâu thuẫn và
khai báo dữ liệu thiếu. `contextual_proxy` không phải quan sát cá nhân, còn
scenario synthetic không phải nhãn default.

## Đường dẫn local

Raw data, profile đã tính và rule result nằm trong các thư mục bị Git ignore:

```text
data/raw/research/fpt_reasoning_poc/
data/processed/research/fpt_reasoning_poc/
outputs/research/fpt_reasoning_poc/
```

Không commit raw workbook, profile, output hoặc dữ liệu có thể chứa thông tin
khách hàng.

## Semantics cần giữ

- `avg_monthly_income` và `avg_monthly_spend` là `contextual_proxy`, không phải
  thu nhập/chi tiêu cá nhân; đơn vị vẫn cần data owner xác nhận.
- `missing` khác `invalid` và khác giá trị 0.
- `age > 23` được đánh giá bởi rule engine; AI không được phá hard rule.
- Trả góp, tên sản phẩm cụ thể và giáo dục FPT chưa có trong source dataset;
  chỉ xuất hiện ở synthetic test nếu được ghi rõ.

## Ví dụ trong credit scoring

Case dưới ngưỡng tuổi nhưng có tín hiệu thanh toán tốt dùng để kiểm tra rằng AI
nhận ra mâu thuẫn nhưng vẫn giữ hard rule `age > 23`.

## Điều cần kiểm tra trong project

- [ ] Xác nhận đơn vị của `avg_monthly_income` và `avg_monthly_spend` với data owner.
- [ ] Xem xét 15 cảnh báo trong validation report trước khi mở rộng dữ liệu.
- [ ] Không đưa raw workbook, profile hoặc output local vào Git.
- [ ] Không đặt API key trong source, notebook, log hoặc prompt.

## Chạy PoC từ repo gốc

```powershell
python -m credit_scoring.research.fpt_reasoning_poc.pipeline
python -m pytest tests/test_fpt_reasoning_poc_rule_engine.py tests/test_fpt_reasoning_poc_experiment.py -q
```

CSV có một dòng cho mỗi case/repeat, gồm kết luận rule engine, response AI đã
tách trường, lý do, evidence, missing data và `response_json` nguyên bản để
đối chiếu suy luận/suy diễn.

Implementation nằm trong `src/credit_scoring/research/fpt_reasoning_poc/`; namespace
này chỉ dành cho research/evaluation và không được import vào application flow.

Research runner dùng OpenRouter:

```powershell
$env:OPENROUTER_API_KEY = "OPENROUTER_KEY_MOI"
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
```

## Tài liệu liên quan

- [Pipeline PoC](../pipelines/fpt_credit_reasoning_poc.md)
- [Alternative-data feature registry](../features/alternative_data_feature_registry.md)
- [Target definition](../domain/target_definition.md)

## Trạng thái áp dụng trong project

Đã đưa code và fixture vào repo gốc; local pipeline chạy được trên 10 hồ sơ
synthetic. Chưa có API run và chưa có feature/model nào được promote lên
production.
