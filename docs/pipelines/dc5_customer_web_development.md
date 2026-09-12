# Kế hoạch phát triển Customer Website

## Mục đích

Tách Customer UI khỏi Streamlit thành một website riêng, có giao diện thân
thiện hơn và có thể mở rộng về sau. Streamlit hiện tại vẫn được giữ làm
prototype/fallback trong suốt quá trình chuyển đổi.

Tài liệu này mô tả các phase, phạm vi và tiêu chí nghiệm thu. Mỗi phase phải
chạy được độc lập trước khi chuyển sang phase kế tiếp.

## Phạm vi hiện tại

- Credit Reasoning Workspace tại `/`, Agent Demo cũ tại `/agent-demo` và
  Admin/Research dashboard local tại `/admin`.
- Nhập hồ sơ thủ công và upload một lead JSON theo schema `dc5-lead-v1`.
- Preview, validation, xác nhận và chạy Agent Harness reasoning flow.
- Workspace có Dashboard, Rule Discovery, Knowledge Base, Customer Assessment
  và LLM Evaluation; cả năm view dùng dữ liệu/API thật, không dùng metric minh họa.
- Không hiển thị demo index hoặc kết luận tín dụng trong flow chính.
- Không OCR, không lưu CCCD/tài liệu thật và không dùng dữ liệu này để ra quyết
  định tín dụng.

## Kiến trúc mục tiêu

```text
React + TypeScript + Tailwind
             │ HTTP/JSON
             ▼
FastAPI backend
             │
             ├── lead schema validation
             ├── credit reasoning flow + Agent Harness
             └── legacy phase-one simulation endpoint
```

Logic dùng lại phải nằm trong `src/credit_scoring/`; frontend không được tự
chép công thức simulation hoặc tự diễn giải CIC.

## Các phase phát triển

### Phase 0 — Chuẩn bị và chốt contract

**Mục tiêu:** chốt API contract, schema lead và ranh giới dữ liệu trước khi
viết frontend.

**Công việc:**

- Giữ `dc5-lead-v1` làm input contract.
- Xác định response simulation và error format thống nhất.
- Xác định frontend/backend chạy local bằng các lệnh riêng.
- Ghi nhận quyết định kiến trúc nếu thay đổi stack hoặc contract.

**Tiêu chí hoàn thành:**

- Có JSON example hợp lệ.
- Có danh sách field bắt buộc/tùy chọn và validation policy.
- Có bản mô tả endpoint sơ bộ.

### Phase 1 — Backend API và skeleton frontend

**Mục tiêu:** website mới chạy end-to-end tối thiểu, chưa tập trung vào thẩm mỹ.

**Công việc:**

- Tạo FastAPI app với endpoint health check.
- Tạo endpoint validate lead và simulate profile.
- Tạo React/TypeScript app với routing tối thiểu.
- Kết nối frontend với backend bằng HTTP JSON.
- Giữ Streamlit không bị thay đổi hoặc xóa.

**Tiêu chí hoàn thành:**

- `GET /health` trả về thành công.
- Frontend gọi được backend local.
- Lead hợp lệ trả về kết quả simulation.
- Lead sai trả về lỗi có thể hiển thị cho người dùng.
- Có unit test cho API và test build frontend.

### Phase 2 — Customer experience

**Mục tiêu:** hoàn chỉnh luồng nhập hồ sơ và upload lead.

**Công việc:**

- Form hồ sơ thủ công.
- Upload `.json`, preview dữ liệu đã chuẩn hóa.
- Nút xác nhận riêng trước khi chạy simulation.
- Màn hình kết quả là Agent Harness trace, không hiển thị demo index.
- Màn hình kết quả có `final_reasoning` gồm summary, evidence, uncertainties và
  recommended actions; mặc định chạy deterministic fallback, còn LLM là tùy
  chọn cho draft reasoning.
- Trạng thái loading, lỗi mạng, JSON không hợp lệ và empty state.
- Nút tải JSON mẫu.

**Tiêu chí hoàn thành:**

- Người dùng hoàn tất luồng mà không cần biết kỹ thuật.
- Không có thao tác upload nào tự động gửi tài liệu định danh ra ngoài.
- Không hiển thị phần Admin/Research trong Customer website.
- Có test cho happy path và các lỗi validation chính.

### Phase 3 — Thiết kế giao diện và khả năng sử dụng

**Mục tiêu:** website có chất lượng trình bày tốt hơn prototype Streamlit.

**Công việc:**

- Thiết kế màu sắc, typography, spacing và branding thống nhất.
- Responsive cho desktop/tablet/mobile.
- Thêm progress/step indicator: Nhập → Kiểm tra → Kết quả.
- Bổ sung accessibility cơ bản: label, focus state, keyboard navigation,
  contrast.
- Chuẩn hóa thông báo để không tạo cảm giác đây là credit decision thật.

**Tiêu chí hoàn thành:**

- Không vỡ layout ở kích thước màn hình chính.
- Có trạng thái hover/focus/loading/error.
- Nội dung cảnh báo research-only và human review rõ ràng.
- Có kiểm tra thủ công trên trình duyệt và screenshot review.

### Phase 4 — Kiểm thử, bảo mật và triển khai

**Mục tiêu:** chuẩn bị bản chạy ổn định ngoài môi trường developer.

**Công việc:**

- Chạy unit, integration và frontend build tests.
- Giới hạn kích thước và MIME type của upload JSON.
- Không log nội dung lead hoặc PII.
- Cấu hình CORS, environment variables và error handling production.
- Đóng gói Docker hoặc runbook triển khai phù hợp môi trường.
- Giữ Streamlit fallback cho đến khi website được nghiệm thu.

**Tiêu chí hoàn thành:**

- `ruff check .`, test phù hợp và `mkdocs build --strict` đạt trong phạm vi
  thay đổi.
- Không có secret, PII hoặc dữ liệu khách hàng trong repository.
- Có hướng dẫn rollback về Streamlit.
- Có checklist nghiệm thu và owner xác nhận trước khi gọi là production.

## API contract dự kiến

### `GET /health`

```json
{"status": "ok"}
```

### `POST /api/leads/validate`

Request body là một lead JSON theo `dc5-lead-v1`. Response trả về profile đã
chuẩn hóa; lỗi trả về message không chứa dữ liệu nhạy cảm.

### `POST /api/leads/simulate`

Request body là profile đã validate. Response gồm:

- `demo_index`
- `components`
- `cic_score`
- `cic_used_in_model: false`
- `note`

Đây là simulation minh họa, không phải credit score và không phải quyết định
cho vay.

### Admin endpoints

- `POST /api/admin/runs`: chạy `quick`, `full` hoặc mở `report-only` bằng
  artifact thực tế.
- `GET /api/admin/report`: tải report HTML mới nhất.

Report HTML hiện có một dashboard tổng quan ở đầu trang: KPI population/positive
rate, ROC-AUC/PR-AUC, EDA overview và phần insight được suy ra trực tiếp từ
metrics, missingness, feature importance và clustering của run. Insight chỉ là
mô tả thống kê; report nhắc rõ không được xem là quan hệ nhân quả hoặc quyết
định tín dụng.

Admin frontend ở route `/admin`; Customer frontend ở route `/`. Hai màn hình
không chia sẻ navigation nghiệp vụ và Admin hiển thị cảnh báo internal-only.

Admin dashboard được chia thành năm trang tương tác:

1. **Models:** bảng và biểu đồ ROC-AUC/PR-AUC, City ablation; bấm model để xem
   insight của đúng setting/model.
2. **Features:** lọc theo setting/model; bấm feature để xem importance và giới
   hạn diễn giải.
3. **Data quality:** domain coverage, missingness và target distribution; bấm
   một mục để xem insight dữ liệu.
4. **Clusters:** quy mô và profile của từng cluster khi Full mode tạo clustering
   artifact; bấm cluster để xem các profile value nổi bật.
5. **Run details:** metadata, run ID, pipeline version và tải report HTML.

Các interaction chỉ dùng artifact của run hiện tại, không sinh metric hoặc kết
luận không có trong dữ liệu.

## Legacy LLM endpoint cho bản diễn giải

Endpoint tương thích cũ `POST /api/insights/generate` vẫn được giữ để không làm
gãy client hiện tại. Flow chính dùng `POST /api/credit-flow/run`; API key chỉ
tồn tại ở backend:

```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-..."
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
python -m uvicorn credit_scoring.dc5.api:app --reload --port 8000
```

Backend tự nhận diện OpenRouter khi có `OPENROUTER_API_KEY`; không cần
`OPENAI_API_KEY`. Có thể đặt `LLM_PROVIDER=openrouter` để cấu hình tường minh.
Model được chọn phải hỗ trợ Structured Outputs. Nếu cần dùng OpenAI trực tiếp,
backend vẫn hỗ trợ `OPENAI_API_KEY` và `OPENAI_MODEL` như phương án tùy chọn.

Các model OpenRouter phù hợp với response JSON hiện tại:

- `openai/gpt-4o-mini`: lựa chọn mặc định, nhanh và tiết kiệm cho nhận xét tiếng Việt.
- `openai/gpt-4o`: chất lượng diễn giải cao hơn khi cần phân tích dài hoặc nhiều bằng chứng.
- `anthropic/claude-sonnet-4.5`: phù hợp khi ưu tiên văn phong và tuân thủ hướng dẫn; chi phí cao hơn.
- `google/gemini-2.5-flash`: lựa chọn nhanh cho prototype nếu model còn khả dụng trong tài khoản.

OpenRouter chỉ chấp nhận JSON Schema với model/provider có tham số
`structured_outputs`; danh sách hỗ trợ có thể thay đổi, nên kiểm tra cột
Supported Parameters trên trang model trước khi đổi. Code bật
`require_parameters=true` để không âm thầm hạ xuống model không đáp ứng schema.

`GET /api/insights/status` cho biết backend đã cấu hình hay chưa nhưng không bao
giờ trả lại API key. Request chỉ cho phép tuổi, thu nhập, nghề nghiệp, thâm niên,
loại nhà ở, người phụ thuộc, số dịch vụ, demo index và các component. Pydantic
từ chối field lạ, nên tên, email, điện thoại, CCCD và user ID không thể đi qua
endpoint này. Nhánh OpenRouter dùng Chat Completions tương thích OpenAI và yêu
cầu JSON Schema nghiêm ngặt; nhánh OpenAI trực tiếp dùng Responses API với
`store=False`. Response luôn có `human_review_required: true` và disclaimer rằng
đây không phải CIC/credit score/quyết định tín dụng. Disclaimer cuối cùng do
backend gắn từ hằng số đã kiểm soát; wording tự do của model không thể làm mất
cảnh báo hoặc khiến request hợp lệ bị lỗi chỉ vì model diễn đạt khác câu mẫu.

Trước mỗi lần tạo diễn giải, backend đọc `latest.json`, `metrics.csv`,
`feature_importance.csv` và `run_metadata.json` trong artifact directory. Model
có ROC-AUC cao nhất của run gần nhất được đưa vào prompt dưới dạng bằng chứng
aggregate, gồm backend, variant/setting, ROC-AUC, PR-AUC, positive rate và năm
feature importance cao nhất. Frontend hiển thị chính xác model/run đã dùng. Có
thể đổi thư mục bằng `DC5_ARTIFACT_DIR`.

Pipeline CatBoost lưu thêm `research_inference_model.cbm` và
`research_inference_manifest.json`. Bundle dùng variant có ROC-AUC cao nhất của
run và loại các feature `age_group_ord`, `gender`, `city` khỏi inference schema.
Nếu toàn bộ feature an toàn của một run đều hằng số, pipeline giữ report nhưng
không tạo inference bundle cho run đó.
`GET /api/models/inference-schema` trả về feature order, kiểu dữ liệu, target và
những feature đã loại.
`GET /api/leads/model-template` trả một lead JSON mẫu có đủ field của bundle;
Customer UI liên kết trực tiếp tới mẫu này cạnh nút upload.

Lead JSON có thể thêm object `model_features` chứa chính xác toàn bộ field trong
manifest. Backend kiểm tra thiếu/thừa field, khôi phục CatBoost, chạy
`predict_proba` và tính năm SHAP contribution có trị tuyệt đối lớn nhất. Chỉ xác
suất target nghiên cứu và reason signals được gửi sang LLM; raw feature vector
không đi qua OpenRouter. Nếu không có `model_features`, LLM vẫn dùng model
evidence aggregate và response ghi rõ chưa chạy individual inference.

Ví dụ cấu trúc rút gọn dưới đây chỉ minh họa vị trí của `model_features`; request
thực phải có đủ danh sách từ endpoint schema:

```json
{
  "schema_version": "dc5-lead-v1",
  "age": 35,
  "income_million_vnd": 15,
  "occupation": "Nhân viên văn phòng",
  "employment_years": 3,
  "household_type": "Chung cư",
  "dependents": 1,
  "service_count": 2,
  "model_features": {
    "active_domain_count_ord": 3,
    "tenure_group_ord": 4,
    "recency_group_ord": 2
  }
}
```

Output này vẫn là research candidate. Target đang dự đoán là nhóm Telco monetary
cao, không phải default/bad debt hoặc CIC score.

Không commit API key hoặc đưa key vào frontend. Chỉ bật với dữ liệu thật sau khi
data owner phê duyệt các trường được truyền và chính sách lưu giữ của provider.

## Cách chạy local

Backend:

```powershell
Set-Location -LiteralPath "D:\Work\FPT\Data science"
$env:PYTHONPATH = "$PWD\src"
python -m uvicorn credit_scoring.dc5.api:app --reload --port 8000
```

Frontend (terminal thứ hai):

```powershell
Set-Location -LiteralPath "D:\Work\FPT\Data science\web\customer"
npm install
npm run dev
```

Mở `http://localhost:5173`. Ở local, Vite proxy các request `/api` sang
`http://127.0.0.1:8000`, vì vậy browser không cần gọi cross-origin. Có thể đổi
URL backend bằng biến `VITE_API_URL` khi frontend chạy ở môi trường khác.

## Customer → Agent reasoning flow

Route `http://localhost:5173/` hiện là flow reasoning duy nhất của customer,
không còn yêu cầu nhập hồ sơ nhân viên. Sau khi xác nhận profile, trang gọi
Agent Harness ngay trên phần kết quả; backend vẫn kiểm tra lại bằng contract
`SafeProfile` trước khi chạy.

Endpoint chính là `POST /api/credit-flow/run` với body:

```json
{
  "profile": {
    "age": 35,
    "income_million_vnd": 15,
    "occupation": "Nhân viên văn phòng",
    "employment_years": 3,
    "household_type": "Chung cư",
    "dependents": 1,
    "service_count": 2
  },
  "use_llm": false
}
```

Flow trả về trace gồm: intake/extract → aggregate ML pattern → LLM rule
candidate → Knowledge Base → 3 synthetic cases → Agent Harness. `use_llm` mặc
định là `false` để không tiêu quota; bật lên chỉ khi đã cấu hình API key. Rule
do LLM sinh ra luôn là `candidate`, chưa được ghi vào KB và chưa thể dùng như
production rule.

Ba case synthetic nằm ở
`configs/reasoning/synthetic_cases.yaml`. Harness kiểm tra normalize, detect
domain, retrieve rule, dựng prompt và validate schema; đây là smoke test logic,
không phải benchmark và không có gold credit label.

ML evidence hiện đọc từ `DC5_ARTIFACT_DIR` và được gắn cờ `research_only` vì
target của run hiện tại là nhóm Telco monetary cao, không phải default/CIC. Nếu
chưa có artifact, bước ML và LLM rule candidate sẽ dừng an toàn thay vì tự tạo
pattern. Các tên feature có hậu tố `_ord` từ model DC5 được map tường minh sang
feature tương ứng trong alternative-data reasoning registry trước khi đưa vào
prompt LLM; feature không có mapping như Telco inbound count vẫn bị loại khỏi
rule candidate thay vì tự tạo định nghĩa mới.

## Legacy Agent reasoning demo cho EPI

Các endpoint `/api/agent-demo/*` cũ vẫn được giữ để tương thích với test và
client cũ, nhưng không còn là flow chính của Customer UI. Flow chính là
`/api/credit-flow/run` ở phần trên và chạy ngay sau bước xác nhận tại `/`.

Knowledge base nằm ở `configs/agent_demo_knowledge.json` và được đọc lại ở mỗi
request. Vì vậy có thể sửa ngưỡng hoặc action trong file, bấm nút reload trên
UI và chạy lại để quan sát rule/LLM conclusion thay đổi. Biến `EPI_KB_PATH` cho
phép trỏ tới một file KB khác.

API demo:

```powershell
curl http://127.0.0.1:8000/api/agent-demo/knowledge
curl http://127.0.0.1:8000/api/agent-demo/scenarios
curl http://127.0.0.1:8000/api/agent-demo/run `
  -H "Content-Type: application/json" `
  -d '{"scenario_id":"steady_analyst","target":"promotion_readiness","use_llm":true}'
```

Khi có `OPENROUTER_API_KEY`, harness gửi model score và rule findings đã rút
gọn sang OpenRouter để sinh conclusion JSON. Khi chưa có key, demo dùng
fallback deterministic để vẫn hiển thị đầy đủ trace. Model baseline hiện là
synthetic placeholder; muốn dùng EPI thật cần thay `_model_score` bằng model
đã train, có target definition, model card và validation tương ứng.

Conclusion dùng strict JSON Schema: mọi object đều khai báo
`additionalProperties: false` và tất cả field đều bắt buộc để tương thích các
provider OpenAI/Azure qua OpenRouter.

## Cách kiểm tra theo phase

Mỗi phase cần ghi lại:

1. Lệnh chạy local.
2. Test đã chạy và kết quả.
3. Screenshot hoặc artifact nếu có giao diện.
4. Các giới hạn còn tồn tại.
5. Quyết định chuyển phase của người phụ trách.

## Rủi ro và ranh giới chưa được phép vượt qua

- Không tự tạo hoặc tuyên bố CIC model khi chưa có target, dữ liệu được phê
  duyệt và model card.
- Không OCR CCCD hoặc tài liệu thu nhập trước khi có phê duyệt data governance.
- Không ghi lead, CCCD, credential hoặc PII vào log, prompt, report hay git.
- Không thay đổi target, metric hoặc validation strategy của pipeline DC5 chỉ để
  phục vụ giao diện.
- Feature/model mới vẫn là research candidate cho đến khi được review
  promotion riêng.

## Trạng thái triển khai hiện tại

- Phase 0: **Hoàn thành** — contract JSON, API response/error policy và tài liệu
  đã được chốt.
- Phase 1: **Hoàn thành local** — FastAPI API và React/TypeScript skeleton cho
  Customer và Admin đã kết nối end-to-end.
- Phase 2: **Hoàn thành local** — form, upload JSON, preview, xác nhận, kết quả
  simulation và Admin pipeline dashboard đã có.
- Phase 3: **Hoàn thành bản đầu** — responsive layout, step indicator,
  loading/error state, accessibility cơ bản và branding prototype đã có.
- Phase 4: **Hoàn thành kiểm tra local; chưa deploy** — backend tests, frontend
  production build và MkDocs đã chạy đạt; deployment/CORS production vẫn cần
  cấu hình theo môi trường đích.
- Streamlit Customer UI: **Đang được giữ làm prototype/fallback**.

## Mục tiêu

Chuyển flow Customer từ Streamlit sang website React/FastAPI local có contract
rõ, trace reasoning có thể kiểm tra và ranh giới research-only minh bạch.

## Khái niệm chính

Frontend chỉ điều phối HTTP/JSON; validation, simulation và Agent Harness nằm ở
backend/source dùng lại. Lead upload được preview và xác nhận trước khi chạy,
không lưu tài liệu định danh.

## Ví dụ trong credit scoring

Một lead hợp lệ có thể chạy flow `intake/extract → aggregate ML pattern → rule
candidate → Knowledge Base → synthetic cases → Agent Harness`. Kết quả là
research reasoning, không phải CIC score hay quyết định cho vay.

## Điều cần kiểm tra trong project

- Chạy backend tests và frontend production build; kiểm tra lỗi validation,
  network, loading và empty state.
- Giới hạn upload JSON, không log PII/credential, và giữ Streamlit fallback cho
  đến khi có owner nghiệm thu.
- Không gọi API provider nếu chưa cấu hình key và chưa phê duyệt dữ liệu được
  truyền.

## Tài liệu liên quan

- [DC5 customer analysis](dc5_customer_analysis.md)
- [Feature reasoning registry](../features/alternative_data_feature_registry.md)
- [Rule knowledge base](../features/alternative_data_rule_knowledge_base.md)

## Trạng thái áp dụng trong project

Website đã hoàn thành local ở mức prototype/research; chưa deploy production và
chưa được xem là hệ thống quyết định tín dụng.
