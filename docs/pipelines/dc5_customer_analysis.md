# Pipeline phân tích khách hàng DC5

## Mục tiêu

Chuyển luồng nghiên cứu trong `DA.ipynb`, `modeling.ipynb` và `1808.ipynb`
thành pipeline có test, chạy bằng một lệnh hoặc một cell, tạo artifact tổng hợp và
giao diện local. Target hiện tại là nhóm Telco monetary cao; đây là research
candidate, không phải target default hoặc mô hình credit-risk production.

## Khái niệm chính

Luồng triển khai:

```text
model_df_extracted.parquet
  → kiểm tra schema/cardinality
  → lọc population và tạo target
  → M0/M1/M2/M3/M4 trên cùng StratifiedKFold
  → ROC-AUC, PR-AUC, fold metrics, feature importance
  → report.html + CSV aggregate
  → Admin Streamlit UI → report.html
  → Customer Streamlit UI (profile intake)
```

UI cũng có phần `Simulation hồ sơ khách hàng` cho giai đoạn 1. Phần này nhận
tuổi, thu nhập, nghề nghiệp, thâm niên, loại nhà ở, người phụ thuộc, số dịch vụ
và CIC tùy chọn; kết quả hiện là `demo profile index` minh họa, không phải CIC
score/credit score và không dùng để quyết định cho vay. CIC chỉ được nối vào
model sau khi có nhãn tín dụng, nguồn dữ liệu và phê duyệt từ data/risk owner.
Người dùng có thể đính kèm CCCD hoặc tài liệu thu nhập để thử luồng giao diện;
file chỉ tồn tại trong phiên Streamlit, chưa OCR/chưa lưu và không được đưa vào
model ở giai đoạn này. Không dùng CCCD thật trong môi trường demo.

Logic dùng lại nằm trong `src/credit_scoring/dc5/`. Notebook
`notebooks/04_dc5_pipeline/01_run_dc5_pipeline.ipynb` chỉ chạy synthetic
assertion rồi gọi pipeline. Artifact nằm dưới `artifacts/` và không commit.

Hai chế độ chính:

- `quick`: M0/M1/M4, tối đa 3 folds để kiểm tra nhanh.
- `full`: M0-M4, số fold lấy từ config (mặc định 5), kèm KMeans/PCA nếu bật.
- `report-only`: mở artifact gần nhất, không đọc dữ liệu hoặc train lại.

Fingerprint gồm đường dẫn/kích thước/mtime của Parquet, config và pipeline
version. Khi fingerprint không đổi, pipeline dùng lại run đã có.

## Hai giao diện

- **Admin UI:** `python -m streamlit run src/credit_scoring/dc5/admin_ui.py` —
  dành cho data team, chạy training, xem importance và tải report.
- **Customer UI:** `python -m streamlit run src/credit_scoring/dc5/customer_ui.py
  --server.port 8502` — chỉ nhập hồ sơ và tài liệu tùy chọn; CIC hiện là
  `CHƯA TÍNH`.

## Ví dụ trong credit scoring

Cài môi trường và chạy CLI:

```bash
python -m pip install -e ".[dev,dc5,ui]"
dc5-pipeline --config configs/dc5_customer_analysis.yaml
dc5-ui
```

Hoặc chạy một cell:

```python
from credit_scoring.dc5 import run_pipeline, smoke_check

smoke_check()
run = run_pipeline(config_path="configs/dc5_customer_analysis.yaml")
run.display()
```

Output gồm `report.html`, `metrics.csv`, `fold_metrics.csv`,
`feature_importance.csv`, EDA aggregate, cluster profile khi bật và
`run_metadata.json`. Các biểu đồ được nhúng vào HTML để file báo cáo xem được
độc lập. Báo cáo không chứa `user_id`.

## Điều cần kiểm tra trong project

- [ ] Đặt `model_df_extracted.parquet` ngoài git và cập nhật `data_path`.
- [ ] Xác nhận schema, target và observation point với mentor/data owner.
- [ ] Chạy `quick` trước; không dùng metric quick để tuyên bố cải thiện.
- [ ] Chạy `full` và kiểm tra artifact trước khi ghi experiment log.
- [ ] Không đưa credential, PII hoặc dữ liệu cấp khách hàng vào UI/report.
- [ ] Chỉ mô tả model/feature là production sau một review promotion riêng.

## Tài liệu liên quan

- [FPT dataset template](../datasets/fpt_dataset_template.md)
- [DC5 validation decision](../decisions/0005-dc5-pipeline-validation.md)
- [Classification metrics](../evaluation/classification_metrics.md)
- [Experiment log](../experiments/experiment_log.md)

## Trạng thái áp dụng trong project

Pipeline, CLI, notebook một-cell và UI local đã được triển khai với test synthetic.
Chưa có run thật trong workspace vì prepared Parquet không được lưu trong git;
không có metric mới được ghi nhận. TODO(FPT): cần xác nhận với mentor hoặc data owner.
