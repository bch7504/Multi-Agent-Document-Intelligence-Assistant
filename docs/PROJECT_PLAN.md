# Kế hoạch phát triển Multi-Agent Document Intelligence Assistant

## 1. Mục tiêu

Nâng cấp project RAG LangChain hiện tại thành một hệ thống Document Intelligence có thể:

- nạp tài liệu PDF và website;
- hỏi đáp trên một hoặc nhiều tài liệu với citation đến đúng nguồn/trang;
- tóm tắt theo tài liệu hoặc phạm vi người dùng chọn;
- tạo quiz có cấu trúc và giải thích đáp án;
- điều phối các workflow bằng LangGraph;
- kiểm tra tính grounded và tính hợp lệ của citation trước khi trả kết quả;
- lưu hội thoại, đánh giá chất lượng và quan sát trace của từng lần chạy;
- chạy được bằng Docker Compose và có một demo phù hợp portfolio AI Engineer.

Project được phát triển tăng dần từ baseline đang chạy. Không viết lại toàn bộ code và không tạo nhiều agent trước khi retrieval/citation được đo lường ổn định.

## 2. Hiện trạng

### Đã có

- Static HTML mock để duyệt layout và interaction cơ bản, không kết nối backend.
- Ingestion từ JSON local và website.
- Token-aware recursive chunking, mặc định 500 tokens và overlap 75 tokens.
- OpenRouter, OpenAI, Gemini hoặc Ollama embeddings có thể chọn độc lập với chat model.
- Milvus standalone và cơ chế cập nhật collection qua staging/backup.
- Hybrid retrieval native trong Milvus gồm dense vector, BM25 và RRF.
- LangChain agent có retrieval tool.
- LangGraph QA, map-reduce Summary và Quiz dùng chung deterministic validator.
- Grounding reviewer với retry về retrieval/generation, tối đa hai lần.
- PostgreSQL recent-window memory và assistant run audit.
- Conversation History, Quiz Library, quiz attempts và quản lý thread.
- Gemini, OpenRouter, OpenAI và Ollama chat providers.
- React/TypeScript production frontend, Nginx reverse proxy và Docker Compose full stack.
- Model catalog cùng thao tác **Apply & test** gọi thử chat/embedding model thật từ backend.
- Retrieval benchmark, RAGAS smoke evaluation, structured logs, request ID và Agent Trace.
- Curated demo corpus gồm 5 tài liệu độc lập, tổng 65 chunks.
- Unit/integration tests không yêu cầu dịch vụ bên ngoài cho phần lớn test suite.

### Chưa có

- OCR cho PDF scan/ảnh.
- Background queue cho ingestion tài liệu lớn; MVP hiện xử lý đồng bộ.
- Authentication, multi-tenant authorization và retention policy theo người dùng.
- Semantic long-term user memory/profile.
- Object storage production và distributed tracing exporter.

### Hạn chế cần xử lý

- Benchmark `v2` đã có 20 gold qrels thủ công và 20 silver cases bám theo các năng lực của Document Assistant; cần tiếp tục bổ sung gold qrels cho PDF người dùng tải lên.
- Bộ RAGAS hiện chỉ có 3 gold-reference cases, phù hợp smoke regression nhưng chưa đủ làm quality gate production.
- PDF lớn có lớp text được hỗ trợ tới 75 MiB, nhưng thời gian parse/embed phụ thuộc provider và vẫn nằm trong một request đồng bộ.
- `frontend/mock.html` chỉ là prototype tĩnh; frontend production nằm trong `frontend/src`.
- Memory hiện là recent conversation window; chưa có semantic long-term user memory.

## 3. Nguyên tắc thiết kế

1. Giữ phiên bản hiện tại chạy được trong suốt quá trình refactor.
2. Retrieval và citation phải ổn định trước khi thêm orchestration.
3. Dùng một collection chunk dùng chung; lọc bằng `document_id`, không tạo collection cho từng tài liệu.
4. Milvus là retrieval store; PostgreSQL là control plane cho tài liệu, hội thoại và run.
5. Web frontend production chỉ giao tiếp với FastAPI; không import hoặc sao chép domain logic từ Python.
6. UI mặc định dùng `task=auto` để supervisor nhận diện QA/Summary/Quiz; các tab thủ công vẫn cho phép ép task rõ ràng.
7. Summary và Quiz là specialist workflow. Chỉ coi một component là agent khi nó thực sự có quyền chọn/gọi tool.
8. Validation xác định được bằng code phải chạy trước LLM reviewer.
9. Mọi retry trong graph đều có giới hạn.
10. Mỗi sprint phải kết thúc bằng một phiên bản demo được.

## 4. Kiến trúc mục tiêu

```text
                       React Web Frontend
                              |
                              v
                           FastAPI
                              |
             +----------------+----------------+
             |                                 |
      Document ingestion                 Assistant run
             |                                 |
 Upload -> Parse by page -> Chunk       Input guardrail
             |                                 |
             +-- PostgreSQL metadata      Task resolver
             +-- Milvus chunks                 |
                                     +----------+----------+
                                     |          |          |
                                     v          v          v
                                  QA flow   Summary flow  Quiz flow
                                     |          |          |
                                     +----------+----------+
                                                |
                                                v
                                    Citation validator
                                                |
                                         Review node
                                      PASS / bounded retry
                                                |
                                                v
                                     Structured response
```

### Ingestion flow

```text
upload/request
  -> validate input
  -> create Document(status=processing)
  -> parse into pages
  -> normalize metadata
  -> chunk with page provenance
  -> embed and write chunks to Milvus
  -> update Document(status=ready)
```

Khi lỗi, document chuyển sang `failed` và lưu thông báo an toàn để UI hiển thị. MVP xử lý đồng bộ; background queue là V2.

### Assistant flow

```text
request
  -> validate selected documents
  -> input guardrail
  -> resolve task
  -> execute specialist workflow
  -> deterministic validation
  -> optional LLM review
  -> persist run/messages
  -> response
```

## 5. Data model

### PostgreSQL

`documents`

- `id`: UUID
- `name`: tên hiển thị
- `mime_type`
- `source_type`: `upload | url | json`
- `source_uri`: nullable
- `checksum`
- `status`: `uploaded | processing | ready | failed`
- `page_count`
- `chunk_count`
- `embedding_model`
- `error_message`: nullable
- `created_at`, `updated_at`

`conversations`

- `id`: UUID
- `title`
- `created_at`, `updated_at`

`messages`

- `id`: UUID
- `conversation_id`
- `role`
- `content`
- `task`
- `run_id`: nullable
- `created_at`

`assistant_runs`

- `id`: UUID
- `conversation_id`
- `task`
- `status`
- `retry_count`
- `latency_ms`
- `trace_id`: nullable
- `created_at`, `completed_at`

Một bảng liên kết sẽ lưu các document được chọn cho conversation hoặc run nếu cần truy vấn/audit lâu dài.

### Milvus collection: `document_chunks`

- `chunk_id`
- `document_id`
- `text`
- `dense_vector`
- `page_number`
- `chunk_index`
- `source_name`
- `section_title`: nullable
- `content_type`
- `embedding_model`

`document_id` và các trường provenance phải filter/retrieve được. Không lưu trạng thái nghiệp vụ của document chỉ trong Milvus.

## 6. API contract dự kiến

### Documents

```text
POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
```

`POST /documents` nhận multipart PDF ở MVP. URL/JSON ingestion có thể dùng chung endpoint với request schema riêng hoặc endpoint nội bộ.

### Conversations và runs

```text
POST /api/v1/conversations
GET  /api/v1/conversations/{conversation_id}
POST /api/v1/assistant/runs
GET  /api/v1/assistant/runs/{run_id}
```

Request chính:

```json
{
  "conversation_id": "uuid",
  "document_ids": ["uuid"],
  "task": "auto",
  "message": "Transformer được định nghĩa như thế nào?"
}
```

`task` nhận `auto`, `qa`, `summary` hoặc `quiz`. Nút UI nên truyền task cụ thể; chat tự do có thể dùng `auto`.

Response chính:

```json
{
  "run_id": "uuid",
  "task": "qa",
  "answer": "...",
  "citations": [
    {
      "document_id": "uuid",
      "document_name": "transformer.pdf",
      "page_number": 5,
      "chunk_id": "uuid",
      "excerpt": "..."
    }
  ],
  "review": {
    "status": "pass",
    "retry_count": 0
  }
}
```

## 7. LangGraph state và workflow

State tối thiểu:

```python
class AssistantState(TypedDict):
    run_id: str
    conversation_id: str
    task: Literal["auto", "qa", "summary", "quiz"]
    message: str
    document_ids: list[str]
    rewritten_query: str | None
    retrieved_chunks: list[RetrievedChunk]
    draft_response: dict | None
    citations: list[Citation]
    review_status: Literal["pending", "pass", "fail"]
    review_feedback: str | None
    retry_count: int
    errors: list[str]
```

Workflow mục tiêu:

```text
START
  -> input_guardrail
  -> task_resolver
       -> qa: rewrite_query -> retrieve -> answer
       -> summary: resolve_scope -> retrieve/map-reduce -> summarize
       -> quiz: resolve_scope -> retrieve -> generate_quiz
  -> citation_validator
  -> review
       -> pass -> persist -> END
       -> fail and retry_count < 2 -> retry appropriate node
       -> fail and retry_count >= 2 -> persist warning -> END
```

## 8. Database được đưa vào giai đoạn nào?

| Giai đoạn | PostgreSQL | Milvus | Lý do |
|---|---:|---:|---|
| Sprint 1 - API/schema baseline | Chưa cần | Optional | Health, contract và unit test phải chạy không cần external service. |
| Sprint 2 - PDF/document lifecycle | Bắt buộc | Bắt buộc | PostgreSQL lưu document/status; Milvus lưu chunk/vector và provenance. |
| Sprint 3 - Retrieval | Bắt buộc | Bắt buộc | Filter theo `document_id`; keyword search có thể dùng PostgreSQL FTS hoặc Milvus sparse search. |
| Sprint 4 - LangGraph | Bắt buộc | Bắt buộc | Xác thực document scope trong PostgreSQL, truy xuất context từ Milvus; checkpoint tạm thời nằm trong process. |
| Sprint 5 - Memory/review | Bắt buộc | Bắt buộc | Persistent messages, review result, retry và audit trail. |
| Sprint 6 - Deploy/evaluation | Bắt buộc | Bắt buộc | Full-stack runtime, evaluation records và observability metadata. |
| Sprint 7 - History/Quiz Library | Bắt buộc | Không đổi | PostgreSQL lưu thread, message, quiz và attempt; Milvus vẫn chỉ phục vụ retrieval. |
| Sprint 8 - Demo hardening | Bắt buộc | Bắt buộc | Kiểm chứng selected-document scope, model runtime và luồng upload/retrieval thật. |

Quyết định lưu trữ:

- PostgreSQL là nguồn dữ liệu chuẩn cho document lifecycle, conversations, messages và assistant runs.
- Milvus chỉ giữ chunks, embeddings và metadata cần cho retrieval.
- Không lưu binary PDF trực tiếp trong PostgreSQL. MVP lưu file qua storage adapter trên local volume; object storage là bước nâng cấp.
- Không dùng in-memory repository cho document API production vì restart sẽ làm mất mapping giữa `document_id` và chunks.
- API liveness không truy cập database. Readiness endpoint sẽ kiểm tra PostgreSQL/Milvus sau khi hai dependency được tích hợp.

### Tiến độ MVP hiện tại

- [x] Chuyển project sang monorepo `frontend/` và `backend/`.
- [x] Giữ UI mock tách biệt, không kết nối backend.
- [x] Khởi tạo FastAPI application factory và `/api/v1` router.
- [x] Thêm liveness endpoint không phụ thuộc LLM/database.
- [x] Định nghĩa Document, Assistant Run, Citation, Review và Trace schemas.
- [x] Thêm backend Dockerfile và API service vào Docker Compose.
- [x] Chuẩn hóa retrieval output thành structured chunks.
- [x] Sinh và kiểm chứng citation trong RAG baseline.
- [x] Tạo retrieval benchmark đầu tiên.
- [x] Chuyển hybrid retrieval sang Milvus native BM25 + RRF, không tải corpus vào RAM.
- [x] Đẩy `document_id` filter xuống retrieval và giới hạn context trước generation.
- [x] Chuyển chunking sang token-aware 500/75 với stable provenance IDs.
- [x] Cho phép người dùng tự chọn provider; giữ Ollama như lựa chọn tùy chọn và thêm UX mock chọn/tải qua nút `Local`.
- [x] Mở rộng benchmark với gold qrels, Precision@K, nDCG@K và latency.
- [x] Chạy toàn bộ test suite trên Python runtime khả dụng.
- [x] Chạy live Milvus với corpus 179 chunks và OpenRouter embeddings.
- [x] Ghi báo cáo baseline đầu tiên tại `docs/reports/SPRINT_1_RETRIEVAL_BASELINE.md`.
- [x] Triển khai code Sprint 2: PostgreSQL, Alembic, PDF parser, local storage và document lifecycle API.
- [x] Thêm shared collection `document_chunks`, append/delete theo `document_id` và readiness check.
- [x] Thêm integration test upload/list/get/delete với indexer giả lập; toàn bộ 58 test đạt.
- [x] Chạy live PostgreSQL, migration, FastAPI và Milvus; liveness/readiness đều đạt.
- [x] Kiểm chứng parser với PDF text thật 69,89 MiB; upload scan 51,2 MiB được nhận nhưng chuyển `failed` an toàn vì chưa có OCR.
- [x] Hoàn tất Sprint 3 cho corpus hiện tại: profiles, query rewrite, 40-case benchmark và báo cáo so sánh.
- [x] Hoàn tất Sprint 4: LangGraph QA/Summary, structured auto routing, checkpointer theo conversation, unified API và trace; toàn bộ 74 test đạt.
- [x] Hoàn tất Sprint 5: Quiz, deterministic validation, LLM reviewer, bounded retry, PostgreSQL conversation memory và input guardrails; toàn bộ 80 test đạt.
- [x] Hoàn tất Sprint 6: React frontend, Docker full stack, model selector, observability và RAGAS baseline.
- [x] Hoàn tất Sprint 7: History, quản lý thread, Quiz Library và quiz attempts bền vững.
- [x] Hoàn tất Sprint 8: curated 5-document corpus, full-document Summary, Auto routing, quiz theo số câu, upload 75 MiB và kiểm tra model thật.

## 9. Roadmap triển khai

### Sprint 1 - Chuẩn hóa baseline hiện tại

Mục tiêu: biến RAG đang chạy thành baseline có contract và đo lường được.

Công việc:

- Tạo monorepo boundary và chuyển code hiện tại vào package backend trước khi xóa legacy root modules.
- Khởi tạo FastAPI application, versioned router và liveness endpoint không phụ thuộc external service.
- Định nghĩa schema nền cho document, assistant run, citation và review.
- Tách dần LLM factory, retrieval và generation khỏi `agent.py`.
- Định nghĩa `RetrievedChunk`, `Citation`, `AssistantResponse`.
- Bổ sung `chunk_id`, source và page provenance vào dữ liệu.
- Tạo tập benchmark ban đầu khoảng 20 câu.
- Thêm test cho metadata, retrieval result và citation mapping.
- Ghi lại baseline Recall@K, MRR và latency.

Definition of Done:

- Câu trả lời có output schema ổn định.
- Citation trỏ được về một chunk có thật.
- Test hiện tại tiếp tục chạy.
- Có báo cáo baseline đầu tiên.

### Sprint 2 - FastAPI, PDF và document lifecycle

Mục tiêu: upload PDF và truy vấn theo `document_id`.

Công việc:

- Thêm FastAPI application và versioned routers.
- Parse PDF theo từng trang.
- Thêm PostgreSQL, ORM và migration.
- Xây document lifecycle và ingestion service.
- Chuyển sang collection `document_chunks` dùng chung.
- Metadata filter theo một hoặc nhiều `document_ids`.
- Viết integration test upload -> index -> retrieve bằng dependency giả lập.

Definition of Done:

- Upload PDF thành công và xem được trạng thái.
- Chunk giữ đúng số trang.
- Hỏi theo `document_id` không lấy dữ liệu từ document khác.
- Trả citation gồm tên tài liệu và trang.

### Sprint 3 - Retrieval chất lượng và mở rộng

Mục tiêu: loại bỏ nút thắt BM25 in-memory và có benchmark đáng tin cậy.

Công việc:

- [x] Chuyển keyword search sang Milvus native sparse/BM25.
- [x] Dùng RRF để kết hợp dense và sparse ranks.
- [x] Đẩy multi-document filter xuống Milvus query.
- [x] Mở candidate pool lên 20 và giới hạn 4-6 chunks cho prompt.
- [x] Gắn 20 gold qrels thủ công cho corpus hiện tại; gold qrels PDF sẽ thêm sau khi có PDF thật.
- [x] Thêm query rewrite cho câu hỏi nối tiếp, giới hạn 6 turns/6.000 ký tự.
- [x] Mở rộng benchmark `v2` lên 40 câu: 20 gold và 20 silver theo use case của Document Assistant; giữ `v1` làm baseline bất biến.
- [x] So sánh dense-only, BM25-only và hybrid RRF trên cùng corpus/configuration.
- [x] Chưa thêm reranker: benchmark hiện tại chưa chứng minh lợi ích đủ để chấp nhận thêm latency/cost.

Definition of Done:

- Không tải toàn bộ corpus vào RAM để dựng BM25.
- Retrieval hỗ trợ multi-document filter.
- Có bảng so sánh Recall@5, MRR và latency.
- Chọn được retrieval configuration mặc định dựa trên số liệu.

### Sprint 4 - LangGraph QA và Summary

Mục tiêu: đưa orchestration rõ ràng vào hệ thống sau khi retrieval ổn định.

Công việc:

- [x] Xây state, nodes, conditional edges và graph compilation.
- [x] Structured task resolver cho `task=auto`.
- [x] QA workflow: rewrite -> retrieve -> answer.
- [x] Summary workflow: resolve scope -> retrieve/map-reduce -> summarize.
- [x] Checkpointer theo conversation/thread trong process; PostgreSQL persistence để Sprint 5.
- [x] Structured response từ FastAPI qua `POST /api/v1/assistant/runs`.
- [x] Unit test node/service và integration test đường đi trong graph/API.

Definition of Done:

- [x] Một API xử lý được QA và Summary.
- [x] Explicit task bỏ qua supervisor/router.
- [x] Trace cho biết chính xác graph đã đi qua node nào.
- [x] QA và Summary đều có citation.

### Sprint 5 - Quiz, Review, Memory và Guardrails

Mục tiêu: hoàn thiện workflow và tăng độ tin cậy.

Công việc:

- [x] Quiz output theo schema, có đáp án, giải thích và citation.
- [x] Deterministic validator kiểm tra citation, document scope và quiz schema.
- [x] LLM reviewer đánh giá grounding sau khi deterministic validation đạt.
- [x] Retry tối đa hai lần và route retry theo nguyên nhân lỗi.
- [x] Lưu conversation/message/run vào PostgreSQL.
- [x] Giới hạn history bằng recent window 12 messages, có thể cấu hình.
- [x] Guardrail cho file, input, document scope và instruction nằm trong tài liệu.

Definition of Done:

- [x] Quiz đúng schema và chỉ có một đáp án hợp lệ cho mỗi câu.
- [x] Citation giả hoặc ngoài document scope bị chặn.
- [x] Follow-up question hoạt động sau khi restart ứng dụng.
- [x] Graph không thể lặp vô hạn.

### Sprint 6 - Evaluation, observability, UI và deploy

Mục tiêu: tạo bản demo portfolio có thể chạy lại và giải thích được.

Công việc:

- Tích hợp Langfuse hoặc tracing backend tương đương.
- Ghi trace node, tool call, chunks, token, latency, lỗi và retry.
- Chạy RAGAS trên benchmark; lưu config và kết quả có version.
- Xây React/TypeScript frontend từ API contract; dùng mock HTML hiện tại làm tham chiếu giao diện.
- UI upload, chọn nhiều document, Ask/Summarize/Quiz và xem citation.
- Trang/expander Agent Trace.
- Docker Compose cho API, UI, PostgreSQL và Milvus.
- README gồm kiến trúc, trade-off, benchmark và demo scenario.

Definition of Done:

- Clone repo, cấu hình `.env` và chạy được bằng Docker Compose.
- Demo đầy đủ upload -> QA/Summary/Quiz -> citation -> trace.
- Evaluation có thể chạy lại bằng một command.
- README đủ để người phỏng vấn hiểu quyết định kỹ thuật chính.

### Sprint 7 - History và Quiz Library

Mục tiêu: biến conversation và quiz thành dữ liệu người dùng có thể xem, làm lại và quản lý.

- [x] List/load/rename/delete conversation và khôi phục message sau reload.
- [x] Lưu quiz thành entity riêng, hỗ trợ attempt, chấm điểm và best score.
- [x] Cascade dữ liệu liên quan khi xóa conversation.
- [x] Tích hợp History và Quiz Library vào frontend thật.

### Sprint 8 - Demo hardening và selected-document workflows

Mục tiêu: làm cho bản demo ổn định, phản ánh đúng phạm vi tài liệu người dùng chọn.

- [x] Tách dataset nguồn thành 5 document records với 65 chunks.
- [x] Summary tải toàn bộ chunks của tài liệu được chọn theo thứ tự nguồn, không đọc cả knowledge base.
- [x] Auto routing hỗ trợ QA, Summary và Quiz; tab thủ công vẫn là override.
- [x] Quiz đọc số câu từ yêu cầu, mặc định 5 và giới hạn tối đa 20.
- [x] Đồng bộ giới hạn upload FE/API/Nginx ở 75 MiB và trả lỗi scan PDF rõ ràng.
- [x] Cho chọn mọi provider/model trong catalog rồi **Apply & test** bằng request thật.
- [x] Loại cache SPA cũ và tinh gọn message UI.

## 10. Cấu trúc source mục tiêu

```text
.
|-- frontend/
|   |-- mock.html
|   |-- src/
|   |   |-- pages/
|   |   |-- components/
|   |   |   |-- common/
|   |   |   |-- chat/
|   |   |   |-- documents/
|   |   |   |-- quiz/
|   |   |   `-- agents/
|   |   |-- services/
|   |   |-- mocks/
|   |   |   |-- data/
|   |   |   `-- handlers/
|   |   |-- hooks/
|   |   |-- types/
|   |   |-- store/
|   |   `-- utils/
|   |-- package.json
|   `-- Dockerfile
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- api/
|   |   |-- agents/
|   |   |   |-- supervisor/
|   |   |   |-- retrieval/
|   |   |   |-- summarizer/
|   |   |   |-- quiz/
|   |   |   `-- reviewer/
|   |   |-- graph/
|   |   |-- rag/
|   |   |-- ingestion/
|   |   |-- tools/
|   |   |-- models/
|   |   |-- schemas/
|   |   |-- services/
|   |   |-- database/
|   |   |-- guardrails/
|   |   |-- en/
|   |   `-- core/valuatio
|   |-- alembic/
|   |-- tests/
|   |-- requirements.txt
|   `-- Dockerfile
|-- docs/
|-- scripts/
|-- .github/workflows/
|-- docker-compose.yml
`-- README.md
```

Các module hiện tại đã được chuyển vào package mới nhưng vẫn giữ nguyên hành vi:

- `frontend/mock.html`: UI mock độc lập, không kết nối backend và không phải production frontend.
- `backend/app/agents/retrieval/agent.py`: tool-calling retrieval agent hiện tại.
- `backend/app/core/llm.py`: LLM provider factory được tách từ agent cũ.
- `backend/app/rag/hybrid_search.py`: hybrid retriever được tách từ agent cũ.
- `backend/app/ingestion/web.py`: URL ingestion hiện tại.
- `backend/app/services/indexing.py`: Milvus seed và connection hiện tại.

Code sẽ được chuyển theo từng vertical slice. Chỉ xóa compatibility layer sau khi test và entrypoint mới thay thế đầy đủ chức năng cũ.

## 11. Phạm vi MVP và V2

### Điều chỉnh so với cấu trúc tham khảo

- `frontend/mock.html` được giữ ngoài `frontend/src`: đây là prototype xem trực tiếp, không phải mock API của React.
- `frontend/src/mocks` chỉ dành cho mock handlers/data khi frontend production được khởi tạo.
- `auth.py` và `Login.tsx` thuộc V2 vì authentication/multi-tenant chưa nằm trong MVP.
- `docx.py` và `pptx.py` thuộc V2; MVP ưu tiên PDF và URL ingestion.
- Backend dùng `assistant/runs` làm contract chính; có thể expose `chat.py` như adapter, không để chat transport quyết định graph design.
- Chỉ retrieval agent có `agent.py` và `prompt.py` ở hiện tại. Các agent khác chỉ có package marker cho đến khi có implementation và test.
- `Dockerfile`, React `package.json`, FastAPI `main.py` và `ci.yml` sẽ được thêm cùng runnable vertical slice tương ứng, không tạo placeholder không chạy được.

### MVP

- PDF và URL ingestion.
- Chọn và hỏi trên nhiều tài liệu.
- QA có citation trang.
- Summary và Quiz.
- LangGraph routing và bounded review.
- Persistent conversation.
- Evaluation dataset và trace.
- Docker Compose.

### V2

- DOCX/PPTX.
- OCR cho PDF scan.
- Authentication và multi-tenant.
- Long-term user memory.
- Background worker/queue quy mô lớn.
- Advanced reranking.
- Object storage và background OCR/ingestion workers.

## 12. Chất lượng và quy tắc hoàn thành chung

Một tính năng chỉ được coi là hoàn thành khi:

- có unit test cho domain logic;
- có integration test tại boundary quan trọng;
- lỗi không làm lộ secret hoặc stack trace cho người dùng;
- cấu hình nằm trong environment/config thay vì hard-code;
- output có type/schema rõ ràng;
- README hoặc tài liệu liên quan được cập nhật;
- phiên bản cũ vẫn chạy hoặc đã có migration được kiểm chứng;
- có log/trace đủ để chẩn đoán lỗi production.

## 13. Ưu tiên tiếp theo

1. Thêm OCR và background job để upload lớn không giữ request HTTP quá lâu.
2. Mở rộng RAGAS/gold set cho từng loại tài liệu và dùng threshold làm regression gate.
3. Thêm authentication, `user_id` và authorization filter trước khi triển khai nhiều người dùng.
4. Đánh giá reranker trên benchmark hiện tại; chỉ bật khi chất lượng tăng đủ bù latency/cost.
5. Chuyển file storage sang object storage và bổ sung backup/retention policy.
6. Thiết kế semantic long-term memory sau khi có consent và chính sách xóa dữ liệu.
