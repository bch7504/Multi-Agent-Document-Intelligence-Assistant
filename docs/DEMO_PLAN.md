# Demo Plan - Multi-Agent Document Intelligence Assistant

Kế hoạch test hoàn toàn trên giao diện nằm tại [UI_TEST_PLAN.md](UI_TEST_PLAN.md).

Thời lượng mục tiêu: 8-10 phút. Kịch bản này dùng dữ liệu và kết quả đã có trong
repository, không phụ thuộc vào việc tìm một PDF mới trong lúc trình bày.

## 1. Mục tiêu demo

Chứng minh bốn giá trị chính:

1. RAG truy xuất đúng phạm vi tài liệu và trả citation kiểm chứng được.
2. LangGraph điều phối các workflow QA, Summary và Quiz với validation/review.
3. PostgreSQL giữ conversation history, run audit, quiz và quiz attempts.
4. Chất lượng retrieval/generation được đo bằng benchmark và RAGAS có thể chạy lại.

Thông điệp mở đầu đề xuất:

> Đây không chỉ là một chatbot hỏi đáp. Hệ thống quản lý knowledge base, điều phối
> nhiều vai trò chuyên biệt, kiểm tra grounding trước khi trả lời, lưu lịch sử và
> cung cấp evaluation có thể tái lập.

## 2. Tài liệu và dữ liệu có sẵn

| Tài liệu/dữ liệu | Trạng thái | Dùng trong demo |
|---|---|---|
| `data/stack_ai.json` | Ready trong production DB | 5 tài liệu demo độc lập, tổng 65 chunks |
| `README.md` | Cập nhật đến Sprint 8 | Cài đặt, kiến trúc và demo entry point |
| `docs/PROJECT_PLAN.md` | Sprint 1-8 hoàn tất | Roadmap và quyết định phạm vi |
| Sprint 1 report | Có | Baseline retrieval ban đầu |
| Sprint 2 report | Có | Document lifecycle/PostgreSQL/Milvus |
| Sprint 3 report | Có | So sánh Dense, BM25 và Hybrid RRF |
| Sprint 4 report | Có | LangGraph QA/Summary |
| Sprint 5 report | Có | Quiz, reviewer, retry và memory |
| Sprint 6 report | Có | Full-stack, observability và RAGAS |
| Sprint 7 report | Có | History và Quiz Library |
| Sprint 8 report | Có | Demo hardening, selected-document workflows và model validation |
| RAGAS JSON report | Có | Kết quả chi tiết có version |

Knowledge base hiện có 5 tài liệu: Enterprise Security, Access & Identity;
Workflow Builder Fundamentals; Retrieval, Chunking & Embeddings; Knowledge Bases;
và Human in the Loop. Mỗi tài liệu có `document_id` riêng để Ask, Summarize và
Quiz chỉ xử lý phạm vi người dùng đã chọn.

## 3. Checklist trước demo

Chạy trước buổi demo 10-15 phút:

```bash
docker compose up -d
docker compose ps
```

Kiểm tra:

```bash
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/documents
```

Kết quả cần có:

- API trả `status=ready`;
- frontend trả HTTP 200 tại `http://localhost:3000`;
- đúng 5 tài liệu curated đều có trạng thái `ready`;
- tổng số chunks của 5 tài liệu là `65`;
- Alembic ở revision `20260917_0005`;
- provider/model trên nút **Models** đúng với embedding đã index.

Nếu dataset chưa xuất hiện, chạy lệnh idempotent:

```bash
docker compose exec -T api python -m backend.app.ingestion.import_json \
  /code/data/stack_ai.json --curated-demo
```

Chuẩn bị trình duyệt:

- Tab 1: `http://localhost:3000`;
- Tab 2: `docs/reports/SPRINT_3_RETRIEVAL_COMPARISON.md`;
- Tab 3: `docs/reports/SPRINT_6_FULLSTACK_EVALUATION.md`;
- tạo một thread mới và chọn `Enterprise Security, Access & Identity`;
- gửi trước một câu hỏi ngắn để warm-up cloud model;
- không mở `.env` hoặc hiển thị API key.

## 4. Kế hoạch test thủ công trước demo

Mở `http://localhost:3000`, nhấn `Ctrl + F5`, sau đó mở DevTools ở tab **Network**
và **Console**. Thực hiện theo đúng thứ tự để kiểm tra cả scope, memory và dữ liệu
được lưu.

### T01 - Khởi động và danh sách tài liệu

1. Kiểm tra cả 6 container bằng `docker compose ps`.
2. Mở FE và xác nhận sidebar hiển thị đúng 5 tài liệu, tất cả ở trạng thái ready.
3. Xác nhận tổng số chunks là 65: `19 + 11 + 10 + 19 + 6`.
4. Mở **Models**, giữ model hiện tại và nhấn **Apply & test**; cả chat và embedding phải báo dùng được.

Kết quả đạt: không có request `404`, `500` hoặc `504`; API health và FE đều trả 200.

### T02 - Ask chỉ trên một tài liệu

Chỉ chọn `Enterprise Security, Access & Identity`, chọn **Ask** và gửi:

```text
According to the selected documentation, how do Role-Based Access Controls,
Workspace and Folder Access, and Project Controls differ?
```

Kết quả đạt:

- reviewer cuối cùng là `PASS`;
- có ít nhất một citation;
- mọi citation đều mang tên `Enterprise Security, Access & Identity`;
- trace có `retrieve_qa -> answer_qa -> validate_output -> review_output`;
- không có citation từ bốn tài liệu không được chọn.

### T03 - Follow-up và short-term memory

Giữ nguyên thread và tài liệu đã chọn, gửi:

```text
How does Authentication and MFA complement those controls?
```

Kết quả đạt:

- trace `rewrite_query` cho thấy câu hỏi được viết lại bằng lịch sử;
- câu trả lời vẫn chỉ có citation từ tài liệu Security;
- refresh trang vẫn tải lại đủ message;
- **History** mở được thread mà không phát sinh 404.

### T04 - Tóm tắt toàn bộ tài liệu được chọn

Giữ duy nhất tài liệu Security, chọn **Summarize** và gửi:

```text
Summarize the selected security documentation into five practical controls for
an enterprise deployment.
```

Kết quả đạt:

- trace ghi `Loaded all 19 indexed chunks in source order`;
- map xử lý các batch của đúng tài liệu Security rồi reduce một lần;
- reviewer là `PASS` và citation chỉ thuộc tài liệu Security;
- không đọc toàn bộ 65 chunks của knowledge base;
- request hoàn tất trước timeout 300 giây. Mốc đo gần nhất khoảng 18 giây.

### T05 - Quiz theo tài liệu được chọn

Tạo thread mới, chỉ chọn `Knowledge Bases`, chọn **Quiz** và gửi:

```text
Create a 2-question quiz about creating and using a Knowledge Base using only the selected documentation.
```

Kết quả đạt:

- có đúng 2 câu, mỗi câu có một đáp án đúng, explanation và citation;
- reviewer cuối cùng là `PASS`;
- citation chỉ thuộc tài liệu `Knowledge Bases`;
- quiz xuất hiện trong **Quizzes**, submit được và lưu attempt/best score.

Đây là prompt smoke ổn định đã được kiểm chứng. Prompt quiz rộng trên nhiều chủ đề vẫn
có thể bị reviewer chặn nếu model gắn sai excerpt; đó là hành vi guardrail mong đợi.

### T06 - Kiểm tra cô lập phạm vi tài liệu

Tạo **New thread**, bỏ chọn Security và chỉ chọn `Knowledge Bases`. Gửi:

```text
How do I create and use a Knowledge Base?
```

Kết quả đạt: mọi citation đều thuộc `Knowledge Bases`. Sau đó chọn thêm
`Retrieval, Chunking & Embeddings` và hỏi mối liên hệ giữa chunking, embeddings
và knowledge base; citation chỉ được phép thuộc hai tài liệu đang chọn.

### T07 - New thread, History và lỗi trình duyệt

1. Nhấn **New thread** và xác nhận vùng chat trống ngay lập tức.
2. Không gửi message, reload trang; không được có request messages trả 404.
3. Mở một thread cũ từ **History**, đổi tên rồi reload.
4. Xóa thread test và xác nhận nó biến mất khỏi History và quiz liên quan được xóa.

Kết quả đạt: Console không có `Failed to load resource`; các request assistant
trả 200. Nếu model cloud chậm, Network có thể pending nhưng không được trả 504
trước 300 giây.

### T08 - Ma trận kết quả nhanh

| Case | Scope | Kết quả bắt buộc |
|---|---|---|
| Ask | 1 tài liệu Security | PASS, citation đúng scope |
| Follow-up | Cùng thread Security | Có query rewrite và memory |
| Summarize | 19 chunks Security | Đọc đủ 19 chunks, không đọc 65 chunks |
| Quiz | 1 tài liệu Knowledge Bases | 2 câu, PASS, lưu Quiz Library |
| Isolation | 1 tài liệu Knowledge Bases | Không citation chéo sang Security |
| Multi-document | Knowledge Bases + Retrieval | Citation chỉ nằm trong 2 tài liệu |
| Persistence | Reload/History | Message và quiz vẫn tồn tại |

## 5. Kịch bản demo 8-10 phút

### 0:00-0:45 - Bài toán và kiến trúc

Trình bày ngắn:

```text
React/Nginx -> FastAPI -> LangGraph
                         |-> PostgreSQL: lifecycle, history, quiz, audit
                         `-> Milvus: dense embedding + BM25 + RRF
```

Nêu rõ multi-agent trong dự án là các vai trò chuyên biệt được LangGraph điều
phối theo state/route, không phải nhiều chatbot độc lập chạy không kiểm soát.

### 0:45-1:30 - Knowledge base và model

1. Chỉ ra 5 tài liệu đã được tách độc lập trong knowledge base.
2. Chọn duy nhất `Enterprise Security, Access & Identity` cho luồng security.
3. Mở **Models**, chỉ ra chat model/embedding model rồi nhấn **Apply & test**.
4. Giải thích backend gọi thử model thật; API key không bao giờ được trả xuống FE.

### 1:30-3:15 - Grounded QA và citation

Chọn **Ask**, dùng prompt:

```text
According to the selected documentation, how do Role-Based Access Controls,
Workspace and Folder Access, and Project Controls differ?
```

Sau khi có kết quả:

1. Mở citation và đối chiếu excerpt.
2. Mở Agent Trace.
3. Chỉ ra luồng `rewrite -> retrieve -> answer -> validate -> review -> finalize`.
4. Giải thích document filter được đẩy xuống retrieval và citation do backend dựng.

### 3:15-4:15 - Conversational memory

Hỏi follow-up:

```text
How does Authentication and MFA complement those controls?
```

Giải thích query rewrite dùng recent PostgreSQL history. Refresh trang để chứng
minh message được nạp lại, sau đó mở **History** và đổi tên thread thành
`Stack AI Security Demo`.

### 4:15-5:30 - Summary workflow

Chọn **Summarize**:

```text
Summarize the Security & Governance guidance into five practical controls for
an enterprise deployment.
```

Mở trace và chỉ ra `scope -> retrieve -> map -> reduce -> validate -> review`.
Map-reduce giúp xử lý nhiều context mà không đưa toàn bộ corpus vào một prompt.

### 5:30-7:15 - Quiz và quản lý kết quả

Tạo thread mới, chỉ chọn `Knowledge Bases`, rồi chọn **Quiz**:

```text
Create a 2-question quiz about creating and using a Knowledge Base using only the selected documentation.
```

Sau khi sinh quiz:

1. Mở citation của một câu hỏi.
2. Mở **Quizzes**.
3. Chọn quiz vừa tạo và làm bài.
4. Submit để hiển thị score, explanation và citation.
5. Cho thấy attempt history và best score.

### 7:15-8:30 - Evaluation có số liệu

Mở Sprint 3 report và trình bày quá trình cải thiện retrieval:

| Mốc | Hit Rate@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| Sprint 1 baseline | 0.4500 | 0.3750 | 0.2542 |
| Sprint 3 Hybrid RRF | 0.9500 | 0.8133 | 0.7191 |

Mở Sprint 6 report:

| RAGAS metric | Score |
|---|---:|
| Faithfulness | 0.9693 |
| Answer relevancy | 0.9158 |
| Context precision | 0.7455 |
| Factual correctness | 0.4867 |

Giải thích factual correctness thấp do answer thường rộng hơn gold reference ngắn;
bộ ba case hiện là smoke baseline, chưa dùng làm production quality gate.

### 8:30-9:00 - Kết luận

Thông điệp kết thúc:

> Hệ thống đã bao phủ vòng đời đầy đủ: ingest tài liệu, retrieval hybrid, sinh
> output có cấu trúc, validation/review, persistent history, quiz management,
> observability và evaluation có thể chạy lại.

## 6. Tiêu chí demo thành công

- Câu QA có ít nhất một citation hợp lệ.
- Agent Trace kết thúc với reviewer `PASS`.
- Follow-up sử dụng được ngữ cảnh thread.
- Reload vẫn xem được message qua History.
- Quiz xuất hiện trong Quiz Library và lưu được attempt/score.
- Không lộ API key hoặc dữ liệu `.env`.

## 7. Phương án dự phòng

| Rủi ro | Cách xử lý |
|---|---|
| Cloud model phản hồi chậm | Dùng thread/quiz đã lưu trong History và Quiz Library |
| Provider rate limit | Chuyển sang cloud provider khác đã được cấu hình; không đổi embedding model của index hiện tại |
| Citation/reviewer fail | Dùng prompt chính xác theo heading ở trên và mở trace để giải thích bounded retry |
| Frontend không mở | Kiểm tra `docker compose ps`, sau đó dùng Swagger tại `http://localhost:8000/docs` |
| Dataset không xuất hiện | Chạy lại lệnh import idempotent trong checklist |
| Không đủ thời gian | Chỉ demo QA + citation + trace, Quiz Library và bảng evaluation |

Không nên demo upload PDF scan vì MVP chưa có OCR. Không chọn Ollama nếu local
runtime/model chưa được chuẩn bị. Không tuyên bố đã có authentication hoặc semantic
long-term user memory; hai phần này vẫn nằm ngoài phạm vi hiện tại.

## 8. Tài liệu dẫn chứng

- [Project plan](PROJECT_PLAN.md)
- [Sprint 1 retrieval baseline](reports/SPRINT_1_RETRIEVAL_BASELINE.md)
- [Sprint 2 document lifecycle](reports/SPRINT_2_DOCUMENT_LIFECYCLE.md)
- [Sprint 3 retrieval comparison](reports/SPRINT_3_RETRIEVAL_COMPARISON.md)
- [Sprint 4 LangGraph QA/Summary](reports/SPRINT_4_LANGGRAPH_QA_SUMMARY.md)
- [Sprint 5 Quiz/Review/Memory](reports/SPRINT_5_QUIZ_REVIEW_MEMORY.md)
- [Sprint 6 Full-stack/Evaluation](reports/SPRINT_6_FULLSTACK_EVALUATION.md)
- [Sprint 7 History/Quiz Library](reports/SPRINT_7_HISTORY_QUIZ_LIBRARY.md)
- [Sprint 8 Demo hardening](reports/SPRINT_8_DEMO_HARDENING.md)
- [RAGAS result](reports/evaluation/ragas_stack_ai_v1.json)
