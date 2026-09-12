# Alternative-data rule Knowledge Base

## Mục tiêu

Định nghĩa Knowledge Base V1 cho LLM reasoning trên alternative data. Các rule
hiện tại là `candidate`, không phải policy tín dụng hoặc production rule.

## Khái niệm chính

Mỗi rule có ID, type, domain, feature references, nội dung, nguồn, evidence,
limitation, confidence, status, version và validation state. Rule được lưu dưới
dạng metadata có cấu trúc, không chỉ là một câu text.

## Các rule V1

| ID | Type | Trọng tâm | Status |
|---|---|---|---|
| `RULE_PAY_001` | Evidence priority | Payment behavior ưu tiên hơn engagement khi xung đột | candidate |
| `RULE_ENG_001` | Guardrail | Engagement không tự chứng minh repayment capacity | candidate |
| `RULE_PAY_002` | Cross-domain | Engagement/shopping không tự override payment xấu | candidate |
| `RULE_PAY_003` | Limitation | Service payment không mặc định tương đương loan repayment | candidate |
| `RULE_SHOP_001` | Guardrail | Shopping frequency không tự chứng minh affordability | candidate |

Machine-readable source: `configs/reasoning/rules.yaml`.

## Ví dụ trong credit scoring

`B_conflict` có engagement mạnh nhưng payment indicators yếu. Harness tương lai
có thể retrieve `RULE_PAY_001` và `RULE_PAY_002`, sau đó yêu cầu LLM nêu rõ
conflict thay vì cho engagement override payment. Đây là evaluation behavior,
không phải credit decision.

## Điều cần kiểm tra trong project

- [ ] Không chuyển `candidate` thành `validated` nếu thiếu data support và human review.
- [ ] Không thêm threshold hoặc causal claim không có trong finding.
- [ ] Kiểm tra mọi feature reference tồn tại trong Feature Registry.
- [ ] Tăng version khi thay đổi nội dung hoặc semantics của rule.

## Tài liệu liên quan

- [Alternative-data feature registry](alternative_data_feature_registry.md)
- [Target definition](../domain/target_definition.md)
- [Model risks](../governance/model_risks.md)

## Trạng thái áp dụng trong project

Knowledge Base V1 đã được khai báo ở trạng thái research candidate. Chưa có rule
nào được phê duyệt để dùng cho production hoặc quyết định tín dụng.
