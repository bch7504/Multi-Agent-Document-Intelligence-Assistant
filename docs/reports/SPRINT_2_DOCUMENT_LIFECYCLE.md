# Sprint 2 Document Lifecycle

Run date: 2026-09-16

## Implemented

- PostgreSQL service with persistent volume and health check in Docker Compose.
- Automatic Alembic migration before the API container starts.
- `documents` table for upload metadata, status, checksum, page/chunk counts,
  embedding model, safe error message, and timestamps.
- Local-volume PDF storage with path containment, streaming SHA-256 checksum,
  PDF signature validation, and an initial 25 MiB default size limit.
- Page-preserving PDF parsing and token-aware chunks carrying stable
  `document_id`, `chunk_id`, and one-based `page_number` metadata.
- Shared Milvus `document_chunks` collection with append and delete operations
  scoped by `document_id`.
- Document API: upload, list, detail, and delete.
- Lifecycle states: `uploaded -> processing -> ready | failed`.
- Readiness endpoint for PostgreSQL and Milvus; liveness remains independent.

## Verification

- 58 unit/integration tests pass without API keys or external services.
- Alembic upgrade was executed successfully against a temporary SQLite database.
- Python compilation and Docker Compose configuration validation pass.
- Live Docker verification passed: PostgreSQL, Milvus, etcd, MinIO, and the API
  are healthy.
- Alembic applied revision `20260916_0001` to PostgreSQL and both
  `alembic_version` and `documents` exist.
- `/health/live`, `/health/ready`, and `/documents` returned successful responses;
  readiness reported both PostgreSQL and Milvus as `ok`.
- A real PDF upload was not executed because no PDF test file exists in the
  workspace; the upload/index lifecycle is covered by the integration test with
  external embedding and Milvus calls replaced.

## Runtime behavior

The MVP processes uploads synchronously. A successful response is `ready`; a
parse or index failure is persisted as `failed` with a safe message suitable for
the UI. Background jobs and retry scheduling remain V2 work.

## Current addendum (2026-09-18)

- The configured limit is now 75 MiB (`78,643,200` bytes) in the frontend,
  FastAPI, Docker configuration, and Nginx; Nginx allows 76 MiB for multipart overhead.
- A 69.89 MiB text PDF was parsed successfully in a direct parser check (46 pages;
  text found on 9 of the first 10 sampled pages). Full indexing was not used as a
  latency test because ingestion is still synchronous.
- A 51.2 MiB scanned PDF reached the API successfully and was persisted as `failed`
  with `PDF does not contain extractable text`. This confirms lifecycle/error handling,
  not OCR support.
- The frontend now shows file size and backend error details instead of only a generic
  `Request failed` message.
