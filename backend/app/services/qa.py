"""Grounded QA baseline with scoped retrieval and bounded context."""

import os
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.app.agents.retrieval.qa_prompt import QA_SYSTEM_PROMPT, build_qa_prompt
from backend.app.rag.schemas import RetrievedChunk
from backend.app.schemas.assistant import (
    AssistantRunRequest,
    AssistantRunResponse,
    AssistantTask,
    ResolvedAssistantTask,
    ReviewResult,
    ReviewStatus,
    TraceStatus,
    TraceStep,
)
from backend.app.services.citations import (
    CitationValidationError,
    citations_from_chunks,
    validate_citations,
)
from backend.app.services.retrieval import retrieve_chunks
from backend.app.services.query_rewrite import rewrite_query


class InsufficientContextError(RuntimeError):
    """Raised when no retrieved evidence is available inside request scope."""


class GroundedAnswerDraft(BaseModel):
    answer: str = Field(min_length=1)
    cited_chunk_ids: list[UUID] = Field(min_length=1)


DEFAULT_CONTEXT_CHUNKS = 6
DEFAULT_CONTEXT_CHARACTERS = 24_000


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _select_context(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Deduplicate ranked candidates and keep the prompt context bounded."""
    max_chunks = _positive_int_env("CONTEXT_MAX_CHUNKS", DEFAULT_CONTEXT_CHUNKS)
    character_budget = _positive_int_env(
        "CONTEXT_MAX_CHARACTERS",
        DEFAULT_CONTEXT_CHARACTERS,
    )
    selected: list[RetrievedChunk] = []
    seen: set[UUID] = set()
    used_characters = 0
    for chunk in sorted(chunks, key=lambda item: item.rank):
        if chunk.chunk_id in seen:
            continue
        if selected and used_characters + len(chunk.content) > character_budget:
            continue
        selected.append(chunk)
        seen.add(chunk.chunk_id)
        used_characters += len(chunk.content)
        if len(selected) >= max_chunks:
            break
    return selected


def _format_evidence(chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for chunk in chunks:
        page = str(chunk.page_number) if chunk.page_number is not None else "n/a"
        blocks.append(
            "\n".join(
                (
                    f"<evidence chunk_id=\"{chunk.chunk_id}\" "
                    f"document_id=\"{chunk.document_id}\" page=\"{page}\">",
                    chunk.content,
                    "</evidence>",
                )
            )
        )
    return "\n\n".join(blocks)


def _select_cited_chunks(
    chunks: list[RetrievedChunk],
    cited_chunk_ids: list[UUID],
) -> list[RetrievedChunk]:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    unknown = [chunk_id for chunk_id in cited_chunk_ids if chunk_id not in by_id]
    if unknown:
        raise CitationValidationError(
            "Model selected chunk IDs that were not retrieved: "
            + ", ".join(str(chunk_id) for chunk_id in unknown)
        )
    return [by_id[chunk_id] for chunk_id in dict.fromkeys(cited_chunk_ids)]


def answer_question(
    request: AssistantRunRequest,
    retriever: Any,
    llm: Any,
    history: list[dict[str, str]] | None = None,
) -> AssistantRunResponse:
    """Run retrieval, structured generation, and deterministic citation review."""
    if request.task not in {AssistantTask.AUTO, AssistantTask.QA}:
        raise ValueError("The QA baseline only accepts task 'auto' or 'qa'")

    run_started = perf_counter()
    retrieval_query = request.message
    rewrite_ms = 0
    if history:
        rewrite_started = perf_counter()
        retrieval_query = rewrite_query(request.message, history, llm)
        rewrite_ms = round((perf_counter() - rewrite_started) * 1_000)
    retrieval_started = perf_counter()
    retrieved = retrieve_chunks(
        retriever,
        retrieval_query,
        document_ids=request.document_ids,
    )
    scoped_chunks = _select_context(retrieved)
    retrieval_ms = round((perf_counter() - retrieval_started) * 1_000)
    if not scoped_chunks:
        raise InsufficientContextError(
            "No retrieved evidence belongs to the selected documents"
        )

    generation_started = perf_counter()
    structured_llm = llm.with_structured_output(GroundedAnswerDraft)
    raw_draft = structured_llm.invoke(
        [
            ("system", QA_SYSTEM_PROMPT),
            ("human", build_qa_prompt(request.message, _format_evidence(scoped_chunks))),
        ]
    )
    draft = GroundedAnswerDraft.model_validate(raw_draft)
    generation_ms = round((perf_counter() - generation_started) * 1_000)

    review_started = perf_counter()
    cited_chunks = _select_cited_chunks(scoped_chunks, draft.cited_chunk_ids)
    citations = citations_from_chunks(cited_chunks)
    validate_citations(citations, scoped_chunks, request.document_ids)
    review_ms = round((perf_counter() - review_started) * 1_000)

    return AssistantRunResponse(
        run_id=uuid4(),
        task=ResolvedAssistantTask.QA,
        answer=draft.answer.strip(),
        citations=citations,
        review=ReviewResult(status=ReviewStatus.PASS, retry_count=0),
        trace=[
            *(
                [
                    TraceStep(
                        id="rewrite_query",
                        label="Query rewrite",
                        detail=f"Standalone retrieval query: {retrieval_query}",
                        duration_ms=rewrite_ms,
                        status=TraceStatus.COMPLETE,
                    )
                ]
                if history
                else []
            ),
            TraceStep(
                id="retrieve",
                label="Structured retrieval",
                detail=f"{len(scoped_chunks)} chunks inside document scope",
                duration_ms=retrieval_ms,
                status=TraceStatus.COMPLETE,
            ),
            TraceStep(
                id="generate",
                label="Grounded QA",
                detail="Structured answer draft generated",
                duration_ms=generation_ms,
                status=TraceStatus.COMPLETE,
            ),
            TraceStep(
                id="review",
                label="Citation validation",
                detail=f"PASS · {len(citations)} citations",
                duration_ms=review_ms,
                status=TraceStatus.COMPLETE,
            ),
            TraceStep(
                id="total",
                label="Total",
                detail="QA baseline completed",
                duration_ms=round((perf_counter() - run_started) * 1_000),
                status=TraceStatus.COMPLETE,
            ),
        ],
    )
