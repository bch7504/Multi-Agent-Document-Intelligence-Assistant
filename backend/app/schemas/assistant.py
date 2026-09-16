"""Contracts for QA, summary, quiz, citations, and review output."""

from enum import Enum
from uuid import UUID

from pydantic import Field, field_validator

from backend.app.schemas.base import ApiModel


class AssistantTask(str, Enum):
    AUTO = "auto"
    QA = "qa"
    SUMMARY = "summary"
    QUIZ = "quiz"


class ResolvedAssistantTask(str, Enum):
    QA = "qa"
    SUMMARY = "summary"
    QUIZ = "quiz"


class ReviewStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class TraceStatus(str, Enum):
    COMPLETE = "complete"
    RUNNING = "running"
    FAILED = "failed"


class AssistantRunRequest(ApiModel):
    conversation_id: UUID
    document_ids: list[UUID] = Field(min_length=1)
    task: AssistantTask = AssistantTask.AUTO
    message: str = Field(min_length=1, max_length=20_000)

    @field_validator("document_ids")
    @classmethod
    def document_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("document_ids must not contain duplicates")
        return value

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class Citation(ApiModel):
    document_id: UUID
    document_name: str = Field(min_length=1, max_length=255)
    page_number: int | None = Field(default=None, ge=1)
    chunk_id: UUID
    excerpt: str = Field(min_length=1, max_length=2_000)
    source_uri: str | None = Field(default=None, max_length=2_048)


class ReviewResult(ApiModel):
    status: ReviewStatus
    retry_count: int = Field(ge=0, le=2)
    feedback: str | None = None


class TraceStep(ApiModel):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    detail: str = Field(default="", max_length=2_000)
    duration_ms: int = Field(ge=0)
    status: TraceStatus


class AssistantRunResponse(ApiModel):
    run_id: UUID
    task: ResolvedAssistantTask
    answer: str = Field(min_length=1)
    citations: list[Citation]
    review: ReviewResult
    trace: list[TraceStep] = Field(default_factory=list)
