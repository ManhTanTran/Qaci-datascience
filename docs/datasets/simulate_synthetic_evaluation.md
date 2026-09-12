# Simulate synthetic evaluation bundle

## Mục tiêu

Mô tả bundle synthetic được cung cấp bên ngoài repository để đánh giá prompt,
counter-argument và reasoning LLM trên alternative data.

## Provenance và phạm vi

- **Nguồn:** file đính kèm `simulate.zip`; raw archive và raw responses không
  được commit vào Git.
- **Nội dung:** 3 synthetic customers, 2 prompt variants, 2 model one-shot
  responses và 2 counter-argument responses.
- **Workbook:** 3 sheet; một sheet có 3 customer rows và 115 cột; một sheet
  mô tả scenario; một sheet rút gọn 33 cột cho prompt.
- **Grain:** một dòng cho mỗi synthetic scenario/customer.
- **Target:** không có credit target. Scenario type là evaluation intent, không
  phải nhãn default/non-default.

## Khái niệm chính

Scenario intent mô tả mẫu hành vi cần kiểm tra, không phải nhãn outcome. One-shot
và counter-argument là các lượt tương tác của LLM, không phải ground truth.

## Cách sử dụng

Bundle phù hợp để:

- kiểm tra prompt Guided so với Minimal;
- kiểm tra xử lý mâu thuẫn engagement/payment;
- xây counter-argument baseline;
- kiểm tra parser và output validator.

Flow web hiện dùng thêm fixture đã chuẩn hóa tại
`configs/reasoning/synthetic_cases.yaml`. Fixture này có đúng ba case để smoke
test domain detection, rule retrieval và Agent Harness; nó không thay thế
workbook đính kèm, không có gold label và không dùng để benchmark.

Bundle chưa phù hợp để:

- train model hoặc đo hiệu quả ML;
- suy ra xác suất default;
- xây production Knowledge Base;
- xác nhận quan hệ nhân quả giữa feature và creditworthiness.

## Ví dụ trong credit scoring

`B_conflict` dùng để kiểm tra LLM có giữ tách biệt giữa engagement mạnh và payment
behavior yếu hay không. Kết quả của scenario này không được dùng làm nhãn bad/good.

## Vấn đề dữ liệu cần chuẩn hóa

- `Unnamed: 0` và BOM trong tên `user_id`.
- Missing đang trộn giữa ô trống, `null` và chuỗi `Không có`.
- Payment semantics, units, denominators và time windows chưa được cung cấp.
- Retail fields thiếu có hệ thống ở cả ba scenario.
- `annual_telco_monetary` không tồn tại nên chưa thể tạo prototype label 4M.

## Điều cần kiểm tra trong project

- [ ] Giữ archive và raw responses ngoài Git.
- [ ] Xác nhận prompt version, model metadata và counter prompt trước khi tính metric.
- [ ] Xác nhận payment semantics, denominator, unit và observation cutoff.
- [ ] Không dùng scenario intent làm credit-risk target.

## Tài liệu liên quan

- [Alternative-data feature registry](../features/alternative_data_feature_registry.md)
- [Target definition](../domain/target_definition.md)
- [Evaluation error analysis](../evaluation/error_analysis.md)

## Trạng thái áp dụng trong project

Phase 0 audit completed. Phase 1 evaluation contracts are implemented; raw
attachment metadata and model-run metadata remain incomplete.

## Trạng thái

Đã audit ở Phase 0. Manifest máy đọc nằm tại
`configs/reasoning/evaluation_manifest.json`.
