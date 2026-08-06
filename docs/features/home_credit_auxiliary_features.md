# Home Credit auxiliary-table research features

## Mục tiêu

Đăng ký toàn bộ research candidate sinh từ năm bảng phụ Home Credit tại grain
`SK_ID_CURR`. Trang này được **sinh tự động từ khai báo `Aggregation` trong
source**, nên công thức ở đây luôn khớp với code đang chạy. Đây là research
candidate, không phải feature production.

## Khái niệm chính

Mỗi feature sinh ra từ một cột nguồn và một thống kê. Tên cột đầu ra ghép theo
quy tắc `{prefix}{tên}_{THỐNG_KÊ}`.

Hai loại tổng được phân biệt rõ:

- `SUM` cộng cột chỉ báo. Nhóm không có dòng nào cho 0, vì "không có bản ghi
  nào" là sự thật chứ không phải thiếu dữ liệu.
- `SUM_OBSERVED` cộng đại lượng đo được bằng `sum(min_count=1)`. Nhóm không
  quan sát được giá trị nào giữ `NaN`, để "không biết nợ bao nhiêu" không bị
  nhập làm một với "nợ bằng 0".

Ratio dùng `credit_scoring.numeric.safe_divide`: mẫu số bằng 0 hoặc missing đều
trả `NaN`, không clip, không tạo cờ denominator.

Danh sách category là cố định, khai trong source. Giá trị ngoài danh sách gom
vào `OTHER`. Nhờ vậy tập cột đầu ra giống nhau khi chạy trên mẫu và trên full
data — đã kiểm chứng: cả năm block cho đúng cùng số cột ở 7.000 khách và ở hơn
300.000 khách.

## Block `bureau`

Nguồn: `bureau.csv`, `bureau_balance.csv`. `builder_version`: `bureau-v1`.

### Gom theo SK_ID_BUREAU

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `BB_MONTHS_COUNT` | `MONTHS_BALANCE` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `BB_MONTHS_BALANCE_MIN` | `MONTHS_BALANCE` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | recency |
| `BB_STATUS_MEAN` | `STATUS_SEVERITY` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BB_STATUS_MAX` | `STATUS_SEVERITY` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BB_DPD_MONTH_SUM` | `IS_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `BB_OBSERVED_MONTH_SUM` | `IS_OBSERVED` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |

### Gom theo SK_ID_BUREAU (6 tháng gần nhất)

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `BB_RECENT_STATUS_MEAN` | `STATUS_SEVERITY` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BB_RECENT_DPD_SUM` | `IS_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |

### Gom theo SK_ID_CURR

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `BUREAU_DAYS_CREDIT_MAX` | `DAYS_CREDIT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | recency |
| `BUREAU_DAYS_CREDIT_MIN` | `DAYS_CREDIT` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | recency |
| `BUREAU_DAYS_CREDIT_MEAN` | `DAYS_CREDIT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | recency |
| `BUREAU_DAYS_CREDIT_ENDDATE_MAX` | `DAYS_CREDIT_ENDDATE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | recency |
| `BUREAU_DAYS_CREDIT_ENDDATE_MIN` | `DAYS_CREDIT_ENDDATE` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | recency |
| `BUREAU_CREDIT_DAY_OVERDUE_MAX` | `CREDIT_DAY_OVERDUE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_CREDIT_DAY_OVERDUE_MEAN` | `CREDIT_DAY_OVERDUE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_AMT_CREDIT_SUM_SUM` | `AMT_CREDIT_SUM` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_AMT_CREDIT_SUM_MEAN` | `AMT_CREDIT_SUM` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_CREDIT_SUM_MAX` | `AMT_CREDIT_SUM` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_CREDIT_SUM_DEBT_SUM` | `AMT_CREDIT_SUM_DEBT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_AMT_CREDIT_SUM_DEBT_MEAN` | `AMT_CREDIT_SUM_DEBT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_CREDIT_SUM_DEBT_MAX` | `AMT_CREDIT_SUM_DEBT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM` | `AMT_CREDIT_SUM_OVERDUE` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_AMT_CREDIT_SUM_OVERDUE_MAX` | `AMT_CREDIT_SUM_OVERDUE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_CREDIT_SUM_LIMIT_SUM` | `AMT_CREDIT_SUM_LIMIT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_AMT_CREDIT_MAX_OVERDUE_MAX` | `AMT_CREDIT_MAX_OVERDUE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_CREDIT_MAX_OVERDUE_MEAN` | `AMT_CREDIT_MAX_OVERDUE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_AMT_ANNUITY_SUM` | `AMT_ANNUITY` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_AMT_ANNUITY_MEAN` | `AMT_ANNUITY` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_CNT_CREDIT_PROLONG_SUM` | `CNT_CREDIT_PROLONG` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `BUREAU_DEBT_CREDIT_RATIO_MEAN` | `DEBT_CREDIT_RATIO` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_DEBT_CREDIT_RATIO_MAX` | `DEBT_CREDIT_RATIO` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_DEBT_CREDIT_RATIO_MIN` | `DEBT_CREDIT_RATIO` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_OVERDUE_CREDIT_RATIO_MEAN` | `OVERDUE_CREDIT_RATIO` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_OVERDUE_CREDIT_RATIO_MAX` | `OVERDUE_CREDIT_RATIO` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `BUREAU_ACTIVE_SUM` | `IS_ACTIVE` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `BUREAU_CLOSED_SUM` | `IS_CLOSED` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `BUREAU_HAS_OVERDUE_SUM` | `HAS_OVERDUE` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `BUREAU_HAS_OVERDUE_MEAN` | `HAS_OVERDUE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_LOAN_COUNT` | `SK_ID_BUREAU` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `BUREAU_BB_MONTHS_TOTAL_SUM` | `BB_MONTHS_COUNT` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `BUREAU_BB_STATUS_MEAN_MEAN` | `BB_STATUS_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_STATUS_MEAN_MAX` | `BB_STATUS_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_STATUS_WORST_MAX` | `BB_STATUS_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_MONTHS_BALANCE_MIN_MIN` | `BB_MONTHS_BALANCE_MIN` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | recency |
| `BUREAU_BB_DPD_MONTH_TOTAL_SUM` | `BB_DPD_MONTH_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `BUREAU_BB_DPD_MONTH_SHARE_MEAN` | `BB_DPD_MONTH_SHARE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_DPD_MONTH_SHARE_MAX` | `BB_DPD_MONTH_SHARE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_LONGEST_DPD_STREAK_MAX` | `BB_LONGEST_DPD_STREAK` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_LONGEST_DPD_STREAK_MEAN` | `BB_LONGEST_DPD_STREAK` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_DPD_EPISODES_MAX` | `BB_DPD_EPISODES` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_DPD_EPISODES_SUM` | `BB_DPD_EPISODES` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `BUREAU_BB_RECENT_STATUS_MEAN_MEAN` | `BB_RECENT_STATUS_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_RECENT_STATUS_MEAN_MAX` | `BB_RECENT_STATUS_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `BUREAU_BB_RECENT_DPD_TOTAL_SUM` | `BB_RECENT_DPD_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |

### Gom theo SK_ID_CURR (chỉ loan Active)

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `BUREAU_ACTIVE_DEBT_SUM` | `AMT_CREDIT_SUM_DEBT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_ACTIVE_CREDIT_SUM` | `AMT_CREDIT_SUM` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_ACTIVE_LIMIT_SUM` | `AMT_CREDIT_SUM_LIMIT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `BUREAU_ACTIVE_LOAN_COUNT` | `SK_ID_BUREAU` | Đếm số dòng trong nhóm | Fill 0 | counts |

## Block `previous_application`

Nguồn: `previous_application.csv`. `builder_version`: `previous-application-v1`.

### Gom theo SK_ID_CURR

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `PREV_APPLICATION_COUNT` | `SK_ID_PREV` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `PREV_APPROVED_SUM` | `IS_APPROVED` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `PREV_APPROVED_MEAN` | `IS_APPROVED` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `PREV_REFUSED_SUM` | `IS_REFUSED` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `PREV_REFUSED_MEAN` | `IS_REFUSED` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `PREV_CANCELLED_SUM` | `IS_CANCELLED` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `PREV_CANCELLED_MEAN` | `IS_CANCELLED` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `PREV_AMT_CREDIT_SUM` | `AMT_CREDIT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `PREV_AMT_CREDIT_MEAN` | `AMT_CREDIT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_CREDIT_MAX` | `AMT_CREDIT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_APPLICATION_MEAN` | `AMT_APPLICATION` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_APPLICATION_MAX` | `AMT_APPLICATION` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_ANNUITY_MEAN` | `AMT_ANNUITY` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_ANNUITY_MAX` | `AMT_ANNUITY` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_DIFF_APPLICATION_CREDIT_MEAN` | `AMT_DIFF_APPLICATION_CREDIT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_DIFF_APPLICATION_CREDIT_MAX` | `AMT_DIFF_APPLICATION_CREDIT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_AMT_DIFF_APPLICATION_CREDIT_MIN` | `AMT_DIFF_APPLICATION_CREDIT` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_DOWN_PAYMENT_RATIO_MEAN` | `DOWN_PAYMENT_RATIO` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_DOWN_PAYMENT_RATIO_MAX` | `DOWN_PAYMENT_RATIO` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_RATE_DOWN_PAYMENT_MEAN` | `RATE_DOWN_PAYMENT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_RATE_DOWN_PAYMENT_MAX` | `RATE_DOWN_PAYMENT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_LOAN_TO_PRICE_MEAN` | `LOAN_TO_PRICE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_LOAN_TO_PRICE_MAX` | `LOAN_TO_PRICE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_DAYS_DECISION_MAX` | `DAYS_DECISION` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | recency |
| `PREV_DAYS_DECISION_MIN` | `DAYS_DECISION` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | recency |
| `PREV_DAYS_DECISION_MEAN` | `DAYS_DECISION` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | recency |
| `PREV_CNT_PAYMENT_MEAN` | `CNT_PAYMENT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `PREV_CNT_PAYMENT_MAX` | `CNT_PAYMENT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |

### Gom theo SK_ID_CURR (chỉ đơn Approved)

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `PREV_HIST_CREDIT_MAX` | `AMT_CREDIT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `PREV_HIST_CREDIT_MEAN` | `AMT_CREDIT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PREV_HIST_ANNUITY_MAX` | `AMT_ANNUITY` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |

## Block `installments`

Nguồn: `installments_payments.csv`. `builder_version`: `installments-v1`.

### Gom theo SK_ID_PREV

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `INST_COUNT` | `NUM_INSTALMENT_NUMBER` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `DPD_MEAN` | `DPD` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `DPD_MAX` | `DPD` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `DPD_SUM` | `DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `LATE_SUM` | `IS_LATE` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `PAYMENT_RATIO_MEAN` | `PAYMENT_RATIO` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PAYMENT_RATIO_MIN` | `PAYMENT_RATIO` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `UNDERPAYMENT_SUM` | `UNDERPAYMENT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `UNDERPAYMENT_MAX` | `UNDERPAYMENT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `UNDERPAID_SUM` | `IS_UNDERPAID` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | amounts |
| `DPD_GE_7_SUM` | `DPD_GE_7` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `DPD_GE_30_SUM` | `DPD_GE_30` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `DPD_GE_60_SUM` | `DPD_GE_60` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `DPD_GE_90_SUM` | `DPD_GE_90` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |

### Gom theo SK_ID_CURR

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `INST_INST_LOAN_COUNT` | `SK_ID_PREV` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `INST_INST_COUNT_SUM` | `INST_COUNT` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `INST_INST_COUNT_MEAN` | `INST_COUNT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `INST_INST_COUNT_MAX` | `INST_COUNT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |
| `INST_DPD_MEAN_MEAN` | `DPD_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `INST_DPD_MEAN_MAX` | `DPD_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `INST_DPD_WORST_MAX` | `DPD_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `INST_DPD_WORST_MEAN` | `DPD_MAX` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `INST_DPD_TOTAL_SUM` | `DPD_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_LATE_SUM` | `LATE_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_LATE_MAX` | `LATE_SUM` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `INST_LATE_RATE_MEAN` | `LATE_RATE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `INST_LATE_RATE_MAX` | `LATE_RATE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `INST_PAYMENT_RATIO_MEAN_MEAN` | `PAYMENT_RATIO_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `INST_PAYMENT_RATIO_MEAN_MIN` | `PAYMENT_RATIO_MEAN` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `INST_PAYMENT_RATIO_WORST_MIN` | `PAYMENT_RATIO_MIN` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `INST_UNDERPAYMENT_SUM` | `UNDERPAYMENT_SUM` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `INST_UNDERPAYMENT_MAX` | `UNDERPAYMENT_SUM` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `INST_UNDERPAID_SUM` | `UNDERPAID_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | amounts |
| `INST_UNDERPAID_RATE_MEAN` | `UNDERPAID_RATE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `INST_UNDERPAID_RATE_MAX` | `UNDERPAID_RATE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `INST_LONGEST_LATE_STREAK_MAX` | `LONGEST_LATE_STREAK` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `INST_LONGEST_LATE_STREAK_MEAN` | `LONGEST_LATE_STREAK` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `INST_LATE_EPISODES_MAX` | `LATE_EPISODES` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `INST_LATE_EPISODES_SUM` | `LATE_EPISODES` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_DPD_GE_7_SUM` | `DPD_GE_7_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_DPD_GE_30_SUM` | `DPD_GE_30_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_DPD_GE_60_SUM` | `DPD_GE_60_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_DPD_GE_90_SUM` | `DPD_GE_90_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |

### Gom theo SK_ID_CURR

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `INST_DPD_LIFETIME_MEAN` | `DPD` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `INST_PAYMENT_RATIO_LIFETIME_MEAN` | `PAYMENT_RATIO` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `INST_LATE_LIFETIME_SUM` | `IS_LATE` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `INST_COUNT_LIFETIME_COUNT` | `NUM_INSTALMENT_NUMBER` | Đếm số dòng trong nhóm | Fill 0 | counts |

## Block `credit_card`

Nguồn: `credit_card_balance.csv`. `builder_version`: `credit-card-v1`.

### Gom theo SK_ID_PREV

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `CC_MONTHS_COUNT` | `MONTHS_BALANCE` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `UTILIZATION_MEAN` | `UTILIZATION` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `UTILIZATION_MAX` | `UTILIZATION` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `UTILIZATION_MIN` | `UTILIZATION` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `UTILIZATION_LAST` | `UTILIZATION` | Giá trị của dòng cuối sau khi sắp xếp | Giữ NaN nếu không có giá trị | amounts |
| `CC_HIGH_UTIL_MONTH_SUM` | `IS_HIGH_UTILIZATION` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | amounts |
| `PAYMENT_RATIO_MEAN` | `PAYMENT_RATIO` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `PAYMENT_RATIO_MIN` | `PAYMENT_RATIO` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `SK_DPD_MEAN` | `SK_DPD` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_MAX` | `SK_DPD` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_SUM` | `SK_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `SK_DPD_DEF_MEAN` | `SK_DPD_DEF` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_DEF_MAX` | `SK_DPD_DEF` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `CC_DPD_MONTH_SUM` | `IS_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `AMT_BALANCE_MEAN` | `AMT_BALANCE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `AMT_BALANCE_MAX` | `AMT_BALANCE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `AMT_BALANCE_LAST` | `AMT_BALANCE` | Giá trị của dòng cuối sau khi sắp xếp | Giữ NaN nếu không có giá trị | amounts |
| `AMT_CREDIT_LIMIT_ACTUAL_MEAN` | `AMT_CREDIT_LIMIT_ACTUAL` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `AMT_CREDIT_LIMIT_ACTUAL_MAX` | `AMT_CREDIT_LIMIT_ACTUAL` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `AMT_CREDIT_LIMIT_ACTUAL_LAST` | `AMT_CREDIT_LIMIT_ACTUAL` | Giá trị của dòng cuối sau khi sắp xếp | Giữ NaN nếu không có giá trị | amounts |
| `AMT_DRAWINGS_CURRENT_MEAN` | `AMT_DRAWINGS_CURRENT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `AMT_DRAWINGS_CURRENT_SUM` | `AMT_DRAWINGS_CURRENT` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `CC_DRAWING_MONTH_SUM` | `HAS_DRAWING` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `CC_ACTIVE_LAST` | `IS_ACTIVE` | Giá trị của dòng cuối sau khi sắp xếp | Giữ NaN nếu không có giá trị | counts |

### Gom theo SK_ID_CURR

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `CC_CC_CARD_COUNT` | `SK_ID_PREV` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `CC_CC_MONTHS_COUNT_SUM` | `CC_MONTHS_COUNT` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `CC_CC_MONTHS_COUNT_MEAN` | `CC_MONTHS_COUNT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `CC_UTILIZATION_MEAN_MEAN` | `UTILIZATION_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_UTILIZATION_MEAN_MAX` | `UTILIZATION_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_UTILIZATION_WORST_MAX` | `UTILIZATION_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_UTILIZATION_LAST_MEAN` | `UTILIZATION_LAST` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_UTILIZATION_LAST_MAX` | `UTILIZATION_LAST` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_HIGH_UTIL_MONTH_SUM` | `CC_HIGH_UTIL_MONTH_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | amounts |
| `CC_CC_HIGH_UTIL_MONTH_MAX` | `CC_HIGH_UTIL_MONTH_SUM` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_HIGH_UTIL_RATE_MEAN` | `CC_HIGH_UTIL_RATE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_HIGH_UTIL_RATE_MAX` | `CC_HIGH_UTIL_RATE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_PAYMENT_RATIO_MEAN_MEAN` | `PAYMENT_RATIO_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_PAYMENT_RATIO_MEAN_MIN` | `PAYMENT_RATIO_MEAN` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_SK_DPD_MEAN_MEAN` | `SK_DPD_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `CC_SK_DPD_MEAN_MAX` | `SK_DPD_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `CC_SK_DPD_WORST_MAX` | `SK_DPD_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `CC_SK_DPD_DEF_WORST_MAX` | `SK_DPD_DEF_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `CC_CC_DPD_MONTH_SUM` | `CC_DPD_MONTH_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `CC_CC_DPD_MONTH_MAX` | `CC_DPD_MONTH_SUM` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `CC_CC_DPD_RATE_MEAN` | `CC_DPD_RATE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `CC_CC_DPD_RATE_MAX` | `CC_DPD_RATE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `CC_AMT_BALANCE_MEAN_MEAN` | `AMT_BALANCE_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_AMT_BALANCE_MEAN_MAX` | `AMT_BALANCE_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_AMT_CREDIT_LIMIT_ACTUAL_MAX_MAX` | `AMT_CREDIT_LIMIT_ACTUAL_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_AMT_CREDIT_LIMIT_ACTUAL_MAX_SUM` | `AMT_CREDIT_LIMIT_ACTUAL_MAX` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `CC_AMT_DRAWINGS_CURRENT_SUM_SUM` | `AMT_DRAWINGS_CURRENT_SUM` | `sum(min_count=1)`; không quan sát được giá trị nào thì NaN | NaN nếu không có giá trị quan sát được | amounts |
| `CC_CC_UTIL_TREND_SLOPE_MEAN` | `CC_UTIL_TREND_SLOPE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_UTIL_TREND_SLOPE_MAX` | `CC_UTIL_TREND_SLOPE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_ACTIVE_CARD_SUM` | `CC_ACTIVE_LAST` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |

### Gom theo SK_ID_CURR (6 tháng gần nhất)

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `CC_CC_RECENT_UTILIZATION_MEAN` | `UTILIZATION` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_RECENT_UTILIZATION_MAX` | `UTILIZATION` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | amounts |
| `CC_CC_RECENT_DPD_MAX` | `SK_DPD` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |

## Block `pos_cash`

Nguồn: `POS_CASH_balance.csv`. `builder_version`: `pos-cash-v1`.

### Gom theo SK_ID_PREV

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `POS_MONTHS_COUNT` | `MONTHS_BALANCE` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `POS_LAST_MONTH_MAX` | `MONTHS_BALANCE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | recency |
| `SK_DPD_MEAN` | `SK_DPD` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_MAX` | `SK_DPD` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_SUM` | `SK_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `SK_DPD_DEF_MEAN` | `SK_DPD_DEF` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_DEF_MAX` | `SK_DPD_DEF` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `SK_DPD_DEF_SUM` | `SK_DPD_DEF` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `POS_DPD_MONTH_SUM` | `IS_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `CNT_INSTALMENT_MAX` | `CNT_INSTALMENT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |
| `CNT_INSTALMENT_FUTURE_MIN` | `CNT_INSTALMENT_FUTURE` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | counts |
| `COMPLETION_RATIO_MAX` | `COMPLETION_RATIO` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |
| `POS_COMPLETED_MAX` | `IS_COMPLETED` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |

### Gom theo SK_ID_CURR

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `POS_POS_CONTRACT_COUNT` | `SK_ID_PREV` | Đếm số dòng trong nhóm | Fill 0 | counts |
| `POS_POS_MONTHS_COUNT_SUM` | `POS_MONTHS_COUNT` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |
| `POS_POS_MONTHS_COUNT_MEAN` | `POS_MONTHS_COUNT` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `POS_POS_MONTHS_COUNT_MAX` | `POS_MONTHS_COUNT` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |
| `POS_POS_LAST_MONTH_MAX` | `POS_LAST_MONTH_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | recency |
| `POS_SK_DPD_MEAN_MEAN` | `SK_DPD_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `POS_SK_DPD_MEAN_MAX` | `SK_DPD_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_SK_DPD_WORST_MAX` | `SK_DPD_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_SK_DPD_TOTAL_SUM` | `SK_DPD_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `POS_SK_DPD_DEF_MEAN_MEAN` | `SK_DPD_DEF_MEAN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `POS_SK_DPD_DEF_MEAN_MAX` | `SK_DPD_DEF_MEAN` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_SK_DPD_DEF_WORST_MAX` | `SK_DPD_DEF_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_DPD_MONTH_SUM` | `POS_DPD_MONTH_SUM` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `POS_POS_DPD_MONTH_MAX` | `POS_DPD_MONTH_SUM` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_DPD_RATE_MEAN` | `POS_DPD_RATE` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_DPD_RATE_MAX` | `POS_DPD_RATE` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_LONGEST_DPD_STREAK_MAX` | `POS_LONGEST_DPD_STREAK` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_LONGEST_DPD_STREAK_MEAN` | `POS_LONGEST_DPD_STREAK` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_DPD_EPISODES_MAX` | `POS_DPD_EPISODES` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_DPD_EPISODES_SUM` | `POS_DPD_EPISODES` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |
| `POS_CNT_INSTALMENT_MAX_MEAN` | `CNT_INSTALMENT_MAX` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `POS_CNT_INSTALMENT_MAX_MAX` | `CNT_INSTALMENT_MAX` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | counts |
| `POS_CNT_INSTALMENT_FUTURE_MIN_MEAN` | `CNT_INSTALMENT_FUTURE_MIN` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `POS_CNT_INSTALMENT_FUTURE_MIN_MIN` | `CNT_INSTALMENT_FUTURE_MIN` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | counts |
| `POS_COMPLETION_RATIO_MAX_MEAN` | `COMPLETION_RATIO_MAX` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | counts |
| `POS_COMPLETION_RATIO_MAX_MIN` | `COMPLETION_RATIO_MAX` | Giá trị nhỏ nhất | Giữ NaN nếu không có giá trị | counts |
| `POS_POS_COMPLETED_SUM` | `POS_COMPLETED_MAX` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | counts |

### Gom theo SK_ID_CURR (6 tháng gần nhất)

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `POS_POS_RECENT_DPD_MAX` | `SK_DPD` | Giá trị lớn nhất | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_RECENT_DPD_MEAN` | `SK_DPD` | Trung bình các giá trị quan sát được | Giữ NaN nếu không có giá trị | delinquency |
| `POS_POS_RECENT_DPD_MONTH_SUM` | `IS_DPD` | Tổng chỉ báo; nhóm không có dòng nào là 0 | Fill 0 | delinquency |

## Cột phái sinh tính sau khi aggregate

### Block `bureau`

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `BUREAU_CTYPE_Consumer credit_COUNT` | `CREDIT_TYPE` | Đếm loan có `CREDIT_TYPE` bằng `Consumer credit`; giá trị ngoài danh sách khai báo gom vào `OTHER` | Fill 0 | counts |
| `BUREAU_CTYPE_Credit card_COUNT` | `CREDIT_TYPE` | Đếm loan có `CREDIT_TYPE` bằng `Credit card`; giá trị ngoài danh sách khai báo gom vào `OTHER` | Fill 0 | counts |
| `BUREAU_CTYPE_Car loan_COUNT` | `CREDIT_TYPE` | Đếm loan có `CREDIT_TYPE` bằng `Car loan`; giá trị ngoài danh sách khai báo gom vào `OTHER` | Fill 0 | counts |
| `BUREAU_CTYPE_Mortgage_COUNT` | `CREDIT_TYPE` | Đếm loan có `CREDIT_TYPE` bằng `Mortgage`; giá trị ngoài danh sách khai báo gom vào `OTHER` | Fill 0 | counts |
| `BUREAU_CTYPE_Microloan_COUNT` | `CREDIT_TYPE` | Đếm loan có `CREDIT_TYPE` bằng `Microloan`; giá trị ngoài danh sách khai báo gom vào `OTHER` | Fill 0 | counts |
| `BUREAU_CTYPE_OTHER_COUNT` | `CREDIT_TYPE` | Đếm loan có `CREDIT_TYPE` bằng `OTHER`; giá trị ngoài danh sách khai báo gom vào `OTHER` | Fill 0 | counts |
| `BUREAU_LOANS_WITH_DPD_COUNT` | `STATUS` qua `SK_ID_BUREAU` | Đếm loan có ít nhất một tháng DPD | Fill 0 | counts |
| `BUREAU_ACTIVE_LOAN_RATIO` | Hai count phía trên | `safe_divide(ACTIVE_LOAN_COUNT, LOAN_COUNT)` | Mẫu số 0 hoặc missing → NaN | counts |
| `BUREAU_ACTIVE_UTILIZATION` | Debt/credit của loan Active | `safe_divide(ACTIVE_DEBT_SUM, ACTIVE_CREDIT_SUM)` | Mẫu số 0 hoặc missing → NaN | amounts |
| `BUREAU_DEBT_CREDIT_RATIO_TOTAL` | Tổng debt và tổng credit | `safe_divide(AMT_CREDIT_SUM_DEBT_SUM, AMT_CREDIT_SUM_SUM)` | Mẫu số 0 hoặc missing → NaN | amounts |
| `BUREAU_OVERDUE_DEBT_RATIO_TOTAL` | Tổng overdue và tổng debt | `safe_divide(AMT_CREDIT_SUM_OVERDUE_SUM, AMT_CREDIT_SUM_DEBT_SUM)` | Mẫu số 0 hoặc missing → NaN | amounts |

### Block `previous_application`

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `PREV_RECENT_REFUSAL_COUNT` | `NAME_CONTRACT_STATUS`, `DAYS_DECISION` | Đếm đơn bị từ chối trong 365 ngày gần nhất | Fill 0 | counts |
| `PREV_AMT_APPLICATION_TREND` | `AMT_APPLICATION`, `DAYS_DECISION` | Hệ số góc OLS trên 5 đơn gần nhất, sắp xếp cũ trước; dương là xin vay ngày càng nhiều | NaN nếu dưới hai đơn | amounts |
| `PREV_CONTRACT_Cash loans_COUNT` | `NAME_CONTRACT_TYPE` | Đếm đơn có `NAME_CONTRACT_TYPE` bằng `Cash loans`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_CONTRACT_Consumer loans_COUNT` | `NAME_CONTRACT_TYPE` | Đếm đơn có `NAME_CONTRACT_TYPE` bằng `Consumer loans`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_CONTRACT_Revolving loans_COUNT` | `NAME_CONTRACT_TYPE` | Đếm đơn có `NAME_CONTRACT_TYPE` bằng `Revolving loans`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_CONTRACT_XNA_COUNT` | `NAME_CONTRACT_TYPE` | Đếm đơn có `NAME_CONTRACT_TYPE` bằng `XNA`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_CONTRACT_OTHER_COUNT` | `NAME_CONTRACT_TYPE` | Đếm đơn có `NAME_CONTRACT_TYPE` bằng `OTHER`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_YIELD_low_action_COUNT` | `NAME_YIELD_GROUP` | Đếm đơn có `NAME_YIELD_GROUP` bằng `low_action`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_YIELD_low_normal_COUNT` | `NAME_YIELD_GROUP` | Đếm đơn có `NAME_YIELD_GROUP` bằng `low_normal`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_YIELD_middle_COUNT` | `NAME_YIELD_GROUP` | Đếm đơn có `NAME_YIELD_GROUP` bằng `middle`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_YIELD_high_COUNT` | `NAME_YIELD_GROUP` | Đếm đơn có `NAME_YIELD_GROUP` bằng `high`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_YIELD_XNA_COUNT` | `NAME_YIELD_GROUP` | Đếm đơn có `NAME_YIELD_GROUP` bằng `XNA`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_YIELD_OTHER_COUNT` | `NAME_YIELD_GROUP` | Đếm đơn có `NAME_YIELD_GROUP` bằng `OTHER`; ngoài danh sách gom vào `OTHER` | Fill 0 | counts |
| `PREV_HAS_RECENT_REFUSAL` | Count phía trên | `RECENT_REFUSAL_COUNT > 0` | Không có missing | counts |

### Block `installments`

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `INST_LOANS_WITH_LATE_COUNT` | `IS_LATE` qua `SK_ID_PREV` | Đếm khoản vay có ít nhất một kỳ trả trễ | Fill 0 | counts |
| `INST_LATE_RATE_LIFETIME` | `IS_LATE`, `NUM_INSTALMENT_NUMBER` | `safe_divide(LATE_LIFETIME_SUM, COUNT_LIFETIME_COUNT)` | Mẫu số 0 hoặc missing → NaN | delinquency |
| `INST_DPD_60D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `DPD` trong cửa sổ 60 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_DPD_60D_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MAX` của `DPD` trong cửa sổ 60 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_LATE_60D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `LATE` trong cửa sổ 60 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_PAYMENT_RATIO_60D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `PAYMENT_RATIO` trong cửa sổ 60 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_UNDERPAYMENT_60D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `UNDERPAYMENT` trong cửa sổ 60 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_60D_COUNT` | `NUM_INSTALMENT_NUMBER` | Số kỳ trả trong cửa sổ 60 ngày gần nhất | Fill 0 | counts |
| `INST_LATE_RATE_60D` | `IS_LATE`, `NUM_INSTALMENT_NUMBER` | `safe_divide` số kỳ trễ trên số kỳ, trong cửa sổ 60 ngày gần nhất | Mẫu số 0 hoặc missing → NaN | delinquency |
| `INST_DPD_RECENT_MINUS_LIFE_60D` | `DPD` | DPD trung bình 60 ngày gần nhất trừ DPD trung bình toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_LATE_RATE_RECENT_MINUS_LIFE_60D` | `IS_LATE` | Tỷ lệ trễ 60 ngày gần nhất trừ tỷ lệ trễ toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_DPD_90D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `DPD` trong cửa sổ 90 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_DPD_90D_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MAX` của `DPD` trong cửa sổ 90 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_LATE_90D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `LATE` trong cửa sổ 90 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_PAYMENT_RATIO_90D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `PAYMENT_RATIO` trong cửa sổ 90 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_UNDERPAYMENT_90D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `UNDERPAYMENT` trong cửa sổ 90 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_90D_COUNT` | `NUM_INSTALMENT_NUMBER` | Số kỳ trả trong cửa sổ 90 ngày gần nhất | Fill 0 | counts |
| `INST_LATE_RATE_90D` | `IS_LATE`, `NUM_INSTALMENT_NUMBER` | `safe_divide` số kỳ trễ trên số kỳ, trong cửa sổ 90 ngày gần nhất | Mẫu số 0 hoặc missing → NaN | delinquency |
| `INST_DPD_RECENT_MINUS_LIFE_90D` | `DPD` | DPD trung bình 90 ngày gần nhất trừ DPD trung bình toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_LATE_RATE_RECENT_MINUS_LIFE_90D` | `IS_LATE` | Tỷ lệ trễ 90 ngày gần nhất trừ tỷ lệ trễ toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_DPD_180D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `DPD` trong cửa sổ 180 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_DPD_180D_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MAX` của `DPD` trong cửa sổ 180 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_LATE_180D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `LATE` trong cửa sổ 180 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_PAYMENT_RATIO_180D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `PAYMENT_RATIO` trong cửa sổ 180 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_UNDERPAYMENT_180D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `UNDERPAYMENT` trong cửa sổ 180 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_180D_COUNT` | `NUM_INSTALMENT_NUMBER` | Số kỳ trả trong cửa sổ 180 ngày gần nhất | Fill 0 | counts |
| `INST_LATE_RATE_180D` | `IS_LATE`, `NUM_INSTALMENT_NUMBER` | `safe_divide` số kỳ trễ trên số kỳ, trong cửa sổ 180 ngày gần nhất | Mẫu số 0 hoặc missing → NaN | delinquency |
| `INST_DPD_RECENT_MINUS_LIFE_180D` | `DPD` | DPD trung bình 180 ngày gần nhất trừ DPD trung bình toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_LATE_RATE_RECENT_MINUS_LIFE_180D` | `IS_LATE` | Tỷ lệ trễ 180 ngày gần nhất trừ tỷ lệ trễ toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_DPD_365D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `DPD` trong cửa sổ 365 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_DPD_365D_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MAX` của `DPD` trong cửa sổ 365 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_LATE_365D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `LATE` trong cửa sổ 365 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | delinquency |
| `INST_PAYMENT_RATIO_365D_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `MEAN` của `PAYMENT_RATIO` trong cửa sổ 365 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_UNDERPAYMENT_365D_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT` | Thống kê `SUM` của `UNDERPAYMENT` trong cửa sổ 365 ngày gần nhất | Fill 0 với SUM chỉ báo; còn lại NaN | amounts |
| `INST_365D_COUNT` | `NUM_INSTALMENT_NUMBER` | Số kỳ trả trong cửa sổ 365 ngày gần nhất | Fill 0 | counts |
| `INST_LATE_RATE_365D` | `IS_LATE`, `NUM_INSTALMENT_NUMBER` | `safe_divide` số kỳ trễ trên số kỳ, trong cửa sổ 365 ngày gần nhất | Mẫu số 0 hoặc missing → NaN | delinquency |
| `INST_DPD_RECENT_MINUS_LIFE_365D` | `DPD` | DPD trung bình 365 ngày gần nhất trừ DPD trung bình toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_LATE_RATE_RECENT_MINUS_LIFE_365D` | `IS_LATE` | Tỷ lệ trễ 365 ngày gần nhất trừ tỷ lệ trễ toàn bộ; dương là xấu đi | NaN nếu thiếu một trong hai vế | delinquency |
| `INST_LAST1_DPD_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MEAN` của `DPD` trên 1 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST1_DPD_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MAX` của `DPD` trên 1 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST1_PAYMENT_RATIO_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MEAN` của `PAYMENT_RATIO` trên 1 kỳ trả gần nhất | NaN nếu không có kỳ nào | amounts |
| `INST_LAST1_LATE_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `SUM` của `LATE` trên 1 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST3_DPD_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MEAN` của `DPD` trên 3 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST3_DPD_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MAX` của `DPD` trên 3 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST3_PAYMENT_RATIO_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MEAN` của `PAYMENT_RATIO` trên 3 kỳ trả gần nhất | NaN nếu không có kỳ nào | amounts |
| `INST_LAST3_LATE_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `SUM` của `LATE` trên 3 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST5_DPD_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MEAN` của `DPD` trên 5 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST5_DPD_MAX` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MAX` của `DPD` trên 5 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_LAST5_PAYMENT_RATIO_MEAN` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `MEAN` của `PAYMENT_RATIO` trên 5 kỳ trả gần nhất | NaN nếu không có kỳ nào | amounts |
| `INST_LAST5_LATE_SUM` | `DPD`, `PAYMENT_RATIO`, `IS_LATE` | Thống kê `SUM` của `LATE` trên 5 kỳ trả gần nhất | NaN nếu không có kỳ nào | delinquency |
| `INST_DPD_TREND_SLOPE` | `{0}` | Hệ số góc OLS trên 20 kỳ gần nhất, sắp xếp cũ trước; dương nghĩa là tăng dần theo thời gian | NaN nếu dưới hai quan sát | delinquency |
| `INST_PAYMENT_RATIO_TREND_SLOPE` | `{0}` | Hệ số góc OLS trên 20 kỳ gần nhất, sắp xếp cũ trước; dương nghĩa là tăng dần theo thời gian | NaN nếu dưới hai quan sát | amounts |
| `INST_DAYS_SINCE_LAST_LATE` | `DAYS_INSTALMENT`, `IS_LATE` | `-MAX(DAYS_INSTALMENT)` trên các kỳ trả trễ | NaN nếu chưa từng trả trễ | recency |

### Block `credit_card`

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `CC_PORTFOLIO_BALANCE` | `AMT_BALANCE`, `AMT_CREDIT_LIMIT_ACTUAL` | `sum(min_count=1)` trên snapshot cuối của mỗi thẻ | NaN nếu không có giá trị quan sát được | amounts |
| `CC_PORTFOLIO_LIMIT` | `AMT_BALANCE`, `AMT_CREDIT_LIMIT_ACTUAL` | `sum(min_count=1)` trên snapshot cuối của mỗi thẻ | NaN nếu không có giá trị quan sát được | amounts |
| `CC_PORTFOLIO_UTILIZATION` | Hai cột portfolio phía trên | `safe_divide(PORTFOLIO_BALANCE, PORTFOLIO_LIMIT)`; ratio của tổng, không phải trung bình của ratio | Mẫu số 0 hoặc missing → NaN | amounts |

### Block `pos_cash`

| Feature | Cột nguồn | Công thức | Missing policy | Family |
|---|---|---|---|---|
| `POS_CONTRACTS_WITH_DPD_COUNT` | `SK_DPD` qua `SK_ID_PREV` | Đếm hợp đồng có ít nhất một tháng DPD | Fill 0 | counts |
| `POS_COMPLETION_RATE` | Hai count hợp đồng | `safe_divide(COMPLETED_SUM, CONTRACT_COUNT)` | Mẫu số 0 hoặc missing → NaN | counts |
| `POS_DPD_CONTRACT_RATIO` | Hai count hợp đồng | `safe_divide(CONTRACTS_WITH_DPD_COUNT, CONTRACT_COUNT)` | Mẫu số 0 hoặc missing → NaN | delinquency |

## Ví dụ trong credit scoring

`BUREAU_AMT_CREDIT_SUM_DEBT_SUM` dùng `SUM_OBSERVED`. Trong 5.000 khách lấy
mẫu có 157 khách mà mọi bản ghi Bureau đều không ghi dư nợ; họ giữ `NaN` ở cả
`SUM`, `MEAN` và `MAX`. Nếu `SUM` trả `0` thì cùng một khách sẽ vừa "nợ bằng
0" theo cột tổng vừa "không rõ" theo cột trung bình, và model học được một
quan hệ do lỗi tạo ra chứ không có thật.

## Điều cần kiểm tra trong project

- [x] Mỗi feature có cột nguồn, công thức, missing policy và family.
- [x] Schema không đổi giữa mẫu nhỏ và full data, có test bảo vệ.
- [x] Cardinality `SK_ID_CURR` duy nhất sau mỗi builder, có test bảo vệ.
- [x] Tên feature không chứa ký tự LightGBM từ chối.
- [ ] Chạy paired ablation trước khi kết luận feature nào đáng giữ.
- [ ] Promote lên production cần review riêng và owner.

## Tài liệu liên quan

- [Feature store](feature_store.md)
- [Home Credit Bureau features](home_credit_bureau_features.md)
- [Feature engineering](feature_engineering.md)
- [ADR-0004](../decisions/0004-auxiliary-feature-modules-in-source.md)

## Trạng thái áp dụng trong project

Research candidate. Đã build trên full data thành năm block Parquet; chưa có
paired ablation nên chưa feature nào được chọn hay loại. Không thuộc E03.
