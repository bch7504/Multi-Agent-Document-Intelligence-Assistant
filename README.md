# RAG chatbot với LangChain

Ứng dụng Streamlit dùng LangChain 1.x, Milvus và ensemble retrieval (70% vector search + 30% BM25) để trả lời dựa trên dữ liệu đã index.

## Tính năng

- LLM: Gemini 2.5 Flash, GPT-5.6 Luna qua OpenRouter, hoặc Qwen2.5 7B local qua Ollama.
- Embedding: HuggingFace `all-MiniLM-L6-v2` hoặc Ollama `nomic-embed-text`.
- Nạp dữ liệu từ JSON local hoặc crawl website.
- Milvus standalone chạy bằng Docker Compose.
- Seed qua collection staging; collection đang dùng được giữ nguyên nếu ghi mới thất bại.
- Agent và retriever được cache theo cấu hình để tránh tạo lại trên mỗi Streamlit rerun.

## Yêu cầu

- Python 3.10 trở lên.
- Docker Desktop/Docker Compose để chạy Milvus.
- Một trong các lựa chọn LLM:
  - Gemini: `GOOGLE_API_KEY`.
  - OpenRouter: `OPENROUTER_API_KEY` và một model hỗ trợ tool calling.
  - Ollama: Ollama đang chạy và đã tải model chat.
- Nếu dùng Ollama embeddings: đã tải `nomic-embed-text`.

## Cài đặt

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Điền API key cần dùng trong `.env`. Không commit file `.env`.

## Cấu hình

```env
MILVUS_URI=http://localhost:19530

GOOGLE_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-5.6-luna
OPENROUTER_SITE_URL=http://localhost:8501
OPENROUTER_APP_NAME=RAG LangChain

OLLAMA_CHAT_MODEL=qwen2.5:7b
USER_AGENT=RAG-LangChain/1.0
```

OpenRouter dùng API tương thích OpenAI tại `https://openrouter.ai/api/v1` với model `openai/gpt-5.6-luna`. Model này hỗ trợ tool calling để agent gọi retriever. Xem [OpenRouter OpenAI SDK integration](https://openrouter.ai/docs/guides/community/openai-sdk), [GPT-5.6 Luna](https://openrouter.ai/openai/gpt-5.6-luna-20260709) và [tool calling](https://openrouter.ai/docs/guides/features/tool-calling).

## Chạy Milvus

File `docker-compose.yml` trong repo dựa trên cấu hình standalone chính thức của Milvus 2.6.x.

```bash
docker compose up -d
docker compose ps
```

- Milvus: `localhost:19530`
- Milvus WebUI: <http://localhost:9091/webui/>
- MinIO API/console: `localhost:9000` / `localhost:9001`

Dữ liệu container nằm trong `volumes/` và không được commit.

## Chuẩn bị dữ liệu

### Cách 1: Qua giao diện

Chạy app, chọn embedding model rồi dùng phần **Nạp dữ liệu** trong sidebar. Embedding model dùng để truy vấn phải trùng với model đã dùng khi seed collection; app kiểm tra thông tin này với collection mới.

File JSON mặc định là `data/stack_ai.json` với cấu trúc:

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

### Cách 2: Qua command line

```bash
python crawl.py
python seed_data.py
```

`crawl.py` tải endpoint Markdown dành cho LLM tại `https://docs.stackai.com/llms-full.txt`
và tạo `data/stack_ai.json`; `seed_data.py` seed file đó vào collection `data_test`
bằng HuggingFace embeddings.

Nếu dùng Ollama:

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
```

## Chạy ứng dụng

```bash
streamlit run main.py
```

Mở <http://localhost:8501>, chọn:

1. Embedding model khớp với collection.
2. Gemini 2.5 Flash, GPT-5.6 Luna (OpenRouter), hoặc Qwen2.5 7B (Local).
3. Collection cần truy vấn.

Agent chỉ được khởi tạo khi gửi câu hỏi đầu tiên và được cache cho các lần rerun tiếp theo.

## Kiểm tra nhanh

```bash
python -m unittest discover -s tests -v
python -m compileall -q main.py agent.py crawl.py seed_data.py
python -m pip check
```

## Cấu trúc

```text
.
├── agent.py             # Retriever, provider LLM và LangChain agent
├── crawl.py             # Crawl/chunk/save dữ liệu
├── seed_data.py         # Seed và kết nối Milvus an toàn
├── main.py              # Streamlit UI
├── tests/               # Smoke/unit tests không cần API key hay Milvus thật
├── docker-compose.yml   # Milvus standalone
├── .env.example         # Cấu hình mẫu
└── requirements.txt
```
