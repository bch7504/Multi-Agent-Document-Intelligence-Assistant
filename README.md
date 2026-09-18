# Multi-Agent Document Intelligence Assistant

Trợ lý tài liệu full-stack dùng React, FastAPI, LangGraph, PostgreSQL và Milvus.
Người dùng chọn một hoặc nhiều tài liệu, sau đó hỏi đáp, yêu cầu tóm tắt hoặc tạo
quiz có citation. Supervisor có thể tự nhận diện tác vụ khi UI ở chế độ **Auto**.

## Tính năng hiện có

- PDF upload, lifecycle `uploaded -> processing -> ready | failed`, giới hạn 75 MiB.
- Demo corpus được tách thành 5 tài liệu độc lập với tổng cộng 65 chunks.
- Hybrid retrieval bằng dense vector + Milvus native BM25 + RRF.
- Filter `document_id` được áp dụng trước retrieval để không lẫn tài liệu ngoài scope.
- LangGraph điều phối QA, full-document Summary và Quiz.
- `task=auto` dùng Supervisor để chọn `qa`, `summary` hoặc `quiz`.
- Citation được dựng từ chunk đã retrieval và kiểm tra bằng code trước LLM reviewer.
- Reviewer có bounded retry tối đa hai lần; output không grounded sẽ bị chặn.
- Quiz lấy đúng số câu từ prompt; mặc định 5 và tối đa 20 câu.
- Conversation history, assistant run audit, quiz library và quiz attempts trong PostgreSQL.
- Chọn độc lập chat/embedding model từ OpenRouter, OpenAI, Gemini hoặc Ollama.
- **Apply & test** gọi thử model thật trước khi áp dụng, không đưa API key xuống browser.
- Agent Trace, token usage, structured JSON log và request ID.
- RAGAS chạy trong evaluation image riêng.

## Kiến trúc

```text
Browser
  -> Nginx + React/TypeScript
  -> FastAPI
       |-> LangGraph: Supervisor -> QA | Summary | Quiz
       |      -> deterministic validation -> reviewer -> bounded retry
       |-> PostgreSQL: documents, conversations, messages, runs, quizzes
       `-> Milvus: dense vectors + BM25 sparse vectors + provenance
```

PostgreSQL là control plane. Milvus chỉ giữ chunks, vectors và metadata retrieval.
PDF binary được lưu trên local volume trong MVP, không lưu trong database.

## Chạy nhanh bằng Docker

Yêu cầu: Docker Desktop/Docker Compose và API key của ít nhất một provider cloud,
hoặc Ollama đã được chuẩn bị sẵn.

```powershell
Copy-Item .env.example .env
# Điền provider/model/API key cần dùng trong .env
docker compose up -d --build
docker compose ps
```

Mở các địa chỉ:

- Frontend: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/api/v1/health/live>
- Readiness: <http://localhost:8000/api/v1/health/ready>
- Milvus WebUI: <http://localhost:9091/webui/>

Container API tự chạy `alembic upgrade head`; không cần tạo database hoặc bảng thủ công.
Dữ liệu PostgreSQL/Milvus nằm trong `volumes/` và không được commit.

## Cấu hình model

`.env.example` chứa cấu hình cho OpenRouter, OpenAI, Gemini và Ollama. API key chỉ
tồn tại ở backend. UI lấy catalog từ `GET /api/v1/models`, cho phép chọn hoặc nhập
model ID, rồi gọi `POST /api/v1/models/validate` khi người dùng nhấn **Apply & test**.
Cấu hình chỉ được áp dụng nếu cả chat và embedding model dùng được.

Embedding của query phải trùng provider/model đã dùng để index tài liệu. UI cho phép
thử lựa chọn khác nhưng sẽ báo cần re-index nếu knowledge base hiện tại dùng embedding khác.

Ví dụ OpenRouter:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-5.6-luna
EMBEDDING_PROVIDER=openrouter
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Không commit `.env`.

## Dữ liệu demo

Import idempotent dataset [data/stack_ai.json](data/stack_ai.json):

```bash
docker compose exec -T api python -m backend.app.ingestion.import_json \
  /code/data/stack_ai.json --curated-demo
```

Lệnh tạo đúng 5 nguồn độc lập:

| Tài liệu | Chunks |
|---|---:|
| Enterprise Security, Access & Identity | 19 |
| Workflow Builder Fundamentals | 11 |
| Retrieval, Chunking & Embeddings | 10 |
| Knowledge Bases | 19 |
| Human in the Loop | 6 |

`stack_ai.json` là nguồn import/rebuild; UI và retrieval dùng năm document records đã
được tách trong PostgreSQL/Milvus, không dùng file aggregate như một tài liệu thứ sáu.

## Sử dụng frontend

1. Chọn một hoặc nhiều tài liệu `ready` ở sidebar.
2. Giữ **Auto** để Supervisor tự nhận diện yêu cầu, hoặc chọn Ask/Summarize/Quiz thủ công.
3. Gửi prompt và mở citation/Agent Trace để kiểm tra nguồn cùng workflow.
4. Dùng **History** để tải, đổi tên hoặc xóa thread.
5. Dùng **Quizzes** để làm lại quiz, xem điểm tốt nhất và attempt history.
6. Dùng **Models -> Apply & test** trước khi đổi model runtime.

`frontend/mock.html` chỉ là prototype tĩnh, không kết nối backend. Frontend thật nằm
trong [frontend/src](frontend/src).

## Upload PDF

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -F "file=@./example.pdf;type=application/pdf"
```

Giới hạn mặc định là `78643200` bytes (75 MiB). Nginx cho phép 76 MiB để chừa
multipart overhead. UI kiểm tra dung lượng trước khi gửi và hiển thị lỗi xử lý từ backend.

MVP hiện chỉ hỗ trợ PDF có lớp text. PDF scan/ảnh sẽ chuyển sang `failed` với thông báo
`PDF does not contain extractable text`; OCR và background ingestion thuộc V2. Upload,
parse, chunk và embedding vẫn chạy đồng bộ nên tài liệu lớn có thể mất vài phút.

## API chính

```text
GET    /api/v1/models
POST   /api/v1/models/validate

POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}

POST   /api/v1/assistant/runs
GET    /api/v1/assistant/runs/{run_id}

GET    /api/v1/conversations
GET    /api/v1/conversations/{id}/messages
PATCH  /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}

GET    /api/v1/quizzes
GET    /api/v1/quizzes/{id}
POST   /api/v1/quizzes/{id}/attempts
GET    /api/v1/quizzes/{id}/attempts
DELETE /api/v1/quizzes/{id}
```

Ví dụ Auto routing:

```json
{
  "conversationId": "00000000-0000-0000-0000-000000000001",
  "documentIds": ["00000000-0000-0000-0000-000000000002"],
  "task": "auto",
  "message": "Create a 5-question quiz from the selected document"
}
```

## Kiểm thử và evaluation

```bash
python -m unittest discover -s backend/tests -v
python -m compileall -q backend
cd frontend && npm ci && npm run build
```

Retrieval benchmark:

```bash
python -m backend.app.evaluation.run_retrieval --collection data_test --k 5
```

RAGAS:

```bash
docker compose --profile evaluation run --rm evaluation
```

RAGAS smoke baseline hiện lưu tại
[docs/reports/evaluation/ragas_stack_ai_v1.json](docs/reports/evaluation/ragas_stack_ai_v1.json):

| Metric | Score |
|---|---:|
| Faithfulness | 0.9693 |
| Answer relevancy | 0.9158 |
| Factual correctness (F1) | 0.4867 |
| Context precision | 0.7455 |

Bộ RAGAS hiện chỉ có 3 gold-reference cases, phù hợp smoke regression nhưng chưa đủ
làm production quality gate.

## Giới hạn hiện tại

- Single-user local deployment, chưa có authentication/multi-tenant authorization.
- Chưa OCR PDF scan.
- Chưa có background queue cho ingestion tài liệu lớn.
- Memory là recent conversation window; chưa có semantic long-term user profile.
- Quiz có reviewer citation nghiêm ngặt; output sẽ bị chặn nếu model gắn đúng facts nhưng sai excerpt.
- Chưa thêm reranker vì benchmark hiện tại chưa chứng minh lợi ích đủ lớn so với latency/cost.

## Tài liệu

- [Project plan](docs/PROJECT_PLAN.md)
- [UI test plan](docs/UI_TEST_PLAN.md)
- [Demo plan](docs/DEMO_PLAN.md)
- [Sprint 1 retrieval baseline](docs/reports/SPRINT_1_RETRIEVAL_BASELINE.md)
- [Sprint 2 document lifecycle](docs/reports/SPRINT_2_DOCUMENT_LIFECYCLE.md)
- [Sprint 3 retrieval comparison](docs/reports/SPRINT_3_RETRIEVAL_COMPARISON.md)
- [Sprint 4 LangGraph QA/Summary](docs/reports/SPRINT_4_LANGGRAPH_QA_SUMMARY.md)
- [Sprint 5 quiz/review/memory](docs/reports/SPRINT_5_QUIZ_REVIEW_MEMORY.md)
- [Sprint 6 full-stack/evaluation](docs/reports/SPRINT_6_FULLSTACK_EVALUATION.md)
- [Sprint 7 history/quiz library](docs/reports/SPRINT_7_HISTORY_QUIZ_LIBRARY.md)
- [Sprint 8 demo hardening](docs/reports/SPRINT_8_DEMO_HARDENING.md)

## Cấu trúc chính

```text
frontend/                 React/TypeScript production UI và mock độc lập
backend/app/api/          FastAPI routers
backend/app/graph/        LangGraph state, nodes và routes
backend/app/rag/          retrieval profiles và hybrid search
backend/app/ingestion/    PDF/web/JSON ingestion
backend/app/services/     document, assistant, memory và quiz services
backend/alembic/          PostgreSQL migrations
backend/tests/            unit và integration tests
docs/                     plan, demo và sprint reports
docker-compose.yml        frontend, API, PostgreSQL, Milvus và evaluation
```
