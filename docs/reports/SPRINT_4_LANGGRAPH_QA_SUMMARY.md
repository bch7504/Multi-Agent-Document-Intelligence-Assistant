# Sprint 4 LangGraph QA and Summary

Run date: 2026-09-17

## Implemented

- One compiled LangGraph serves QA and Summary through
  `POST /api/v1/assistant/runs`.
- Explicit `qa` and `summary` tasks bypass the LLM task resolver.
- `auto` uses structured output restricted to the two supported Sprint 4 tasks.
- QA path: query rewrite, document-scoped retrieval, structured grounded answer,
  deterministic citation validation, response finalization.
- Summary path: scope resolution, document-scoped retrieval, bounded map batches,
  reduce synthesis, deterministic citation validation, response finalization.
- An in-process LangGraph checkpointer uses `conversationId` as `thread_id` and
  keeps at most 12 messages while supplying bounded history to follow-up query
  rewriting.
- Checkpoint serialization uses an explicit type allowlist and passes with
  strict msgpack enabled.
- PostgreSQL validates that every selected document exists and is `ready`
  before graph execution.
- Trace steps expose the exact nodes traversed, their result summary, and timing.

## Routing

```text
START
  ├─ task=qa ──────────────────────> rewrite -> retrieve -> answer
  ├─ task=summary ─────────────────> scope -> retrieve -> map -> reduce
  └─ task=auto -> structured router ─┬─> QA path
                                     └─> Summary path

QA/Summary -> validate citations -> finalize -> END
```

`task=quiz` returns an explicit unsupported-task error until Sprint 5.

## API contract

```http
POST /api/v1/assistant/runs
Content-Type: application/json
```

```json
{
  "conversationId": "00000000-0000-0000-0000-000000000001",
  "documentIds": ["00000000-0000-0000-0000-000000000002"],
  "task": "summary",
  "message": "Summarize the selected document"
}
```

The response contains `runId`, resolved `task`, `answer`, verified `citations`,
`review`, and the graph `trace`.

## Verification

- All 74 unit and integration tests pass.
- Explicit QA routing is verified to skip the task resolver.
- Auto Summary is verified to traverse map and reduce nodes.
- A repeated `conversationId` is verified to use checkpointed history for query
  rewriting.
- Missing and non-ready documents are rejected before graph invocation.
- Python compilation and strict LangGraph checkpoint serialization pass.
- Docker Compose rebuilt successfully; API, PostgreSQL, and Milvus readiness
  checks all report healthy.
- Live OpenRouter smoke test against the existing `data_test` collection passed:
  QA returned 3 verified citations and Summary returned 6 verified citations.
  Their trace paths matched the compiled graph exactly.

## Deferred to Sprint 5

- Persistent conversations, messages, runs, and checkpoints in PostgreSQL.
- Quiz generation, LLM reviewer, bounded retry, and expanded guardrails.

## Current addendum (2026-09-18)

Sprint 5 added Quiz and the common reviewer/retry path. Sprint 8 extended `auto`
routing to all three tasks (`qa`, `summary`, `quiz`) and made Auto the default in
the production frontend while retaining explicit task tabs as overrides.

Selected-document Summary no longer summarizes only top retrieval hits. It loads
all indexed chunks for the selected documents in source order, then chooses a
single-pass or bounded map/reduce strategy from the context size. A live one-document
Security summary loaded all 19 chunks, returned 17 scoped citations, and passed review.
