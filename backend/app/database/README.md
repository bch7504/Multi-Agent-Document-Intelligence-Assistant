# Database boundary

Database integration is active for the Sprint 2 PDF/document lifecycle.

- PostgreSQL owns documents now; conversations, messages, assistant runs, and checkpoints are added in later sprints.
- Milvus will own retrievable chunks, embeddings, and retrieval metadata.
- Uploaded binaries will use a storage adapter; they will not be stored in PostgreSQL.
- Liveness remains database-independent. Readiness checks PostgreSQL and Milvus.

The production document API uses SQLAlchemy sessions and Alembic migrations; in-memory SQLite is used only in tests.
