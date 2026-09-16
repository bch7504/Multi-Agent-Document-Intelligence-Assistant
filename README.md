# Multi-Agent Document Intelligence Assistant

Project đang được nâng cấp từ RAG LangChain hiện tại thành hệ thống Document Intelligence với FastAPI, LangGraph, Milvus, PostgreSQL và web frontend.

Roadmap và thiết kế đầy đủ nằm tại [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

Kết quả retrieval đầu tiên nằm tại [docs/reports/SPRINT_1_RETRIEVAL_BASELINE.md](docs/reports/SPRINT_1_RETRIEVAL_BASELINE.md).

## Trạng thái hiện tại

Backend RAG hiện có:

- LangChain 1.x agent với retrieval tool.
- Hybrid retrieval native trong Milvus: dense vector + BM25 + RRF.
- Gemini, OpenRouter, OpenAI hoặc Ollama chat model.
- OpenRouter, OpenAI, Gemini hoặc Ollama embeddings, với model có thể cấu hình riêng.
- Ingestion từ JSON local hoặc website.
- Cập nhật Milvus collection qua staging/backup để tránh mất collection cũ khi seed lỗi.

Phần đang được xây tiếp:

- Document API trên nền FastAPI đã có upload/list/detail/delete.
- PDF ingestion theo trang và citation có cấu trúc đã được triển khai cho MVP.
- PostgreSQL hiện lưu document lifecycle; conversation/message sẽ được thêm ở Sprint 4–5.
- LangGraph QA, Summary, Quiz và Review workflows.
- React/TypeScript frontend production.
- Evaluation, tracing và full-stack Docker Compose.

FastAPI foundation hiện có:

- application factory và API prefix `/api/v1`;
- liveness endpoint không phụ thuộc LLM/database;
- schema nền cho document, assistant run, citation và review;
- backend Dockerfile và service API trong Docker Compose.

Sprint 1 baseline hiện có thêm:

- kết quả retrieval chuẩn hóa thành structured chunks;
- grounded QA dùng structured LLM output;
- citation do backend dựng từ `chunk_id` đã retrieval;
- deterministic validation cho document scope, page và excerpt;
- retrieval benchmark 20 câu với Hit Rate@K, Recall@K và MRR.
- document scope được đẩy xuống Milvus trước retrieval;
- token-aware chunking 500 tokens/75 overlap với stable `document_id` và `chunk_id`;
- benchmark hỗ trợ gold qrels, Precision@K, nDCG@K và latency.

Sprint 3 retrieval hiện có:

- ba profile đo độc lập: `dense_only`, `bm25_only`, `hybrid_rrf`;
- benchmark `v2` gồm 20 gold qrels và 20 silver cases bám theo năng lực của Document Assistant; `v1` được giữ nguyên để tái lập baseline Sprint 1;
- query rewrite cho follow-up question với history được giới hạn;
- live comparison chọn `hybrid_rrf` làm mặc định;
- chưa thêm reranker vì chưa có bằng chứng benchmark đủ mạnh so với chi phí/latency.

## UI mock

[frontend/mock.html](frontend/mock.html) là bản xem giao diện độc lập:

- không kết nối backend;
- không gửi file hoặc dữ liệu ra ngoài;
- không cần cài Node.js/Python;
- có interaction giả lập cho chọn tài liệu, upload, task mode và chat;
- có nút `Cloud` và `Local` để chọn độc lập chat/embedding model, hoặc nhập model ID mong muốn cho OpenRouter, OpenAI, Gemini và Ollama; tải Ollama chỉ được mô phỏng và UI không giữ API key.

Mở trực tiếp file bằng trình duyệt để duyệt giao diện. JavaScript trong mock chỉ phục vụ interaction cục bộ và sẽ không được dùng làm business logic cho frontend thật.

## Yêu cầu cho RAG hiện tại

- Python 3.10 trở lên.
- Docker Desktop/Docker Compose để chạy Milvus.
- Một trong các lựa chọn LLM:
  - Gemini: `GOOGLE_API_KEY`.
  - OpenRouter: `OPENROUTER_API_KEY` và model hỗ trợ tool calling.
  - OpenAI: `OPENAI_API_KEY`.
  - Ollama: Ollama đang chạy và đã tải chat model.
- Một embedding provider: `openrouter`, `openai`, `gemini` hoặc `ollama`.
- Nếu dùng OpenRouter/OpenAI/Gemini embeddings, API key tương ứng được dùng lại; nếu dùng Ollama, cần tải model khớp với `OLLAMA_EMBEDDING_MODEL`.
- Cấu hình local khuyên dùng cho tài liệu Việt–Anh:
  - chat: `qwen3:8b`;
  - embedding: `qwen3-embedding:0.6b`.

## Cài đặt Python

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp .env.example .env
```

Trong `.env`, người dùng phải tự chọn `LLM_PROVIDER` và `EMBEDDING_PROVIDER`; project không tự chọn provider mặc định. Chỉ điền API key của provider được chọn và không commit file `.env`.

Model chat và embedding được chọn độc lập qua các biến như `OPENROUTER_MODEL`, `OPENROUTER_EMBEDDING_MODEL`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` và `OLLAMA_EMBEDDING_MODEL`. Mỗi lần đổi embedding model phải index lại collection Milvus.

Ví dụ dùng OpenRouter cho cả chat và embedding:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-5.6-luna
EMBEDDING_PROVIDER=openrouter
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Local vẫn được hỗ trợ nhưng không chạy cho đến khi người dùng chủ động đặt `LLM_PROVIDER=ollama` hoặc `EMBEDDING_PROVIDER=ollama`.

### Chạy hoàn toàn local với Ollama

UI để người dùng tự chọn model. Cấu hình dưới đây chỉ là lựa chọn khuyên dùng để chạy nhanh:

```bash
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
```

Máy ít RAM có thể dùng `qwen3:4b`; máy mạnh hơn có thể dùng `qwen3:14b`. Sau đó chỉnh `OLLAMA_CHAT_MODEL` trong `.env`. Khi đổi `OLLAMA_EMBEDDING_MODEL`, bắt buộc index lại collection vì vector dimension/model đã thay đổi.

API key Gemini/OpenRouter/OpenAI chỉ nằm trong `.env` ở backend, không nhập vào UI và không gửi xuống trình duyệt.

## Chạy API và Milvus bằng Docker

```bash
docker compose up -d
docker compose ps
```

- API health: <http://localhost:8000/api/v1/health/live>
- API readiness: <http://localhost:8000/api/v1/health/ready>
- API docs ở môi trường development: <http://localhost:8000/docs>
- Milvus: `localhost:19530`
- Milvus WebUI: <http://localhost:9091/webui/>
- MinIO API/console: `localhost:9000` / `localhost:9001`

Dữ liệu container nằm trong `volumes/` và không được commit.

PostgreSQL, database và bảng `documents` được tạo tự động. Container API chạy
`alembic upgrade head` trước khi FastAPI khởi động, nên không cần tạo database
hoặc bảng thủ công.

Upload PDF sau khi stack đã sẵn sàng:

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -F "file=@./example.pdf;type=application/pdf"
```

Các endpoint document:

```text
POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
```

Nếu chỉ cần hạ tầng Milvus:

```bash
docker compose up -d etcd minio standalone
```

Chạy API trực tiếp sau khi cài dependencies:

```bash
fastapi dev backend/app/main.py
```

## Chuẩn bị dữ liệu hiện tại

Crawl website mặc định và lưu JSON:

```bash
python -m backend.app.ingestion.web
```

Seed JSON vào Milvus:

```bash
python -m backend.app.services.indexing
```

Lần seed tiếp theo sẽ tạo collection schema mới gồm dense vector và Milvus native BM25. Collection cũ không có sparse field sẽ báo lỗi rõ ràng và cần được seed lại.

File JSON đầu vào có cấu trúc:

```json
[
  {
    "page_content": "Nội dung tài liệu",
    "metadata": {
      "source": "https://example.com",
      "title": "Tiêu đề"
    }
  }
]
```

## Kiểm tra nhanh

```bash
python -m unittest discover -s backend/tests -v
python -m compileall -q backend
python -m pip check
```

Chạy retrieval benchmark sau khi collection `data_test` đã được index:

```bash
python -m backend.app.evaluation.run_retrieval --collection data_test --k 5
```

Benchmark không gọi LLM và không cần LLM API key.

## Cấu trúc hiện tại

```text
.
|-- frontend/
|   |-- mock.html            # Static UI mock, không gọi backend
|   |-- src/                 # Scaffold cho React frontend production
|   `-- README.md
|-- backend/
|   |-- app/
|   |   |-- main.py          # FastAPI application factory
|   |   |-- agents/
|   |   |   `-- retrieval/
|   |   |       `-- agent.py # Tool-calling retrieval agent hiện tại
|   |   |-- api/             # Versioned routers và health endpoint
|   |   |-- core/
|   |   |   `-- llm.py       # LLM provider factory
|   |   |-- ingestion/
|   |   |   `-- web.py       # Crawl/chunk/save dữ liệu web
|   |   |-- rag/
|   |   |   `-- hybrid_search.py
|   |   `-- services/
|   |       `-- indexing.py  # Seed và kết nối Milvus
|   |-- alembic/             # PostgreSQL migrations từ Sprint 2
|   |-- tests/
|   |-- requirements.txt
|   `-- Dockerfile
|-- scripts/
|-- docs/
|   `-- PROJECT_PLAN.md
|-- docker-compose.yml       # API và Milvus standalone
|-- .env.example
`-- README.md
```

## Quy ước chuyển đổi

Các module RAG cũ đã được chuyển vào package mới nhưng chưa bị viết lại. Mỗi vertical slice sẽ được thay thế kèm test; compatibility code chỉ bị xóa sau khi API/workflow mới cung cấp đầy đủ hành vi tương đương.
