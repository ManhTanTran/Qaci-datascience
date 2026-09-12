# Alternative-data reasoning feature registry

## Phạm vi

Registry này mô tả 31 field được đưa vào `Prompt_View` của workbook synthetic.
`scenario` và `user_id` chỉ là định danh fixture, không phải feature reasoning.
Các cột còn lại trong workbook 115 cột hiện chưa thuộc registry v1.

Đây là research candidate registry cho evaluation. Chưa có feature nào được
promote thành feature production.

## Nguyên tắc

- Missing là unknown, không phải bằng chứng tiêu cực.
- Engagement, consumption và regional context không tự chứng minh khả năng trả nợ.
- Payment features chỉ được gọi là bằng chứng tín dụng trực tiếp sau khi xác nhận
  loại nghĩa vụ, mẫu số, event definition và observation window.
- Healthcare fields không được dùng để suy luận bệnh lý hoặc creditworthiness.
- `city`, `gender` và age group không dùng làm bằng chứng cá nhân trong baseline.

| Feature | Domain | Evidence type | Source column | Formula/aggregation | Missing policy | Limitation |
|---|---|---|---|---|---|---|
| `age_group` | demographic | demographic context | `age_group` | Source value | Unknown | Fairness/coverage context only |
| `gender` | demographic | sensitive context | `gender` | Source value | Unknown | Không dùng cho individual reasoning |
| `city` | regional context | regional context | `city` | Source value | Unknown | Không suy luận giàu/nghèo cá nhân |
| `income_band_est` | capacity | capacity proxy | `income_band_est` | Source bucket | Unknown | Không phải thu nhập xác minh |
| `active_domain_count` | engagement | engagement proxy | `active_domain_count` | Source bucket | Unknown | Không phải repayment evidence |
| `tenure_group` | engagement | engagement proxy | `tenure_group` | Source bucket | Unknown | Tenure dài không tự chứng minh ổn định |
| `recency_group` | engagement | recency proxy | `recency_group` | Source bucket | Unknown | Giảm hoạt động có nhiều cách giải thích |
| `app_count_group` | engagement | engagement proxy | `app_count_group` | Source bucket | Unknown | Không phải repayment evidence |
| `app_tenure_group` | engagement | engagement proxy | `app_tenure_group` | Source bucket | Unknown | Không phải repayment evidence |
| `app_recency_days` | engagement | recency proxy | `app_recency_days` | Source bucket | Unknown | Chưa rõ cutoff và định nghĩa |
| `loyalty_points` | loyalty | engagement proxy | `loyalty_points` | Source bucket | Unknown | Không phải repayment evidence |
| `loyalty_tier` | loyalty | engagement proxy | `loyalty_tier` | Source bucket | Unknown | Không phải repayment evidence |
| `telco_contract_status` | payment | service-status proxy | `telco_contract_status` | Source value | Unknown | Không phải formal credit outcome |
| `telco_internet_usage_group` | engagement | usage proxy | `telco_internet_usage_group` | Source bucket | Unknown | Usage cao không đồng nghĩa khả năng trả nợ |
| `telco_internet_trend_group` | engagement | trend proxy | `telco_internet_trend_group` | Source bucket | Unknown | Trend giảm không tự là deterioration |
| `telco_monetary_group` | consumption | spending proxy | `telco_monetary_group` | Source bucket | Unknown | Spending không đồng nghĩa repayment capacity |
| `healthcare_last_order_date` | healthcare | sensitive proxy | `healthcare_last_order_date` | Source bucket | Unknown | Không suy luận bệnh lý/credit |
| `healthcare_order_count_6m` | healthcare | sensitive proxy | `healthcare_order_count_6m` | Source bucket | Unknown | Không suy luận bệnh lý/credit |
| `healthcare_spend_6m` | healthcare | sensitive proxy | `healthcare_spend_6m` | Source bucket | Unknown | Không suy luận bệnh lý/credit |
| `healthcare_aov_6m` | healthcare | sensitive proxy | `healthcare_aov_6m` | Source bucket | Unknown | Không suy luận bệnh lý/credit |
| `healthcare_repeat_purchase_rate_6m` | healthcare | sensitive proxy | `healthcare_repeat_purchase_rate_6m` | Source bucket | Unknown | Không suy luận bệnh lý/credit |
| `occupation` | employment | employment context | `occupation` | Source value | Unknown | Không tự xác nhận thu nhập ổn định |
| `employment_status` | employment | employment context | `employment_status` | Source value | Unknown | Cần semantics và verify income |
| `monthly_income` | capacity | self-reported capacity | `monthly_income` | Source value | Unknown, không fill zero | Unit VND/month cần xác nhận |
| `monthly_expense` | capacity | self-reported capacity | `monthly_expense` | Source value | Unknown, không fill zero | Có thể thiếu các nghĩa vụ khác |
| `payment_on_time_rate_12m` | payment | payment behavior | `payment_on_time_rate_12m` | On-time / observed payments | Giữ uncertainty về denominator | Chưa rõ payment type |
| `overdue_days_max_12m` | payment | payment behavior | `overdue_days_max_12m` | Maximum observed overdue days | Zero chỉ khi verified | Không tự là default |
| `payment_failure_count_12m` | payment | payment behavior | `payment_failure_count_12m` | Count failed payments | Zero chỉ khi verified | Có thể gồm technical failure |
| `online_purchase_frequency` | shopping | consumption proxy | `online_purchase_frequency` | Source bucket | Unknown | Frequency không có order value |
| `purchase_category_distribution` | shopping | consumption proxy | `purchase_category_distribution` | Source description | Unknown | Không phải quan hệ nhân quả |
| `recent_purchase_trend` | shopping | trend proxy | `recent_purchase_trend` | Source bucket | Unknown | Tăng/giảm có nhiều cách giải thích |

Machine-readable source: `configs/reasoning/feature_definitions.yaml`.

## Mục tiêu

Đăng ký rõ lineage, missing policy và giới hạn diễn giải của các field
alternative-data trước khi chúng được dùng trong evaluation reasoning.

## Khái niệm chính

Registry phân biệt evidence type với feature source: engagement, consumption và
regional context không tự trở thành bằng chứng về khả năng trả nợ. Missing được
giữ là unknown và mọi field hiện vẫn là research candidate.

## Ví dụ trong credit scoring

`payment_on_time_rate_12m` chỉ có thể được xem là payment behavior sau khi xác
nhận payment type, denominator và observation window; `healthcare_spend_6m`
không được dùng để suy luận bệnh lý hoặc creditworthiness.

## Điều cần kiểm tra trong project

- Xác nhận owner, đơn vị đo, cutoff và denominator của từng field trước khi
  đưa vào prompt hoặc model.
- Kiểm tra schema registry khớp với YAML machine-readable và không đưa PII vào
  prompt, log hay artifact.
- Không promote feature hoặc biến candidate rule thành production policy khi
  chưa có review riêng.

## Tài liệu liên quan

- Machine-readable feature definitions: `configs/reasoning/feature_definitions.yaml`
- [Alternative-data rule knowledge base](alternative_data_rule_knowledge_base.md)

## Trạng thái áp dụng trong project

Registry v1 chỉ phục vụ synthetic evaluation và Agent Harness research. Chưa có
field nào là feature production.
