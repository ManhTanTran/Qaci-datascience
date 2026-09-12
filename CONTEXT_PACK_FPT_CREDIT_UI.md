# Context Pack — FPT Credit Reasoning PoC và UI

## Mục tiêu

Xây PoC để kiểm tra AI có suy luận đúng trên hồ sơ tài chính rút gọn từ dữ liệu FPT hay không. Đây là research PoC, không phải hệ thống xét duyệt khoản vay thật.

## Kiến trúc bắt buộc

```text
Raw Excel/CSV
  → validate dữ liệu
  → chọn/gom feature quan trọng
  → tạo profile nghiệp vụ
  → rule engine quyết định
  → AI giải thích, phát hiện mâu thuẫn và dữ liệu thiếu
```

Rule engine là nguồn quyết định. AI không được tự ý phá hard rule hoặc thay đổi kết quả rule.

## Phần UI mong muốn triển khai

UI cần bắt đầu từ bước biến đổi dữ liệu, không bắt đầu từ AI:

1. Người dùng upload file raw Excel/CSV.
2. Hiển thị số dòng, số cột, tên sheet và cảnh báo dữ liệu.
3. Hiển thị mapping `raw columns → feature quan trọng`:
   - feature/profile field đích;
   - raw columns được dùng và chưa có;
   - transform/formula;
   - trạng thái `available`, `missing`, `invalid`;
   - source trace để truy ngược.
4. Hiển thị profile rút gọn theo từng user.
5. Hiển thị kết quả rule và lý do từ rule engine.
6. Hiển thị AI response riêng: explanation, evidence, risk, missing data, conflict với rule và JSON/CSV response gốc.

UI nên có hai khu vực/tabs tách biệt:

- `Application`: xử lý một hồ sơ/người dùng cho mục đích hiển thị và tích hợp UI. Không gọi AI để quyết định.
- `Research`: chạy synthetic test cases, lặp nhiều lần, lưu response và đánh giá AI.

## Dataset và output hiện tại

- Raw workbook: `data/raw/research/fpt_reasoning_poc/FPT_credit_scoring_synthetic_10_cases.xlsx`
- Raw sheet: `Synthetic_Customers`, hiện có 10 user và 194 cột.
- Feature mapping: `configs/research/fpt_reasoning_poc/feature_mapping.yaml`
- Profile code: `src/credit_scoring/research/fpt_reasoning_poc/build_profiles.py`
- Profile dễ đọc: `data/processed/research/fpt_reasoning_poc/profiles.csv`
- Profile đầy đủ/evidence trace: `data/processed/research/fpt_reasoning_poc/profiles.jsonl`
- Validation: `data/processed/research/fpt_reasoning_poc/validation_report.json`
- Rule results: `outputs/research/fpt_reasoning_poc/rule_results.jsonl`
- AI results: `outputs/research/fpt_reasoning_poc/experiment_results.jsonl` và `.csv`

Workbook prototype hiện có các sheet chính:

`00_README → 01_DASHBOARD → 02_RAW_TO_IMPORTANT → 03_PROFILE_FEATURES → 04_VALIDATION → 05_RULE_RESULTS → 06_AI_RESPONSE`

## 10 nhóm feature quan trọng hiện tại

`user_id`, `age`, `local_context`, `location`, `device_usage`, `payment_history_12m`, `shopping_installment`, `orders`, `healthcare_spending`, `fpt_education`.

Lưu ý: đây là 10 nhóm nghiệp vụ, không phải 10 raw columns. Một profile field có thể gom nhiều raw columns.

## Quy tắc dữ liệu và nghiệp vụ

- Missing khác zero.
- Giá trị sai thang đo giữ là `invalid`, không đổi thành 0.
- Thu nhập/chi tiêu địa phương là `contextual_proxy`, không phải thu nhập cá nhân.
- Tuổi: `18-23 = FAIL`, `23-30 = UNKNOWN`, `31-40+ = PASS`; tuổi chính xác được so sánh trực tiếp.
- Trả góp, tên sản phẩm cụ thể và giáo dục FPT chưa có trong dataset; chỉ tạo synthetic test khi ghi rõ.
- Không đưa API key vào source, notebook, prompt, log hoặc tài liệu.

## Trạng thái và việc cần làm tiếp

- Pipeline local đã chạy: 10 profiles, 10 rule results, 8 synthetic test cases.
- Có 15 cảnh báo giá trị cần data owner xác nhận.
- Cần xác nhận đơn vị của `avg_monthly_income` và `avg_monthly_spend`.
- Cần xác nhận `age > 23` là hard rule chính thức hay chỉ là điều kiện test.
- Bước UI tiếp theo: làm màn upload raw và màn mapping raw → important features; sau đó mới nối profile/rule/application service.

## Nguyên tắc cho task mới

Đọc `AGENTS.md` trước khi sửa repo. Giữ logic dùng lại trong `src/credit_scoring/`, thêm test cho logic mới, không trộn code research với application, và cập nhật registry/tài liệu khi thêm dataset hoặc feature.
