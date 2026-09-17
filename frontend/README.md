# Frontend

`frontend/` contains two independent interfaces:

- `mock.html`: the original standalone visual prototype. It never calls the backend.
- `src/`: the production React/TypeScript application backed by `/api/v1`.

The production application supports server-backed chat/embedding model selection,
custom model IDs, PDF upload, document selection, QA, summary, quiz, citations,
reviewer status, token usage, and Agent Trace. Embedding selection is locked once
ready documents exist because changing it requires re-indexing Milvus.

Run locally:

```bash
npm install
npm run dev
```

Or run the full stack and open <http://localhost:3000>:

```bash
docker compose up -d --build
```

API keys stay in backend environment variables. The browser never receives them.
