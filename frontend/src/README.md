# Production frontend source

- `components/documents`: PDF upload, lifecycle state, and multi-document scope.
- `components/chat`: assistant workspace and citation rendering.
- `components/quiz`: interactive quiz answers and explanations.
- `components/agents`: graph trace, review, retry, latency, and token usage.
- `services`: typed FastAPI client.
- `types`: camelCase API contracts shared by UI components.

This application does not reuse business logic from `../mock.html`.
