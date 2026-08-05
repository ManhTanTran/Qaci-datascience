# Home Credit bureau research features

## Mục tiêu

Đăng ký 36 research candidate của E03 được tổng hợp từ `bureau.csv` và
`bureau_balance.csv` tại grain `SK_ID_CURR`. E03-BASE vẫn là E01
application-only; các feature này chưa được promote và không phải feature
production.

## Khái niệm chính

`bureau_balance` được tổng hợp trước theo `SK_ID_BUREAU`, sau đó ghép one-to-one
vào `bureau` và tổng hợp tiếp theo `SK_ID_CURR`. `MONTHS_BALANCE` tương đối so
với application date (`-1` là tháng gần nhất). `DAYS_CREDIT` gần 0 hơn nghĩa là
khoản tín dụng gần application hơn; vì vậy `MAX(DAYS_CREDIT)` là khoản gần nhất.

Mọi amount sum dùng `sum(min_count=1)`. Giá trị âm được giữ nguyên, không clip
và không tạo negative indicator. `safe_divide` trả `NaN` nếu mẫu số bằng 0 hoặc
missing; ratio âm hoặc lớn hơn 1 vẫn được giữ. Count của application không có
Bureau history được fill 0; amount, time và ratio giữ `NaN`.

### Counts — 7 feature

| Feature | Source column | Công thức | Missing policy |
|---|---|---|---|
| `BUREAU_LOAN_COUNT` | `SK_ID_BUREAU` | Count loan theo `SK_ID_CURR` | Fill 0 |
| `BUREAU_ACTIVE_COUNT` | `CREDIT_ACTIVE` | Count `CREDIT_ACTIVE == "Active"` | Fill 0 |
| `BUREAU_SOLD_COUNT` | `CREDIT_ACTIVE` | Count `CREDIT_ACTIVE == "Sold"` | Fill 0 |
| `BUREAU_CREDIT_TYPE_NUNIQUE` | `CREDIT_TYPE` | Số credit type khác nhau | Fill 0 |
| `BUREAU_CREDIT_PROLONG_SUM` | `CNT_CREDIT_PROLONG` | Sum số lần prolong | Fill 0 |
| `BUREAU_ACTIVE_LOAN_RATIO` | Hai count phía trên | `safe_divide(ACTIVE_COUNT, LOAN_COUNT)` | Denominator 0/missing → NaN |
| `BUREAU_BB_COVERAGE_RATIO` | Hai bảng qua `SK_ID_BUREAU` | Số loan có BB history / loan count | Không history hoặc denominator 0 → NaN |

`HAS_BUREAU_HISTORY` bị loại trước screening vì suy ra chính xác từ
`BUREAU_LOAN_COUNT > 0`; giữ cả hai sẽ là redundancy mức 1. `BUREAU_BAD_DEBT_COUNT`
bị loại vì chỉ có 21/1.716.428 Bureau rows.
`BUREAU_CLOSED_COUNT` không được xuất; trạng thái Closed chiếm phần còn lại sau
Active/Sold/Bad debt và phần Bad debt bị loại là cực thưa.

### Amounts — 12 feature

| Feature | Source column | Công thức | Missing policy |
|---|---|---|---|
| `BUREAU_CREDIT_SUM` | `AMT_CREDIT_SUM` | `SUM(min_count=1)` | All missing/no history → NaN |
| `BUREAU_CREDIT_MAX` | `AMT_CREDIT_SUM` | Max | Không observed value → NaN |
| `BUREAU_DEBT_SUM` | `AMT_CREDIT_SUM_DEBT` | `SUM(min_count=1)` | All missing/no history → NaN |
| `BUREAU_DEBT_MEAN` | `AMT_CREDIT_SUM_DEBT` | Mean | Không observed value → NaN |
| `BUREAU_DEBT_MAX` | `AMT_CREDIT_SUM_DEBT` | Max | Không observed value → NaN |
| `BUREAU_ACTIVE_CREDIT_SUM` | `AMT_CREDIT_SUM`, `CREDIT_ACTIVE` | `SUM(min_count=1)` trên Active loans | Không eligible/observed loan → NaN |
| `BUREAU_ACTIVE_DEBT_SUM` | `AMT_CREDIT_SUM_DEBT`, `CREDIT_ACTIVE` | `SUM(min_count=1)` trên Active loans | Không eligible/observed loan → NaN |
| `BUREAU_OVERDUE_SUM` | `AMT_CREDIT_SUM_OVERDUE` | `SUM(min_count=1)` | No history → NaN |
| `BUREAU_LIMIT_SUM` | `AMT_CREDIT_SUM_LIMIT` | `SUM(min_count=1)` | All missing/no history → NaN |
| `BUREAU_ANNUITY_SUM` | `AMT_ANNUITY` | `SUM(min_count=1)` | All missing/no history → NaN; không biến all-missing thành 0 |
| `BUREAU_DEBT_CREDIT_RATIO` | Aggregated debt/credit | `safe_divide(DEBT_SUM, CREDIT_SUM)` | Denominator 0/missing → NaN |
| `BUREAU_OVERDUE_DEBT_RATIO` | Aggregated overdue/debt | `safe_divide(OVERDUE_SUM, DEBT_SUM)` | Denominator 0/missing → NaN |

`BUREAU_OVERDUE_MAX` bị loại trước screening vì profiling cho thấy redundancy
mức 1 với `BUREAU_OVERDUE_SUM`; bản 36 feature chỉ giữ tổng overdue amount.

### Recency — 9 feature

| Feature | Source column | Công thức | Missing policy |
|---|---|---|---|
| `BUREAU_DAYS_CREDIT_MAX` | `DAYS_CREDIT` | Max; gần 0 hơn là gần application hơn | No history → NaN |
| `BUREAU_DAYS_CREDIT_MIN` | `DAYS_CREDIT` | Min | No history → NaN |
| `BUREAU_DAYS_CREDIT_MEAN` | `DAYS_CREDIT` | Mean | No history → NaN |
| `BUREAU_ACTIVE_ENDDATE_MAX` | `DAYS_CREDIT_ENDDATE`, `CREDIT_ACTIVE` | Max chỉ trên Active loans; đây là expected end date | Không eligible/observed loan → NaN |
| `BUREAU_CLOSED_ENDDATE_FACT_MAX` | `DAYS_ENDDATE_FACT`, `CREDIT_ACTIVE` | Max chỉ trên Closed loans; đây là actual end date | Không eligible/observed loan → NaN |
| `BUREAU_CLOSED_ENDDATE_DELAY_MEAN` | Hai end-date columns | Mean của `DAYS_ENDDATE_FACT - DAYS_CREDIT_ENDDATE` trên Closed loans đủ hai cột; dương là đóng muộn | Không eligible row → NaN |
| `BUREAU_BB_MONTHS_BALANCE_MIN` | `MONTHS_BALANCE` | Min qua các loan có BB history; giữ nguyên dấu | Không BB history → NaN |
| `BUREAU_BB_MONTHS_BALANCE_MAX` | `MONTHS_BALANCE` | Max qua các loan có BB history; `-1` là tháng gần nhất | Không BB history → NaN |
| `BUREAU_BB_MONTHS_SINCE_LAST_DPD` | `MONTHS_BALANCE`, `STATUS` | Loan-level `-MAX(MONTHS_BALANCE | STATUS∈1..5)`; customer-level Min qua loans | Không DPD hoặc không BB history → NaN |

Time-window và recent-k aggregates được hoãn sang E05, không phải bị từ chối.

### Delinquency — 8 feature

| Feature | Source column | Công thức | Missing policy |
|---|---|---|---|
| `BUREAU_CREDIT_DAY_OVERDUE_MAX` | `CREDIT_DAY_OVERDUE` | Max overdue days | No history → NaN |
| `BUREAU_BB_MONTH_COUNT` | `MONTHS_BALANCE` | Tổng BB rows qua các loan | Fill 0 |
| `BUREAU_BB_STATUS_0_RATIO_TOTAL` | `STATUS` | Count `0` / tổng BB month | Không BB/denominator 0 → NaN |
| `BUREAU_BB_STATUS_C_RATIO_TOTAL` | `STATUS` | Count `C` / tổng BB month | Không BB/denominator 0 → NaN |
| `BUREAU_BB_ANY_DPD_RATIO_TOTAL` | `STATUS` | Count status 1–5 / tổng BB month | Không BB/denominator 0 → NaN |
| `BUREAU_BB_ANY_DPD_RATIO_OBSERVED` | `STATUS` | Count status 1–5 / count status 0–5 | Không observed month → NaN |
| `BUREAU_BB_SEVERE_DPD_RATIO_TOTAL` | `STATUS` | Count status 3–5 / tổng BB month | Không BB/denominator 0 → NaN |
| `BUREAU_BB_SEVERE_DPD_RATIO_OBSERVED` | `STATUS` | Count status 3–5 / count status 0–5 | Không observed month → NaN |

`C` và `X` không được coi là giá trị DPD có thứ tự. Status counts chỉ là
intermediate để tính ratio và không được xuất cùng `BB_MONTH_COUNT`, tránh bộ
feature dư thừa count/ratio/denominator.

## Ví dụ trong credit scoring

`BUREAU_OVERDUE_DEBT_RATIO` biểu diễn overdue amount tương đối với tổng debt,
trong khi `BUREAU_CREDIT_DAY_OVERDUE_MAX` biểu diễn mức nghiêm trọng theo số
ngày. Hai nguồn overdue gần giống nhưng không đồng nhất nên cả hai chiều được
giữ trong research set.

## Điều cần kiểm tra trong project

- [x] Công thức, source column và missing policy của đủ 36 feature được ghi lại.
- [x] Cardinality hai tầng và merge one-to-one được synthetic assertion bảo vệ.
- [x] Amount sum dùng `min_count=1`; denominator 0 trả `NaN`.
- [x] Không dùng `TARGET`, auxiliary table ngoài Bureau hoặc leaderboard.
- [x] Smoke Kaggle version 3 hoàn tất: 5.000 train + 5.000 test application,
  49.227 Bureau rows và 1.207.059 Bureau Balance rows sau khi lọc theo ID;
  hai tầng aggregate lần lượt có 34.247 và 8.627 khóa duy nhất. Diagnostics ghi
  coverage loan-level `34.247/49.227 = 69,57%`; full screening phải đối chiếu
  lại với mốc profiling `45,11%`.
- [ ] Chỉ chạy full screening sau Checkpoint 3 và pre-registration tương ứng.

## Tài liệu liên quan

- [Credit bureau features](bureau_features.md)
- [Home Credit application features](home_credit_application_features.md)
- [Home Credit validation](../evaluation/home_credit_validation.md)
- Notebook: `notebooks/03_home_credit_multitable/01_bureau_ablation.ipynb`

## Trạng thái áp dụng trong project

Research candidate cho E03. Smoke chỉ xác nhận execution, schema, cardinality và
artifact; metric smoke không dùng để chọn feature. Chưa có full-data OOF result
và chưa được promote thành production feature.
