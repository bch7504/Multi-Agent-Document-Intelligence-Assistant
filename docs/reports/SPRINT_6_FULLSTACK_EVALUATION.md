# Sprint 6 - Full-stack, Evaluation và Observability

## Kết quả

Sprint 6 hoàn thiện bản demo portfolio chạy được end-to-end:

- React/TypeScript production frontend tách biệt hoàn toàn với `mock.html`;
- model selector thật cho OpenRouter/OpenAI/Gemini/Ollama, custom model ID và
  provider availability không làm lộ API key;
- upload PDF, list/select nhiều document, Ask/Summarize/Quiz;
- import idempotent pre-chunked JSON dataset vào PostgreSQL + Milvus production;
- render citation, quiz explanation, reviewer/retry và Agent Trace;
- Nginx phục vụ SPA và reverse proxy `/api/v1` đến FastAPI;
- structured JSON request/run logs với `X-Request-ID`;
- token usage được thu bằng callback LangChain và lưu trong `assistant_runs`;
- audit endpoint `GET /api/v1/assistant/runs/{run_id}`;
- RAGAS 0.4.3 chạy trong Docker profile riêng;
- CI build/test backend và strict TypeScript production build.

## RAGAS baseline v1

Dataset: `stack_ai_ragas_v1.json`, 3 gold-reference cases trên collection `data_test`.

| Metric | Score |
|---|---:|
| Faithfulness | 0.9693 |
| Answer relevancy | 0.9158 |
| Factual correctness (F1) | 0.4867 |
| LLM context precision without reference | 0.7455 |

Kết quả đầy đủ và cấu hình/version/hash dataset nằm tại
`docs/reports/evaluation/ragas_stack_ai_v1.json`.

Factual correctness thấp hơn các metric còn lại vì answer thường mở rộng nhiều
capability grounded hơn gold reference. Gold reference đã được bổ sung từ corpus,
nhưng bộ 3 case vẫn chỉ là smoke baseline; cần tăng số case trước khi dùng làm
quality gate production.

Chạy lại toàn bộ dataset:

```bash
docker compose --profile evaluation run --rm evaluation
```

Chạy nhanh một case:

```bash
docker compose --profile evaluation run --rm evaluation \
  python -m backend.app.evaluation.run_ragas --max-cases 1
```

Evaluator được tách khỏi API image vì RAGAS kéo theo `datasets`, `pyarrow` và
`scipy`. Tokenizer `cl100k_base` được bake vào image để retrieval không phụ thuộc
download tokenizer lúc runtime.

## Observability

Mỗi request có request ID trả qua response header và log JSON. Mỗi assistant run
ghi task, status, retry, số document/citation, latency và token usage. Trace chi tiết,
citations và quiz được lưu trong PostgreSQL để đọc lại qua audit endpoint.

Đây là tracing backend tương đương tối thiểu cho MVP, không yêu cầu gửi dữ liệu tới
Langfuse SaaS. Có thể thêm OpenTelemetry/Langfuse exporter sau mà không thay đổi API.

## Kiểm chứng

- Frontend strict build: PASS.
- Backend: 91 tests PASS, 1 optional local-corpus test SKIP.
- Alembic: `20260917_0003 (head)`.
- UI: HTTP 200 tại `http://localhost:3000`.
- Nginx proxy → API readiness: `ready`.
- Live OpenRouter QA: reviewer PASS, 3 citations, 7 trace steps và 5,785 tokens
  được ghi nhận (5,387 input, 398 output).
- Full RAGAS 3-case run: PASS, report đã lưu.
