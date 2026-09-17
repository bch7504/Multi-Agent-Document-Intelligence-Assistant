"""Shared state contract for the multi-agent assistant graph."""

from typing import Literal, TypedDict
from uuid import UUID

from backend.app.rag.schemas import RetrievedChunk
from backend.app.schemas.assistant import (
    AssistantRunRequest,
    AssistantRunResponse,
    Citation,
    QuizResult,
    ResolvedAssistantTask,
    TraceStep,
)
from backend.app.services.summary import SummaryMapDraft
from backend.app.services.quiz import QuizDraft


MAX_CHECKPOINT_MESSAGES = 12


def merge_history(
    existing: list[dict[str, str]],
    updates: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Append conversation messages while bounding short-term memory."""
    return [*existing, *updates][-MAX_CHECKPOINT_MESSAGES:]


class AssistantGraphState(TypedDict, total=False):
    request: AssistantRunRequest
    started_at: float
    history: list[dict[str, str]]
    resolved_task: ResolvedAssistantTask
    retrieval_query: str
    chunks: list[RetrievedChunk]
    answer: str
    cited_chunk_ids: list[UUID]
    map_drafts: list[SummaryMapDraft]
    quiz_draft: QuizDraft
    quiz: QuizResult
    citations: list[Citation]
    validation_passed: bool
    review_status: Literal["pass", "fail"]
    review_feedback: str | None
    retry_target: Literal["generation", "retrieval"]
    retry_count: int
    trace: list[TraceStep]
    response: AssistantRunResponse
