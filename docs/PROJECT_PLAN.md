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
- Gemini, OpenRouter, OpenAI và Ollama chat providers.
- Unit/smoke tests không yêu cầu dịch vụ bên ngoài.

### Chưa có

- Upload và parse PDF theo trang.
- PDF page metadata đầy đủ cho document lifecycle.
- FastAPI và API contract ổn định.
- PostgreSQL cho document/conversation metadata.
- LangGraph workflow được định nghĩa rõ ràng.
- Summary, Quiz và Review workflow.
- Persistent conversation memory.
- Gold evaluation dataset, RAGAS và tracing production.
- Docker Compose cho toàn bộ ứng dụng.

### Hạn chế cần xử lý

- Benchmark `v2` đã có 20 gold qrels thủ công và 20 silver cases bám theo các năng lực của Document Assistant; cần tiếp tục bổ sung gold qrels cho PDF người dùng tải lên.
- Người dùng chọn trực tiếp tên collection; cách này không phù hợp với document lifecycle.
- Câu trả lời hiện là chuỗi text, chưa có output schema và citation có thể kiểm chứng.
- Chưa có web frontend production; file mock không chứa business logic và không gọi API.
- Lịch sử hội thoại mất khi session kết thúc.

## 3. Nguyên tắc thiết kế

1. Giữ phiên bản hiện tại chạy được trong suốt quá trình refactor.
2. Retrieval và citation phải ổn định trước khi thêm orchestration.
3. Dùng một collection chunk dùng chung; lọc bằng `document_id`, không tạo collection cho từng tài liệu.
4. Milvus là retrieval store; PostgreSQL là control plane cho tài liệu, hội thoại và run.
5. Web frontend production chỉ giao tiếp với FastAPI; không import hoặc sao chép domain logic từ Python.
6. Các task rõ ràng từ UI được route trực tiếp; chỉ dùng supervisor khi `task=auto`.
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
| Sprint 4 - LangGraph | Bắt buộc | Bắt buộc | Lưu run/conversation/checkpoint và truy xuất context. |
| Sprint 5 - Memory/review | Bắt buộc | Bắt buộc | Persistent messages, review result, retry và audit trail. |
| Sprint 6 - Deploy/evaluation | Bắt buộc | Bắt buộc | Full-stack runtime, evaluation records và observability metadata. |

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
- [ ] Chạy upload end-to-end với một PDF thật khi có file kiểm thử được chọn.
- [x] Hoàn tất Sprint 3 cho corpus hiện tại: profiles, query rewrite, 40-case benchmark và báo cáo so sánh.

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

- Xây state, nodes, conditional edges và graph compilation.
- Structured task resolver cho `task=auto`.
- QA workflow: rewrite -> retrieve -> answer.
- Summary workflow: resolve scope -> retrieve/map-reduce -> summarize.
- Checkpointer theo conversation/thread.
- Streaming event hoặc response từ FastAPI.
- Unit test từng node và integration test đường đi trong graph.

Definition of Done:

- Một API xử lý được QA và Summary.
- Explicit task bỏ qua supervisor/router.
- Trace cho biết chính xác graph đã đi qua node nào.
- QA và Summary đều có citation.

### Sprint 5 - Quiz, Review, Memory và Guardrails

Mục tiêu: hoàn thiện workflow và tăng độ tin cậy.

Công việc:

- Quiz output theo schema, có đáp án, giải thích và citation.
- Deterministic validator kiểm tra citation, document scope và quiz schema.
- LLM reviewer đánh giá grounding cho các trường hợp cần thiết.
- Retry tối đa hai lần và route retry theo nguyên nhân lỗi.
- Lưu conversation/message/run vào PostgreSQL.
- Giới hạn history; dùng recent window hoặc conversation summary.
- Guardrail cho file, input, document scope và instruction nằm trong tài liệu.

Definition of Done:

- Quiz đúng schema và chỉ có một đáp án hợp lệ cho mỗi câu.
- Citation giả hoặc ngoài document scope bị chặn.
- Follow-up question hoạt động sau khi restart ứng dụng.
- Graph không thể lặp vô hạn.

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
|   |   |-- evaluation/
|   |   `-- core/
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
- React frontend.

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

## 13. Thứ tự thực hiện ngay

1. Scaffold package theo cấu trúc mới.
2. Định nghĩa retrieval/citation schemas.
3. Viết adapter quanh retriever hiện tại để trả structured chunks.
4. Thêm citation vào baseline chat.
5. Tạo benchmark nhỏ và ghi kết quả baseline.
6. Sau đó mới bắt đầu FastAPI và PDF ingestion.
