# Real-estate price pipeline

Hai module nối nhau qua một file JSONL, dùng chung một UI (cổng 8768):

```
Module 1  module1_crawler/   Tavily tìm web + model tóm tắt ──► data/llm_answers.jsonl (append-only)
Module 2  module2_extractor/ LLM trích claim giá → hậu kiểm bằng code ──► data/claims.db
Runner + UI  pipeline/       đọc file hand-off, hàng chờ/retry, giám sát chất lượng, token & chi phí
```

## Cài đặt (một lần)

Yêu cầu Python ≥ 3.11.

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -3 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env                                   # điền key (xem bên dưới)
```

| Cấu hình                                                                                        | Nơi đặt                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API key, base URL                                                                                 | `.env` — `TAVILY_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` (module 1); `EXTRACTOR_API_KEY`, `EXTRACTOR_BASE_URL` (module 2, bỏ trống = dùng lại `OPENAI_*`) |
| Chế độ `manual`/`auto`, batch, retry, model trích xuất, ngưỡng chất lượng, cổng UI | `config.yaml`                                                                                                                                                                                      |
| Giá để tính chi phí (token, Tavily)                                                          | `config.yaml → cost` (để trống thì UI chỉ hiện token)                                                                                                                                       |

## Chạy

**UI chung** — `python -m pipeline ui` → http://127.0.0.1:8768

- `/` là Module 1 (chuẩn bị job, chạy lượt tìm kiếm, tiến độ, token/chi phí).
- `/extract-claims` là Module 2 (quét file, chạy trích xuất, chất lượng, answers, claims, token/chi phí, lỗi đầu vào, lịch sử chạy). API: `/api/v1/research-answers/*` và `/api/v1/extract-claims/*`.

**Module 1 — thu thập** (`module1_crawler/`)

```bash
python -m wardprice.research_answers prepare --period 2026-10 [--province "Hà Nội"] [--code 00001]
python -m wardprice.research_answers run --period 2026-10 --limit 5 [--batches N] [--retry-failed]
python -m wardprice.research_answers status --period 2026-10
```

Mỗi lượt chạy tự nối các dòng mới vào `data/llm_answers.jsonl` (không trùng). Bản chụp từng kỳ và DB job nằm ở `data/module1/`. Đổi file đích bằng `LLM_ANSWERS_FILE` hoặc `config.yaml → input_file`.

**Module 2 — trích xuất** (`module2_extractor/`)

```bash
python -m pipeline run-once --limit 5      # quét file + xử lý (nên thử 5 answer trước)
python -m pipeline watch                   # chế độ auto, chạy liên tục
python -m pipeline status | reprocess ... | export --format csv
```

Kết quả: `data/claims.db`; xuất CSV vào `data/exports/`.

## Hợp đồng `data/llm_answers.jsonl`

Mỗi dòng một object: `crawled_at`, `chatbot`, `answer_text` (bắt buộc); `answer_id`, `crawl_run_id`, `target_month` (YYYY-MM), `model_name`, `query_text`. Module 2 chỉ đọc dòng đã kết thúc bằng xuống dòng; dòng hỏng vào bảng `input_errors`.

## Kiểm thử

```bash
pytest            # toàn repo: module 1, module 2, runner, UI, end-to-end, volume
```

## Lưu ý

- Test dùng LLM/Tavily giả; hãy chạy thử 5 địa bàn / 5 answer với API thật trước khi chạy lớn.
- UI chỉ bind `127.0.0.1`, không có đăng nhập.
