# Alternative-data Agent Harness

## Mục tiêu

Mô tả harness provider-neutral cho online LLM reasoning: chuẩn hóa feature,
phát hiện domain, retrieve rule, tạo prompt và kiểm tra structured output.

## Khái niệm chính

Harness không tự sinh rule từ khách hàng mới. Rule được load từ Knowledge Base;
feature definition được load từ registry. LLM chỉ nhận payload đã lọc và output
phải tham chiếu feature/rule tồn tại.

## Luồng xử lý

```text
customer features
  → normalization
  → domain detection
  → metadata rule retrieval
  → prompt payload
  → provider adapter (optional)
  → strict output validation
```

Implementation hiện tại nằm trong `src/credit_scoring/reasoning/`:

- `feature_registry.py`: loader và missing normalization;
- `retriever.py`: domain detector và deterministic metadata retrieval;
- `prompt_builder.py`: payload/prompt builder;
- `harness.py`: provider-neutral orchestration.
- `llm_client.py`: OpenAI Responses và OpenRouter structured-output adapters.
- `workspace.py`: application service cho catalog, customer assessment,
  prompt comparison, counter-argument và audit `simulate.zip`.

Customer web tại `/` có năm view dùng chung một API contract:

1. Dashboard: đếm feature, rule, synthetic case và trạng thái LLM thực tế.
2. Rule Discovery: đọc aggregate model evidence và sinh candidate rule tùy chọn.
3. Knowledge Base: xem rule metadata, limitation và validation state.
4. Customer Assessment: detect domain, retrieve rule, reasoning và validation.
5. LLM Evaluation: GPT/Gemini, minimal/guided, counter-argument và reference audit.

Các endpoint tương ứng:

- `GET /api/reasoning/workspace`
- `POST /api/reasoning/rule-discovery`
- `POST /api/reasoning/assess`
- `GET /api/reasoning/evaluation/reference`
- `POST /api/reasoning/evaluate`
- `POST /api/reasoning/challenge`

## Tích hợp LLM

Không có API key thì harness chỉ chạy retrieval/prompt construction. Khi cần gọi
LLM, dùng biến môi trường:

```powershell
$env:REASONING_LLM_PROVIDER = "openrouter"
$env:OPENROUTER_API_KEY = "..."
$env:REASONING_LLM_MODEL = "google/gemini-2.5-flash"
```

`openrouter` dùng OpenAI-compatible API và có thể chọn model GPT, Claude hoặc
Gemini theo model name. Đây chưa phải native Gemini SDK adapter. OpenAI trực tiếp
dùng `REASONING_LLM_PROVIDER=openai` và `OPENAI_API_KEY`.

Chạy từ JSON bên ngoài repository:

```powershell
python scripts/run_reasoning_harness.py .\customer_features.json --use-llm
```

CLI không tự ghi input, prompt hoặc response vào repository.

## Ví dụ trong credit scoring

Khi customer có `payment_on_time_rate_12m`, `overdue_days_max_12m` và
`active_domain_count`, harness retrieve các rule payment/engagement liên quan.
Nếu một giá trị là missing, harness truyền nó vào `missing_information` thay vì
coi là tín hiệu tiêu cực.

## Điều cần kiểm tra trong project

- [ ] Chỉ gửi field nằm trong Feature Registry.
- [ ] Không để missing biến thành zero hoặc negative evidence.
- [ ] Chỉ chấp nhận rule ID tồn tại trong tập rule đã retrieve.
- [ ] Provider adapter phải trả structured output theo schema.
- [ ] Không gọi provider nếu chưa có API key được cấp phép.
- [ ] Kiểm tra model/provider hỗ trợ structured outputs trước khi đổi model.
- [ ] Không dùng harness output làm credit decision nếu target/rule chưa được phê duyệt.

## Tài liệu liên quan

- [Alternative-data feature registry](../features/alternative_data_feature_registry.md)
- [Alternative-data rule Knowledge Base](../features/alternative_data_rule_knowledge_base.md)
- [Evaluation error analysis](../evaluation/error_analysis.md)

## Trạng thái áp dụng trong project

Harness deterministic core, provider adapter, local FastAPI endpoints và web
workspace đã được triển khai và kiểm thử. OpenRouter có thể chạy model GPT hoặc
Gemini qua model ID cấu hình; OpenAI trực tiếp dùng Responses API. Reference
evaluation chỉ báo các kiểm tra mô tả từ file thật trong `simulate.zip`, không
suy ra accuracy, hallucination rate hoặc robustness score khi chưa có gold label
và rubric được phê duyệt. Chưa có rule nào được promote lên production.
