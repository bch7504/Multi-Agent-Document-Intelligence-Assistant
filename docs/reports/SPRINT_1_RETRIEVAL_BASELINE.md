# Sprint 1 Retrieval Baseline

Run date: 2026-09-15

## Configuration

- Corpus: current Stack AI `llms-full.txt`
- Indexed chunks: 179
- Milvus collection: `data_test`
- Retrieval profile: dense vector + native BM25 + RRF (`dense_bm25_v1`)
- Embedding provider: OpenRouter
- Embedding model: `openai/text-embedding-3-small`
- Dense vector dimensions: 1536
- Evaluation dataset: `stack_ai_retrieval_v1.json`
- Evaluation cases: 20 silver phrase cases, 0 manually reviewed gold qrels
- Retrieval cutoff: K = 5

## Results

| Metric | Result |
|---|---:|
| Hit Rate@5 | 0.4500 |
| Mean Precision@5 | 0.0900 |
| Mean Recall@5 | 0.3250 |
| Mean Reciprocal Rank | 0.3750 |
| Mean nDCG@5 | 0.2542 |
| Mean latency | 676.38 ms |
| P95 latency | 806.98 ms |

Nine of twenty silver cases found at least one expected phrase in the top five
chunks. The remaining eleven cases scored zero under phrase matching.

## Interpretation

This is a reproducible first baseline, not a production quality target. The
dataset was written for an older snapshot of the Stack AI documentation while
the corpus was crawled from the current documentation. A zero score can
therefore mean either a retrieval miss or that the expected phrase/page no
longer exists in the current corpus.

Before using these numbers for retrieval tuning:

1. Review the zero-hit cases against the current corpus.
2. Replace stale expected phrases.
3. Add manually reviewed `relevant_chunk_ids` as gold qrels.
4. Compare vector-only, BM25-only and hybrid retrieval on the same snapshot.

The benchmark implementation was also corrected during this run so repeated
occurrences of one silver phrase cannot produce nDCG greater than 1.

An end-to-end smoke test also completed successfully with OpenRouter chat:
scoped retrieval returned six chunks, structured generation completed, three
backend-built citations passed deterministic validation, and review status was
`PASS`.
