# FPT Credit Reasoning PoC pipeline

## Mục tiêu

Chạy một pipeline có thể truy vết từ raw Excel/CSV đến profile, deterministic rule
result và tùy chọn AI explanation cho research PoC.

## Khái niệm chính

```text
Raw input → inspect → validate → mapping/transform → profile/evidence → rules → AI explanation
```

Rule engine là source of truth cho `PASS`, `FAIL`, `UNKNOWN`. AI không được override
decision, không phát hành `loan_approved`/`loan_rejected`, và phải đánh dấu conflict.

## Ví dụ trong credit scoring

```powershell
python -m credit_scoring.research.fpt_reasoning_poc.pipeline
python -m credit_scoring.research.fpt_reasoning_poc.run_experiment `
  --input data/processed/research/fpt_reasoning_poc/cases.jsonl `
  --output outputs/research/fpt_reasoning_poc/experiment_results.jsonl `
  --model openai/gpt-4o-mini --repeats 1
```

Không chạy lệnh LLM nếu chưa cấu hình secret qua `OPENROUTER_API_KEY` trong
environment. Pipeline dữ liệu không cần API key.

## Điều cần kiểm tra trong project

- [ ] `Synthetic_Customers` được chọn thay vì `Prompt_View`.
- [ ] Missing/invalid giữ riêng và warning unit vẫn được hiển thị.
- [ ] Age range giao ngưỡng 23 trả về `UNKNOWN`; trạng thái age > 23 vẫn là research condition.
- [ ] Chỉ chạy experiment với `repeat_count` đã cấu hình và lưu `run_id` duy nhất.

## Tài liệu liên quan

- [Synthetic dataset card](../datasets/fpt_credit_reasoning_poc.md)
- [Feature groups](../features/fpt_reasoning_poc_features.md)
- [Experiment log](../experiments/experiment_log.md)

## Trạng thái áp dụng trong project

Đây là research PoC. Application gọi shared data pipeline; research layer chỉ thêm
scenario/ablation/repeated-run/evaluation. Không có claim production readiness.
