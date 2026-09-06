# DC5 synthetic demo dataset

## Mục tiêu

Bộ dữ liệu giả lập để thử giao diện và pipeline DC5 mà không cần truy cập dữ liệu khách hàng thật.

## Khái niệm chính

Đây là dữ liệu synthetic có schema cố định và seed tái lập. Các quan hệ thống kê được dựng để
kiểm thử luồng phần mềm, không đại diện cho khách hàng hoặc quy luật tín dụng thực tế.

## Nguồn và phạm vi

- Schema tham chiếu: workbook `DC5xQACI- DMDL KH FPT_20260805 (2).xlsx` do người dùng cung cấp.
- Dữ liệu: sinh hoàn toàn bằng code với seed cố định; không sao chép bản ghi, PII hoặc credential.
- Grain: một dòng cho một khách hàng synthetic.
- Quy mô mặc định: 100.000 dòng.
- Target demo: `telco_monetary_group_ord == 4`, chỉ phục vụ nghiên cứu/minh họa.

## File đầu ra

- `data_extracted/model_df_extracted.parquet`: đầy đủ cột để pipeline/UI đọc nhanh.
- `artifacts/dc5_demo_100k.xlsx`: 23 cột theo sheet mẫu để kiểm tra bằng Excel.

Hai file được tạo cục bộ và không được commit vào Git.

## Cách tái tạo

```powershell
python scripts/generate_dc5_demo_data.py --rows 100000 --seed 20260805
```

## Giới hạn

Các quan hệ thống kê được dựng để tạo kết quả demo có thể diễn giải. Metric, phân phối và feature
importance từ bộ này không phản ánh hiệu quả trên dữ liệu FPT thật và không được dùng cho quyết định
kinh doanh hoặc tín dụng.

## Ví dụ trong credit scoring

Dùng bộ dữ liệu để kiểm tra việc đọc Parquet, chia fold, huấn luyện M0-M4, tạo feature importance
và hiển thị báo cáo; không dùng metric demo để chọn chính sách tín dụng.

## Điều cần kiểm tra trong project

- [ ] Không commit Parquet, Excel sinh ra hoặc dữ liệu khách hàng thật.
- [ ] Giữ seed và schema ổn định khi kiểm thử hồi quy.
- [ ] Gắn nhãn rõ mọi metric là synthetic/demo.

## Tài liệu liên quan

- [Dataset catalog](dataset_catalog.md)
- [DC5 customer analysis pipeline](../pipelines/dc5_customer_analysis.md)
- [DC5 validation decision](../decisions/0005-dc5-pipeline-validation.md)

## Trạng thái áp dụng trong project

Được dùng cho demo local và kiểm thử pipeline; không phải dataset production.
