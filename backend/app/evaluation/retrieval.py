"""Provider-independent retrieval metrics with silver and gold qrel support."""

import json
import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from uuid import UUID

from backend.app.rag.schemas import RetrievedChunk


@dataclass(frozen=True)
class RetrievalCase:
    id: str
    question: str
    expected_phrases: tuple[str, ...] = ()
    relevant_chunk_ids: tuple[UUID, ...] = ()
    document_ids: tuple[UUID, ...] = ()

    @property
    def evaluation_mode(self) -> str:
        return "gold_qrel" if self.relevant_chunk_ids else "silver_phrase"


@dataclass(frozen=True)
class CaseResult:
    id: str
    evaluation_mode: str
    hit_at_k: float
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    retrieved_count: int
    latency_ms: float


@dataclass(frozen=True)
class MetricSlice:
    case_count: int
    hit_rate_at_k: float
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg_at_k: float
    mean_latency_ms: float
    p95_latency_ms: float


@dataclass(frozen=True)
class BenchmarkReport:
    case_count: int
    gold_case_count: int
    silver_case_count: int
    k: int
    hit_rate_at_k: float
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg_at_k: float
    mean_latency_ms: float
    p95_latency_ms: float
    gold_metrics: MetricSlice | None
    silver_metrics: MetricSlice | None
    cases: tuple[CaseResult, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _uuid_tuple(values, field_name: str, case_id: str) -> tuple[UUID, ...]:
    parsed: list[UUID] = []
    for value in values or ():
        try:
            parsed.append(UUID(str(value)))
        except ValueError as error:
            raise ValueError(
                f"Benchmark case '{case_id}' has invalid UUID in {field_name}"
            ) from error
    return tuple(dict.fromkeys(parsed))


def load_cases(path: Path) -> list[RetrievalCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Benchmark dataset must be a non-empty JSON list")

    cases: list[RetrievalCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise ValueError(f"Benchmark case at index {index} must be an object")
        case_id = str(raw.get("id") or "").strip()
        question = str(raw.get("question") or "").strip()
        phrases = tuple(
            phrase
            for item in raw.get("expected_phrases") or []
            if (phrase := str(item).strip())
        )
        relevant_chunk_ids = _uuid_tuple(
            raw.get("relevant_chunk_ids"),
            "relevant_chunk_ids",
            case_id,
        )
        document_ids = _uuid_tuple(raw.get("document_ids"), "document_ids", case_id)
        if not case_id or not question or not (phrases or relevant_chunk_ids):
            raise ValueError(
                f"Benchmark case at index {index} requires id, question, and either "
                "expected_phrases or relevant_chunk_ids"
            )
        if case_id in seen_ids:
            raise ValueError(f"Duplicate benchmark id: {case_id}")
        seen_ids.add(case_id)
        cases.append(
            RetrievalCase(
                id=case_id,
                question=question,
                expected_phrases=phrases,
                relevant_chunk_ids=relevant_chunk_ids,
                document_ids=document_ids,
            )
        )
    return cases


def _ndcg(relevance: list[bool], relevant_total: int, k: int) -> float:
    dcg = sum(
        1 / math.log2(rank + 1)
        for rank, is_relevant in enumerate(relevance, start=1)
        if is_relevant
    )
    ideal_count = min(relevant_total, k)
    idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / idcg if idcg else 0.0


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _metric_slice(results: list[CaseResult]) -> MetricSlice | None:
    if not results:
        return None
    latencies = [result.latency_ms for result in results]
    return MetricSlice(
        case_count=len(results),
        hit_rate_at_k=mean(result.hit_at_k for result in results),
        mean_precision_at_k=mean(result.precision_at_k for result in results),
        mean_recall_at_k=mean(result.recall_at_k for result in results),
        mean_reciprocal_rank=mean(result.reciprocal_rank for result in results),
        mean_ndcg_at_k=mean(result.ndcg_at_k for result in results),
        mean_latency_ms=mean(latencies),
        p95_latency_ms=_percentile_95(latencies),
    )


def evaluate_retrieval(
    cases: list[RetrievalCase],
    retrieve: Callable[[str], list[RetrievedChunk]],
    k: int = 5,
    retrieve_scoped: Callable[[str, tuple[UUID, ...]], list[RetrievedChunk]] | None = None,
) -> BenchmarkReport:
    if not cases:
        raise ValueError("At least one benchmark case is required")
    if k < 1:
        raise ValueError("k must be positive")

    results: list[CaseResult] = []
    for case in cases:
        started = perf_counter()
        if case.document_ids and retrieve_scoped is not None:
            retrieved = retrieve_scoped(case.question, case.document_ids)
        else:
            retrieved = retrieve(case.question)
        chunks = sorted(retrieved, key=lambda item: item.rank)[:k]
        latency_ms = round((perf_counter() - started) * 1_000, 3)

        if case.relevant_chunk_ids:
            relevant_ids = set(case.relevant_chunk_ids)
            relevance = [chunk.chunk_id in relevant_ids for chunk in chunks]
            relevant_found = len(
                {chunk.chunk_id for chunk in chunks if chunk.chunk_id in relevant_ids}
            )
            recall = relevant_found / len(relevant_ids)
            relevant_total = len(relevant_ids)
        else:
            contents = [_normalize(chunk.content) for chunk in chunks]
            expected = list(
                dict.fromkeys(_normalize(phrase) for phrase in case.expected_phrases)
            )
            matched_phrases: set[int] = set()
            relevance: list[bool] = []
            for content in contents:
                newly_matched = {
                    index
                    for index, phrase in enumerate(expected)
                    if index not in matched_phrases and phrase in content
                }
                relevance.append(bool(newly_matched))
                matched_phrases.update(newly_matched)
            recall = len(matched_phrases) / len(expected)
            relevant_total = len(expected)

        first_relevant_rank = next(
            (rank for rank, is_relevant in enumerate(relevance, start=1) if is_relevant),
            None,
        )
        results.append(
            CaseResult(
                id=case.id,
                evaluation_mode=case.evaluation_mode,
                hit_at_k=float(any(relevance)),
                precision_at_k=sum(relevance) / k,
                recall_at_k=recall,
                reciprocal_rank=(
                    1 / first_relevant_rank if first_relevant_rank is not None else 0.0
                ),
                ndcg_at_k=_ndcg(relevance, relevant_total, k),
                retrieved_count=len(chunks),
                latency_ms=latency_ms,
            )
        )

    latencies = [result.latency_ms for result in results]
    gold_count = sum(case.evaluation_mode == "gold_qrel" for case in cases)
    gold_results = [result for result in results if result.evaluation_mode == "gold_qrel"]
    silver_results = [
        result for result in results if result.evaluation_mode == "silver_phrase"
    ]
    return BenchmarkReport(
        case_count=len(results),
        gold_case_count=gold_count,
        silver_case_count=len(results) - gold_count,
        k=k,
        hit_rate_at_k=mean(result.hit_at_k for result in results),
        mean_precision_at_k=mean(result.precision_at_k for result in results),
        mean_recall_at_k=mean(result.recall_at_k for result in results),
        mean_reciprocal_rank=mean(result.reciprocal_rank for result in results),
        mean_ndcg_at_k=mean(result.ndcg_at_k for result in results),
        mean_latency_ms=mean(latencies),
        p95_latency_ms=_percentile_95(latencies),
        gold_metrics=_metric_slice(gold_results),
        silver_metrics=_metric_slice(silver_results),
        cases=tuple(results),
    )
