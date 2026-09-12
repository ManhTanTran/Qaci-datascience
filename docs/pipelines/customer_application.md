# User-facing application flow

## Mục tiêu

Đây là luồng dành cho người dùng: nhận một profile theo application contract,
validate, chạy simulation/inference đã được tích hợp và trả kết quả có human
review. Luồng này không chạy synthetic research cases, không đọc experiment
outputs và không dùng kết quả research làm quyết định tự động.

## Khái niệm chính

Application contract là đầu vào được allow-list và validate trước khi xử lý.
Kết quả mô phỏng chỉ hỗ trợ chuyên viên; nó không phải credit score hay quyết
định tín dụng.

## Vị trí code

- Application boundary: `src/credit_scoring/application/`
- User service: `src/credit_scoring/application/service.py`
- Existing API/UI implementation: `src/credit_scoring/dc5/` và `web/customer/`
- Research-only pipeline: `src/credit_scoring/research/fpt_reasoning_poc/`

## Chạy kiểm tra application flow

```powershell
python -m pytest tests/test_application_boundary.py tests/test_dc5_api.py -q
```

`assess_user_profile()` chỉ dùng profile đã validate và trả `research_used=False`.
Đây vẫn là demo/application skeleton, chưa phải hệ thống xét duyệt tín dụng
production.

## Ví dụ trong credit scoring

Một profile hợp lệ được kiểm tra schema, chuẩn hóa và đưa vào application
simulation. Các synthetic case dùng để đánh giá AI nằm ở research flow và không
được chạy trong request của user.

## Điều cần kiểm tra trong project

- [ ] Validate application input trước khi gọi model hoặc LLM.
- [ ] Giữ `human_review_required=True` cho output hiện tại.
- [ ] Không đọc `outputs/research/` trong application request.
- [ ] Review riêng mọi feature/rule trước khi promote.

## Ranh giới bắt buộc

- Research có thể tạo candidate/evaluation artifact, nhưng application không
  tự động lấy artifact đó làm rule.
- Application không import `credit_scoring.research.fpt_reasoning_poc`.
- Mọi model/rule muốn đưa vào application phải được review, có owner, formula,
  validation và test riêng.

## Tài liệu liên quan

- [FPT Credit Reasoning PoC](fpt_credit_reasoning_poc.md)
- [DC5 customer website](dc5_customer_web_development.md)
- [Alternative-data Agent Harness](alternative_data_agent_harness.md)

## Trạng thái áp dụng trong project

Application boundary đã có service và test riêng. API/UI hiện tại vẫn là demo
nghiên cứu; chưa được xem là hệ thống production hoặc quyết định tín dụng thật.
