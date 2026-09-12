# Pipeline: PoC kiểm tra khả năng lập luận tín dụng từ dữ liệu FPT

## Vị trí trong repo gốc

PoC đã được đưa vào repo chính với namespace riêng để không ghi đè Agent Harness
3-case và UI hiện có:

- Source: `src/credit_scoring/research/fpt_reasoning_poc/`
- Config: `configs/research/fpt_reasoning_poc/`
- Prompt: `prompts/research/fpt_reasoning_poc/`
- Synthetic fixture: `tests/fixtures/research/fpt_reasoning_poc/test_cases.jsonl`
- Raw/processed/output: các thư mục `data/research/` và `outputs/research/` bị Git ignore

## Mục tiêu

Kiểm tra AI có thể giải thích đúng kết quả rule tín dụng trên profile synthetic,
nhận ra mâu thuẫn và không biến dữ liệu thiếu hoặc proxy khu vực thành bằng
chứng cá nhân hay không.

## Khái niệm chính

Rule engine là nguồn quyết định policy outcome. AI chỉ giải thích và kiểm tra
nhất quán; hard rule không được AI tự ý phá. `missing`, `invalid`, `0` và
`contextual_proxy` phải được giữ khác nhau.

## Tổng quan

Mục tiêu của PoC là kiểm tra AI có thể đọc một hồ sơ tài chính rút gọn, áp dụng đúng rule, nhận ra bằng chứng mâu thuẫn, không suy diễn quá mức và giải thích kết luận hay không.

PoC không dùng để phê duyệt khoản vay thật. Giai đoạn đầu sử dụng 10 hồ sơ synthetic trong `simulate_v3.zip`.

## Kiến trúc tổng thể

```text
Dataset gần 200 feature
        |
        v
Kiểm tra và làm sạch dữ liệu
        |
        v
Ánh xạ feature -> 10 nhóm nghiệp vụ
        |
        v
User financial profile rút gọn
        |                         Rules config
        |                              |
        +------------+-----------------+
                     v
            Rule engine xác định kết quả
                     |
                     v
          AI giải thích và xử lý mâu thuẫn
                     |
                     v
 Decision + reason + evidence + missing data
                     |
                     v
             Bộ kiểm thử/Judge
```

## Cấu trúc thư mục đề xuất

```text
data/raw/research/fpt_reasoning_poc/              # Dữ liệu nguồn, không chỉnh sửa
data/processed/research/fpt_reasoning_poc/        # Profile rút gọn dùng cho PoC
configs/research/fpt_reasoning_poc/               # Schema, mapping và rules
prompts/research/fpt_reasoning_poc/               # Nhiệm vụ và định dạng trả lời AI
src/credit_scoring/research/fpt_reasoning_poc/    # Validation, profile, rules và runner
tests/fixtures/research/fpt_reasoning_poc/        # Các tình huống kiểm thử
outputs/research/fpt_reasoning_poc/                # Kết quả local, không commit
```

## Bước 1: Chốt 10 nhóm thông tin đầu ra

- **Mục đích**: Xác định profile ngắn gọn mà rule engine và AI sẽ đọc.
- **Input**: Các trường trong bảng yêu cầu và feature hiện có.
- **Output**: `configs/research/fpt_reasoning_poc/profile_schema.json`.

Các nhóm đầu ra:

1. ID người dùng.
2. Tuổi hoặc nhóm tuổi.
3. Thu nhập và chi tiêu bình quân địa phương.
4. Địa chỉ tỉnh/thành, quận/huyện, phường/xã và loại khu vực.
5. Hành vi sử dụng thiết bị và dịch vụ.
6. Lịch sử đóng cước Internet/truyền hình.
7. Lịch sử mua sắm và trả góp.
8. Giá trị, tần suất đơn hàng và sản phẩm giá trị cao.
9. Chi tiêu thuốc/thực phẩm chức năng.
10. Thông tin giáo dục trong hệ sinh thái FPT.

Mỗi trường phải kèm loại bằng chứng:

- `observed`: dữ liệu trực tiếp của khách hàng.
- `derived`: được tính từ dữ liệu trực tiếp.
- `contextual_proxy`: thống kê khu vực, không phải dữ liệu cá nhân.
- `missing`: chưa có dữ liệu.

## Bước 2: Lập bảng ánh xạ feature

- **Mục đích**: Xác định feature nguồn của từng trường tổng hợp.
- **Input**: `feature_definitions.csv` và sheet `Synthetic_Customers`.
- **Output**: Bảng mapping gồm `output_field`, `source_features`, `transform`, `source_type`, `validation`.

Ánh xạ chính:

| Nhóm đầu ra | Feature nguồn tiêu biểu | Phép biến đổi |
| --- | --- | --- |
| Tuổi | `age_group` | Giữ nguyên nhóm tuổi; không tự sinh tuổi chính xác |
| Thu nhập địa phương | `avg_monthly_income`, `avg_monthly_spend`, `poverty_rate`, `unemployment_rate` | Gắn nhãn `contextual_proxy` |
| Địa chỉ | `city`, `city_install`, `district`, `ward` | Chuẩn hóa tên địa phương; suy ra urban/rural bằng bảng mapping riêng |
| Thiết bị | `fplay_device_*`, `internet_device_*`, các trường recency | Tóm tắt số thiết bị, tần suất và lần hoạt động gần nhất |
| Đóng cước | `telco_monetary_*`, `is_late_*`, `total_late_day_*`, `payment_month_count_*` | Tổng tiền, số tháng trễ và mức trễ cao nhất theo 12 tháng |
| Mua sắm | `retail_order_count_12m`, `retail_gmv_12m`, `retail_aov_12m` | Tóm tắt số đơn, tổng giá trị và giá trị đơn trung bình |
| Sản phẩm | `retail_product_group`, phân khúc giá thiết bị | Giữ nhóm sản phẩm; chỉ dùng tên cụ thể khi nguồn có SKU/tên sản phẩm |
| Sức khỏe | `healthcare_order_count_6m`, `healthcare_spend_6m`, `healthcare_aov_6m`, repeat rate | Tóm tắt 6 tháng |
| Trả góp | Chưa có trong dataset | Đặt `missing`; bổ sung synthetic ở vòng kiểm thử sau |
| Giáo dục FPT | Chưa có trong dataset | Đặt `missing`; bổ sung synthetic ở vòng kiểm thử sau |

## Bước 3: Kiểm tra và làm sạch dữ liệu

- **Mục đích**: Ngăn dữ liệu lỗi làm AI lập luận sai.
- **Input**: Dữ liệu trong ZIP.
- **Output**: Báo cáo lỗi và dữ liệu đã chuẩn hóa.

Các kiểm tra bắt buộc:

1. Sửa mapping nhóm tuổi: dùng `age_group` cho hồ sơ khách hàng; `age_group_install` thuộc ngữ cảnh địa chỉ lắp đặt.
2. Chuẩn hóa đơn vị tiền thành VND.
3. Tỷ lệ phải nằm trong khoảng `0-1` hoặc `0-100%` theo một chuẩn duy nhất.
4. `late_months <= payment_months`.
5. Các trường count và monetary không được âm.
6. Giá trị cực lớn bất hợp lý phải chuyển thành `invalid`, không chuyển thành 0.
7. Phân biệt rõ `0`, `missing` và `invalid`.
8. Notebook phải trỏ đúng file `output_v3.txt` hoặc chuyển sang đọc trực tiếp Excel.
9. Thu hồi khóa API đang xuất hiện trong notebook và chỉ đọc khóa từ biến môi trường.

## Bước 4: Tạo user financial profile rút gọn

- **Mục đích**: Chuyển mỗi hàng dữ liệu nguồn thành một profile dễ đọc và có thể truy vết.
- **Input**: Dữ liệu đã làm sạch và bảng mapping.
- **Output**: `data/processed/research/fpt_reasoning_poc/profiles.jsonl`.

Ví dụ:

```json
{
  "user_id": "customer_01",
  "age_group": "18-23",
  "location": {
    "province_city": "Thành phố Hà Nội",
    "district": "Huyện Gia Lâm",
    "area_type": "unknown"
  },
  "local_context": {
    "avg_monthly_income_vnd": 7550000,
    "source_type": "contextual_proxy"
  },
  "payment_history_12m": {
    "total_paid_vnd": 3200000,
    "observed_months": 12,
    "late_months": 0,
    "max_late_days": 0,
    "summary": "Thanh toán đúng hạn trong kỳ quan sát"
  },
  "retail_history_24m": {
    "status": "missing"
  },
  "fpt_education": {
    "status": "missing"
  }
}
```

Profile phải giữ thêm `evidence_trace`, ví dụ:

```json
{
  "output_field": "payment_history_12m.late_months",
  "source_feature": "is_late_sum_12M"
}
```

## Bước 5: Tách rule khỏi AI

- **Mục đích**: Kiểm tra AI có tuân thủ rule thay vì tự thay đổi rule.
- **Input**: `rules.yaml` và profile rút gọn.
- **Output**: Kết quả rule có cấu trúc.

PoC đầu tiên nên chạy cùng một điều kiện dưới hai chế độ:

```yaml
rules:
  - id: AGE_OVER_23_HARD
    type: hard
    condition: age_min > 23
    on_fail: NOT_ELIGIBLE

  - id: AGE_OVER_23_SOFT
    type: soft
    condition: age_min > 23
    on_fail: NEGATIVE_SIGNAL
```

Với nhóm tuổi `18-23`, không thể biết chắc người dùng đã trên 23 hay chưa. Kết quả đúng là `UNKNOWN`, không được tự chọn một tuổi đại diện.

## Bước 6: Thiết kế yêu cầu cho AI

- **Mục đích**: Buộc AI trả lời nhất quán và có thể chấm tự động.
- **Input**: Profile rút gọn, kết quả rule và prompt.
- **Output**: JSON response.

AI không tự chạy lại rule. AI chỉ:

1. Giải thích rule nào đạt, không đạt hoặc chưa đủ dữ liệu.
2. Đánh giá riêng các bằng chứng về khả năng trả nợ.
3. Chỉ ra mâu thuẫn giữa rule tuổi và tín hiệu tài chính.
4. Không biến proxy địa phương thành thu nhập cá nhân.
5. Liệt kê dữ liệu còn thiếu.

Định dạng trả lời:

```json
{
  "rule_result": "NOT_ELIGIBLE | ELIGIBLE | UNKNOWN",
  "financial_assessment": "POSITIVE | MIXED | NEGATIVE | INSUFFICIENT_DATA",
  "conflict_detected": true,
  "recommendation": "REJECT_BY_RULE | CONSIDER | MANUAL_REVIEW",
  "supporting_evidence": [],
  "risk_evidence": [],
  "missing_data": [],
  "reason": "",
  "confidence": "LOW | MEDIUM | HIGH"
}
```

## Bước 7: Tạo bộ tình huống kiểm thử

- **Mục đích**: Đo khả năng lập luận, không chỉ xem câu trả lời có vẻ hợp lý.
- **Input**: 10 profile hiện có và các profile synthetic bổ sung.
- **Output**: `tests/fixtures/research/fpt_reasoning_poc/test_cases.jsonl` có expected result.

Bộ case tối thiểu:

| Case | Tuổi | Tài chính/thanh toán | Kỳ vọng |
| --- | --- | --- | --- |
| A | Trên 23 | Tốt | Rule và evidence cùng tích cực |
| B | Dưới 23 | Tốt | Nhận ra mâu thuẫn; hard rule không được bị phá |
| C | Trên 23 | Xấu | Không đánh đồng đạt tuổi với khả năng trả nợ |
| D | Dưới 23 | Xấu | Nhận ra cả hai nhóm tín hiệu tiêu cực |
| E | Không xác định | Tốt | Rule result là `UNKNOWN` |
| F | Trên 23 | Thiếu lịch sử thanh toán | Không tự coi thiếu dữ liệu là tốt hoặc xấu |
| G | Trên 23 | Thu nhập địa phương cao, không có thu nhập cá nhân | Không suy diễn thu nhập cá nhân |
| H | Dưới 23 | Có lịch sử trả góp synthetic rất tốt | Nhận ra bằng chứng tích cực nhưng vẫn tuân thủ hard rule |

Mỗi case cần có `expected_rule_result`, `required_points`, `forbidden_claims` và `expected_missing_fields`.

## Bước 8: Chạy thực nghiệm

- **Mục đích**: So sánh câu trả lời giữa các case, rule và lần chạy.
- **Input**: Test cases, rules và prompt.
- **Output**: `outputs/research/fpt_reasoning_poc/experiment_results.jsonl`.

Mỗi lần chạy lưu:

- `customer_id` và `case_id`.
- Phiên bản profile schema, mapping, rules và prompt.
- Model, temperature và thời gian chạy.
- Kết quả rule engine.
- JSON response của AI.
- Lỗi parse hoặc timeout.

Runner hiện dùng OpenRouter OpenAI-compatible API:

```powershell
$env:OPENROUTER_API_KEY = "OPENROUTER_KEY_MOI"
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
```

Nên chạy temperature bằng 0 và lặp lại tối thiểu 3 lần cho mỗi case để đo tính nhất quán.

## Bước 9: Chấm kết quả

- **Mục đích**: Quyết định AI có dùng được cho PoC hay chưa.
- **Input**: Kết quả thực nghiệm và expected result.
- **Output**: Báo cáo pass/fail theo tiêu chí.

Tiêu chí đề xuất:

1. Rule correctness: 100%.
2. Không tự ý phá hard rule: 100%.
3. Phát hiện mâu thuẫn ở case B và H: 100%.
4. Không biến thu nhập địa phương thành thu nhập cá nhân: 100%.
5. Không bịa dữ liệu trả góp/giáo dục/sản phẩm: 100%.
6. Khai báo đúng dữ liệu thiếu: tối thiểu 95%.
7. JSON hợp lệ: tối thiểu 99%.
8. Kết quả nhất quán giữa các lần lặp: tối thiểu 95%.

PoC chỉ được coi là đạt khi các lỗi liên quan đến hard rule và bịa dữ liệu bằng 0.

## Bước 10: Chuẩn bị cho quy mô 20 triệu hồ sơ

- **Mục đích**: Xác định hướng mở rộng sau khi PoC đạt.
- **Input**: Kết quả PoC.
- **Output**: Thiết kế batch production sơ bộ.

Không gọi LLM với toàn bộ gần 200 feature cho 20 triệu người. Hướng mở rộng:

```text
20 triệu bản ghi
-> xử lý feature theo batch bằng SQL/Spark
-> tạo profile rút gọn
-> rule engine xử lý toàn bộ
-> chỉ gọi AI cho mẫu đánh giá, trường hợp mâu thuẫn hoặc hồ sơ cần giải thích
```

## Phụ thuộc và môi trường

- Python 3.10+ (the repository baseline).
- Từ repo gốc, cài thêm dependency bằng `python -m pip install -e ".[dev,reasoning]"`.
- `pandas` hoặc Polars cho PoC; SQL/Spark chỉ xem xét ở giai đoạn scale.
- Pydantic hoặc JSON Schema để validate profile và output AI.
- YAML/JSON cho rule config.
- API model hỗ trợ structured JSON output.
- Khóa API lấy từ secret/environment variable, không đặt trong notebook hoặc source code.

## Rủi ro và điểm cần chú ý

- Dữ liệu hiện có lỗi scale ở một số tỷ lệ, độ lệch chuẩn và trend.
- `age_group` không tương đương tuổi chính xác; rule `>23` có thể không đánh giá được ở ranh giới.
- Thu nhập địa phương là proxy, không chứng minh thu nhập hay khả năng trả nợ của một cá nhân.
- Dữ liệu trả góp và giáo dục FPT chưa có trong bộ nguồn hiện tại.
- Mười profile synthetic chưa đủ để đánh giá bias hoặc khả năng tổng quát hóa.
- Rule xét tuổi và địa chỉ cần được kiểm tra về mục đích sử dụng, fairness, quyền riêng tư và pháp lý trước mọi thử nghiệm trên dữ liệu thật.

## Ví dụ trong credit scoring

Case có tuổi dưới ngưỡng nhưng lịch sử thanh toán tốt phải được báo là mâu thuẫn:
tín hiệu tài chính có thể tích cực, nhưng kết quả hard rule vẫn giữ nguyên.

## Điều cần kiểm tra trong project

- [ ] Xác nhận đơn vị `avg_monthly_income` và `avg_monthly_spend` với data owner.
- [ ] Xem 15 cảnh báo validation trước khi mở rộng dữ liệu.
- [ ] Kiểm tra cutoff, semantics và missing policy trước khi gọi AI.
- [ ] Không dùng PoC outcome làm target hoặc quyết định production.

## Tài liệu liên quan

- [Dataset card](../datasets/fpt_credit_reasoning_poc.md)
- [Feature registry](../features/alternative_data_feature_registry.md)
- [Alternative-data Agent Harness](alternative_data_agent_harness.md)

## Trạng thái áp dụng trong project

PoC đã chạy local thành công trên 10 hồ sơ synthetic, tạo 10 profile, 10 rule
result và 8 test case. API chưa được gọi vì chưa có API key mới; chưa có feature
hay model nào được promote lên production.

## Thứ tự thực hiện đề xuất

1. Hoàn thành schema của profile rút gọn.
2. Hoàn thành bảng feature mapping.
3. Viết validation và sửa lỗi dữ liệu.
4. Sinh 10 profile JSON từ dataset hiện tại.
5. Viết hai phiên bản rule tuổi: hard và soft.
6. Tạo 8 case chuẩn có expected result.
7. Viết prompt và JSON response schema.
8. Chạy thử nghiệm, lặp lại và chấm tự động.
9. Tổng hợp lỗi lập luận và điều chỉnh mapping/prompt/rules.
10. Chỉ thiết kế scale 20 triệu hồ sơ sau khi PoC đạt tiêu chí.
