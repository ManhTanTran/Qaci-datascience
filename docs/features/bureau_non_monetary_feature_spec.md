# Bureau non-monetary credit-history feature specification

## Mục tiêu và phạm vi

Tài liệu này định nghĩa candidate feature set **lịch sử tín dụng phi tiền tệ** từ
block Bureau (`bureau.csv` và `bureau_balance.csv`). Nó loại giá trị tiền trực tiếp
và mọi ratio suy ra từ giá trị tiền. Các feature vẫn mô tả lịch sử, trạng thái và
hành vi tín dụng; vì vậy *non-monetary* không đồng nghĩa với *non-financial* hay
không dùng thông tin tài khoản tín dụng. Đây là research candidate, chưa phải
production feature.

Nguồn dữ liệu:

- `bureau.csv`: grain khoản vay (`SK_ID_BUREAU`), liên kết khách hàng qua `SK_ID_CURR`.
- `bureau_balance.csv`: grain khoản vay-tháng, liên kết với `bureau` qua
  `SK_ID_BUREAU`, sử dụng `MONTHS_BALANCE` và `STATUS`.

Experiment này trả lời câu hỏi: **nếu không biết số tiền đã vay/nợ/trả nhưng biết
cấu trúc và hành vi lịch sử tín dụng, model dự đoán default được đến đâu?**

Mọi feature phải được tính trước thời điểm quyết định, giữ missing khác zero, kiểm tra
khóa duy nhất ở grain khách hàng và ghi builder version trong manifest Parquet. Manifest
phải khai `feature_scope: non_monetary_credit_history` để tránh diễn giải nhầm là
non-financial.

## Feature hiện có tiếp tục sử dụng

Các feature dưới đây lấy từ block bureau/bureau-balance hiện tại và được giữ lại sau
khi kiểm tra công thức thực tế trong source builder:

| Feature | Bảng nguồn | Raw column/chìa khóa | Ý nghĩa |
|---|---|---|---|
| `BUREAU_LOAN_COUNT` | bureau | `SK_ID_BUREAU` | Số khoản tín dụng |
| `BUREAU_ACTIVE_SUM`, `BUREAU_CLOSED_SUM`, `BUREAU_ACTIVE_LOAN_COUNT` | bureau | `CREDIT_ACTIVE` | Số khoản active/closed |
| `BUREAU_ACTIVE_LOAN_RATIO` | bureau | `CREDIT_ACTIVE`, `SK_ID_BUREAU` | Tỷ lệ active trên tổng khoản |
| `BUREAU_DAYS_CREDIT_MAX`, `MIN`, `MEAN` | bureau | `DAYS_CREDIT` | Thời điểm mở tín dụng |
| `BUREAU_DAYS_CREDIT_ENDDATE_MAX`, `MIN` | bureau | `DAYS_CREDIT_ENDDATE` | Khoảng thời gian kết thúc dự kiến |
| `BUREAU_CREDIT_DAY_OVERDUE_MAX`, `MEAN` | bureau | `CREDIT_DAY_OVERDUE` | Mức overdue hiện tại, không phải amount |
| `BUREAU_HAS_OVERDUE_SUM`, `MEAN` | bureau | `CREDIT_DAY_OVERDUE > 0` | Số và tỷ lệ khoản overdue |
| `BUREAU_CNT_CREDIT_PROLONG_SUM` | bureau | `CNT_CREDIT_PROLONG` | Tổng số lần gia hạn |
| `BUREAU_CTYPE_*_COUNT` | bureau | `CREDIT_TYPE` | Số khoản theo loại credit |
| `BUREAU_BB_MONTHS_TOTAL_SUM` | bureau_balance | `MONTHS_BALANCE`, `SK_ID_BUREAU` | Số quan sát tháng |
| `BUREAU_BB_MONTHS_BALANCE_MIN_MIN` | bureau_balance | `MONTHS_BALANCE` | Tháng xa nhất được quan sát |
| `BUREAU_BB_STATUS_MEAN_MEAN`, `MAX` | bureau_balance | `STATUS` | Severity mean theo mapping ordinal; P1/experimental |
| `BUREAU_BB_STATUS_WORST_MAX` | bureau_balance | `STATUS` | Severity tệ nhất; P0 nếu mapping giữ thứ tự severity |
| `BUREAU_BB_DPD_MONTH_TOTAL_SUM` | bureau_balance | `STATUS`, `MONTHS_BALANCE` | Số tháng DPD |
| `BUREAU_BB_DPD_MONTH_SHARE_MEAN`, `MAX` | bureau_balance | `STATUS`, `MONTHS_BALANCE` | Tỷ lệ tháng DPD theo loan |
| `BUREAU_BB_LONGEST_DPD_STREAK_MAX`, `MEAN` | bureau_balance | `STATUS`, `MONTHS_BALANCE` | Chuỗi DPD liên tiếp |
| `BUREAU_BB_DPD_EPISODES_MAX`, `SUM` | bureau_balance | `STATUS`, `MONTHS_BALANCE` | Số episode DPD |
| `BUREAU_BB_RECENT_STATUS_MEAN_MEAN`, `MAX` | bureau_balance | `STATUS`, `MONTHS_BALANCE` | Severity mean trong recent window; P1/experimental |
| `BUREAU_BB_RECENT_DPD_TOTAL_SUM` | bureau_balance | `STATUS`, `MONTHS_BALANCE` | DPD trong recent window |
| `BUREAU_LOANS_WITH_DPD_COUNT` | bureau + bureau_balance | `SK_ID_BUREAU`, `STATUS` | Số loan từng có DPD |

Tổng danh sách hiện tại là 37 feature (không tính `SK_ID_CURR`). Nếu source xác nhận
`BUREAU_ACTIVE_SUM` và `BUREAU_ACTIVE_LOAN_COUNT` cùng công thức, candidate mới chỉ
giữ `BUREAU_ACTIVE_LOAN_COUNT`. Khi có schema migration riêng, đổi
`BUREAU_CLOSED_SUM` thành `BUREAU_CLOSED_LOAN_COUNT` để thống nhất cách đặt tên.

### Status mapping hiện tại

Builder pandas và Spark hiện tại dùng mapping `C → 0`, `0 → 0`, `1..5 → 1..5`;
`X` là **unobserved**. Vì vậy `BUREAU_BB_MONTHS_TOTAL_SUM` là số raw monthly rows,
có thể gồm `X`, còn denominator đúng cho DPD rate là tổng observed/eligible months.
`C` được tính là eligible observed month với DPD bằng zero. Đổi mapping này phải đổi
builder version và không được xem là cùng feature cũ.

## Feature mới dự kiến xây dựng

Các feature mới được tạo từ feature đã aggregate hoặc từ raw columns nêu dưới đây.
Không dùng các amount feature (`AMT_*`) làm input.

| Feature mới | Nguồn | Công thức/đầu vào |
|---|---|---|
| `BUREAU_HAS_HISTORY` | bureau | Sau khi left join application: `0` nếu không có bureau record, ngược lại `1` |
| `BUREAU_HAS_ACTIVE_LOAN` | bureau | `BUREAU_ACTIVE_LOAN_COUNT > 0` |
| `BUREAU_CLOSED_LOAN_RATIO` | bureau | `BUREAU_CLOSED_SUM / BUREAU_LOAN_COUNT` |
| `BUREAU_OTHER_STATUS_COUNT`, `RATIO` | bureau | `LOAN_COUNT - ACTIVE_COUNT - CLOSED_COUNT`; chỉ bật nếu `CREDIT_ACTIVE` có trạng thái khác |
| `BUREAU_CREDIT_HISTORY_DAYS` | bureau | Assert `DAYS_CREDIT <= 0`, sau đó `-BUREAU_DAYS_CREDIT_MIN` |
| `BUREAU_DAYS_SINCE_LATEST_CREDIT` | bureau | Assert `DAYS_CREDIT <= 0`, sau đó `-BUREAU_DAYS_CREDIT_MAX` |
| `BUREAU_CREDIT_SPAN_DAYS` | bureau | `MAX(DAYS_CREDIT) - MIN(DAYS_CREDIT)` |
| `BUREAU_DATED_LOAN_COUNT` | bureau | Count non-null `DAYS_CREDIT` |
| `BUREAU_LOANS_PER_YEAR` | bureau | `DATED_LOAN_COUNT / (HISTORY_DAYS / 365)`; null dưới `min_history_days_for_annualized_rate` từ config |
| `BUREAU_AVG_DAYS_BETWEEN_CREDITS` | bureau | `SPAN_DAYS / (DATED_LOAN_COUNT - 1)`; null nếu count < 2, zero hợp lệ nếu nhiều loan cùng ngày |
| `BUREAU_LOANS_LAST_180D`, `LAST_365D`, `LAST_730D` | bureau | Count `DAYS_CREDIT >= -180`, `-365`, `-730`; fixed-day windows |
| `BUREAU_CREDIT_TYPE_BUCKET_NUNIQUE` | bureau | Count of nonzero `BUREAU_CTYPE_*_COUNT` |
| `BUREAU_CREDIT_TYPE_RAW_NUNIQUE` | bureau | `CREDIT_TYPE.nunique()` trước khi gộp bucket |
| `BUREAU_DOMINANT_CREDIT_TYPE_SHARE` | bureau | `max(CTYPE counts) / BUREAU_LOAN_COUNT` |
| `BUREAU_CREDIT_TYPE_KNOWN_RATIO` | bureau | `sum(CTYPE bucket counts) / BUREAU_LOAN_COUNT` |
| `BUREAU_EVER_PROLONGED` | bureau | `BUREAU_CNT_CREDIT_PROLONG_SUM > 0` |
| `BUREAU_PROLONG_PER_LOAN` | bureau | `PROLONG_SUM / BUREAU_LOAN_COUNT` |
| `BUREAU_LOANS_WITH_PROLONG_COUNT`, `RATIO` | bureau | Count `CNT_CREDIT_PROLONG > 0`, then divide count by loan count |
| `BUREAU_LOANS_WITH_BB_COUNT` | bureau + bureau_balance | Count distinct bureau loans with at least one bureau_balance row |
| `BUREAU_HAS_BB_HISTORY` | bureau + bureau_balance | `BUREAU_LOANS_WITH_BB_COUNT > 0` |
| `BUREAU_BB_LOAN_COVERAGE_RATIO` | bureau + bureau_balance | `LOANS_WITH_BB_COUNT / LOAN_COUNT` |
| `BUREAU_EVER_HAD_DPD` | bureau + bureau_balance | `BUREAU_LOANS_WITH_DPD_COUNT > 0` |
| `BUREAU_DPD_LOAN_RATIO` | bureau + bureau_balance | `LOANS_WITH_DPD_COUNT / LOAN_COUNT` |
| `BUREAU_DPD_OBSERVED_LOAN_RATIO` | bureau + bureau_balance | `LOANS_WITH_DPD_COUNT / LOANS_WITH_BB_COUNT` |
| `BUREAU_BB_AVG_OBSERVED_MONTHS_PER_OBSERVED_LOAN` | both | `BB_OBSERVED_MONTH_TOTAL / LOANS_WITH_BB_COUNT`; excludes unobserved `X` months |
| `BUREAU_BB_OBSERVED_MONTH_TOTAL` | bureau_balance | Sum `IS_OBSERVED`; current mapping includes `C`, excludes `X` |
| `BUREAU_BB_GLOBAL_DPD_MONTH_RATIO` | bureau_balance | `DPD_MONTH_TOTAL_SUM / BB_OBSERVED_MONTH_TOTAL` |
| `BUREAU_DPD_EPISODES_PER_OBSERVED_LOAN` | both | `DPD_EPISODES_SUM / LOANS_WITH_BB_COUNT` |
| `BUREAU_AVG_DPD_EPISODE_LENGTH` | bureau_balance | `DPD_MONTH_TOTAL_SUM / DPD_EPISODES_SUM` |
| `BUREAU_RECENT_DPD_SHARE` | bureau_balance | `RECENT_DPD_TOTAL_SUM / DPD_MONTH_TOTAL_SUM` |
| `BUREAU_BB_RECENT_OBSERVED_MONTH_TOTAL` | bureau_balance | Number of eligible observed months in configured recent window |
| `BUREAU_RECENT_DPD_RATE` | bureau_balance | `RECENT_DPD_TOTAL_SUM / RECENT_OBSERVED_MONTH_TOTAL` |
| `BUREAU_DPD_RATE_TREND` | bureau_balance | `RECENT_DPD_RATE - PRIOR_DPD_RATE`, where prior excludes recent window |
| `BUREAU_STATUS_TREND` | bureau_balance | Experimental: `RECENT_STATUS_MEAN - PRIOR_STATUS_MEAN` |

`BUREAU_LOANS_PER_YEAR`, `BUREAU_AVG_DAYS_BETWEEN_CREDITS`, raw type unique,
`RECENT_DPD_SHARE`, `DPD_RATE_TREND`, mọi `STATUS_MEAN_*` và `STATUS_TREND` là
P1/experimental. Các feature còn lại là P0 candidate. Không dùng status mean/trend
làm P0 vì `STATUS` là ordinal, không phải thang đo khoảng cách tuyến tính.

Các feature dùng recent window chỉ được bật sau khi xác minh mapping `STATUS` và
kích thước cửa sổ trong source. Manifest của mỗi feature recent phải ghi explicit
window (ví dụ relative month `-11..0`, 12 tháng), mapping version và missing policy.
Mẫu số bằng zero hoặc không quan sát được phải trả missing, không trả infinity.

## Missing policy và coverage

Ba trạng thái sau phải được phân biệt sau khi left join với application:

| Trạng thái | Cờ/count | Các temporal và DPD feature |
|---|---|---|
| Không có bureau record | `HAS_HISTORY=0`, `LOAN_COUNT=0` | null |
| Có bureau nhưng không có bureau_balance | `HAS_HISTORY=1`, `HAS_BB_HISTORY=0` | BB/DPD feature là null |
| Có bureau_balance nhưng không DPD | `HAS_BB_HISTORY=1` | DPD count/rate là zero |

Không fill toàn bộ bureau feature bằng zero. Chỉ count/cờ có semantics rõ ràng mới
được dùng zero trong trường hợp không có record.

## Manifest taxonomy

Mỗi entry feature trong manifest/registry phải mang metadata tối thiểu sau để các
candidate set được chọn bằng metadata thay vì hard-code danh sách cột:

```yaml
feature_scope: non_monetary_credit_history
feature_family: structural_history | delinquency | ordinal_status
uses_monetary_value: false
uses_direct_delinquency_signal: true | false
derived_threshold_flag: true | false
priority: P0 | P1
```

Ví dụ `BUREAU_LOAN_COUNT` là `structural_history`, không direct delinquency,
P0. `BUREAU_BB_LONGEST_DPD_STREAK_MAX` là `delinquency`, direct delinquency,
P0. `BUREAU_BB_STATUS_MEAN_MEAN` là `ordinal_status`, direct delinquency, P1.
Các flag threshold như `HAS_ACTIVE_LOAN`, `EVER_PROLONGED`, `EVER_HAD_DPD` giữ lại
để thử với linear model, nhưng phải mang `derived_threshold_flag: true`.

Config của builder phải khai explicit, ví dụ:

```yaml
bureau:
  min_history_days_for_annualized_rate: 30
  recent_window:
    unit: month_index
    lower: -11
    upper: 0
    expected_width: 12
  status_mapping_version: bureau-status-v1
```

`DAYS_CREDIT` windows use fixed days (`180D`, `365D`, `730D`); recent
`bureau_balance` windows use `MONTHS_BALANCE`. The current legacy builder uses
`MONTHS_BALANCE >= -6` (seven indexed months `-6..0` when all are present), so a
new 12-month definition is a new feature/version, not a silent replacement.

## Những feature không thuộc candidate này

Loại khỏi candidate toàn bộ direct monetary và ratio suy ra từ monetary:
`AMT_CREDIT_SUM*`, `AMT_CREDIT_SUM_DEBT*`, `AMT_CREDIT_SUM_OVERDUE*`,
`AMT_CREDIT_SUM_LIMIT*`, `AMT_ANNUITY*`, `BUREAU_ACTIVE_DEBT_SUM`,
`BUREAU_ACTIVE_CREDIT_SUM`, `BUREAU_ACTIVE_LIMIT_SUM`, các debt/credit,
overdue/credit và utilization ratios.

## Quy trình xác minh trước khi dùng model

1. Đối chiếu từng công thức với pandas builder và Spark builder; không suy luận
   mapping/window chỉ từ tên Parquet.
2. Tạo block candidate Parquet mới và manifest: source table, raw inputs, formula,
   missing policy, builder version.
3. Kiểm tra schema, key set, cardinality, null mask, infinity và parity Spark/pandas.
4. Chạy ablation có nhãn structural/history và direct delinquency riêng để xác định
   score đến từ cấu trúc lịch sử hay từ direct delinquency signal.
5. Merge candidate với `application` rồi chạy OOF ablation so với baseline hiện tại.
6. Chỉ promote sau review riêng; trong giai đoạn này các feature vẫn là research
   candidate.

## Invariant bắt buộc

- `0 <= ACTIVE_LOAN_RATIO, CLOSED_LOAN_RATIO, BB_LOAN_COVERAGE_RATIO <= 1`.
- `DATED_LOAN_COUNT`, `ACTIVE_COUNT`, `CLOSED_COUNT`, `LOANS_WITH_BB_COUNT` và
  `LOANS_WITH_PROLONG_COUNT` không vượt `LOAN_COUNT`.
- `LOANS_WITH_DPD_COUNT <= LOANS_WITH_BB_COUNT`.
- `DPD_MONTH_TOTAL <= BB_OBSERVED_MONTH_TOTAL <= BB_MONTHS_TOTAL`; streak và
  episode không vượt DPD total.
- `RECENT_OBSERVED_MONTH_TOTAL <= BB_OBSERVED_MONTH_TOTAL`.
- `RECENT_DPD_TOTAL <= DPD_MONTH_TOTAL`; các DPD rate nằm trong `[0, 1]`.
- `CREDIT_HISTORY_DAYS >= DAYS_SINCE_LATEST_CREDIT`.
- `sum(credit type bucket counts) <= LOAN_COUNT`; known ratio và dominant share nằm
  trong `[0, 1]`.
- Nếu `OTHER_STATUS` được bật thì `OTHER_STATUS_COUNT >= 0`.

## Khái niệm chính

Non-monetary ở đây nghĩa là không dùng trực tiếp giá trị tiền và ratio suy ra từ
giá trị tiền; một số field vẫn là tín hiệu lịch sử tín dụng hoặc delinquency.
`X` là tháng không quan sát được, nên không được tính như tháng không quá hạn.

## Ví dụ trong credit scoring

`BUREAU_BB_LONGEST_DPD_STREAK_MAX` là candidate về hành vi delinquency, còn
`BUREAU_CREDIT_HISTORY_DAYS` mô tả cấu trúc lịch sử. Cả hai chỉ được đánh giá
qua ablation có validation riêng, không suy ra quan hệ nhân quả từ importance.

## Điều cần kiểm tra trong project

- Đối chiếu công thức, mapping `STATUS`, time window và missing policy với
  builder pandas/Spark trước khi tạo block mới.
- Kiểm tra key set, cardinality, schema, null mask, infinity và manifest sau
  mỗi aggregate/join.
- Chỉ promotion sau review owner và experiment có pre-registration riêng.

## Tài liệu liên quan

- [Spark Bureau feature contract](home_credit_bureau_spark.md)
- [Feature store](feature_store.md)
- [Experiment log](../experiments/experiment_log.md)

## Trạng thái áp dụng trong project

Đây là specification cho research candidate. Chưa có feature trong tài liệu này
được promote thành production feature.
