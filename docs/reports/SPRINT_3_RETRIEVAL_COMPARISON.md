# Sprint 3 Retrieval Comparison

Run date: 2026-09-16

## Configuration

- Corpus: StackAI documentation snapshot in `data/stack_ai.json`
- Indexed chunks: 179
- Milvus collection: `data_test`
- Embedding: OpenRouter `openai/text-embedding-3-small`
- Dataset: `stack_ai_retrieval_v2.json`, containing 20 manually reviewed gold
  qrels and 20 project-aligned silver cases covering document ingestion,
  retrieval, citations, memory, providers, security, orchestration, and tracing
- Cutoff: K = 5
- Candidate pool: 20
- Hybrid ranker: RRF with K = 60

## Live comparison

| Profile | Hit Rate@5 | Precision@5 | Recall@5 | MRR | nDCG@5 | Mean latency | P95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense only | 0.8750 | 0.2000 | 0.8250 | 0.7396 | 0.6370 | 777.04 ms | 954.54 ms |
| BM25 only | 0.9250 | 0.2150 | 0.8500 | 0.7329 | 0.6563 | **7.69 ms** | **8.90 ms** |
| Hybrid RRF | **0.9500** | **0.2250** | **0.9000** | **0.8133** | **0.7191** | 823.28 ms | 1396.77 ms |

The single-field profiles execute true dense-only and BM25-only searches. BM25
does not call the embedding API; dense and hybrid do.

## Decision

`hybrid_rrf` remains the production default because it has the best Hit Rate,
Precision, Recall, MRR, and nDCG. Compared with dense-only it improves MRR by
about 10.0% and nDCG@5 by about 12.9% in this run.
BM25-only remains useful as a low-latency, no-embedding fallback, but its recall
and ranking quality are lower.

## Gold and silver interpretation

| Hybrid RRF slice | Cases | Hit Rate@5 | Precision@5 | Recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| Gold qrels | 20 | 1.0000 | 0.2400 | 0.9750 | 0.8017 | 0.8266 |
| Project-aligned silver | 20 | 0.9000 | 0.2100 | 0.8250 | 0.8250 | 0.6117 |

The earlier aggregate score was artificially low because 11 of the 20 legacy
silver cases expected phrases that no longer existed in the current corpus.
Those cases produced unavoidable zero-hit results. The replacement silver set
now targets this project's required capabilities rather than a random sampling
of product documentation. The Sprint 1 file
`stack_ai_retrieval_v1.json` is now frozen for historical reproducibility;
`stack_ai_retrieval_v2.json` is the active current-corpus benchmark.

The two current Hybrid zero-hit silver cases are `local-model-hosting` and
`observability-traces`. Their expected evidence exists in the corpus, so they
are retained as valid hard cases rather than edited to inflate the score.

Precision@5 must be interpreted against label density. Fifteen gold cases have
one relevant chunk and five have two, so even perfect retrieval has a maximum
mean Precision@5 of 0.25. The measured gold Precision@5 of 0.24 is therefore
96% of the dataset's attainable maximum, not a low precision result.

No external reranker is added in Sprint 3. The current evidence supports RRF,
but does not isolate enough additional gain from reranking to justify another
model call, operational dependency, and latency budget. A reranker should be
reconsidered only with a dedicated ablation on real uploaded PDF corpora.

## Query rewrite

Follow-up questions can now be rewritten into standalone retrieval queries.
History is restricted to user/assistant roles, six recent turns, and 6,000
characters. The rewrite step is skipped when no history is supplied and is
recorded in the assistant trace when used.

## Verification

- All 65 unit/integration tests pass.
- Live comparison completed against Milvus using the same dataset and K for all profiles.
- Docker services from Sprint 2 remain healthy.
- RAGAS is intentionally deferred to Sprint 6, where generated-answer quality
  and faithfulness will be evaluated in addition to retrieval quality.
