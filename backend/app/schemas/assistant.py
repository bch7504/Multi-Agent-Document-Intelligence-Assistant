"""Contracts for QA, summary, quiz, citations, and review output."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.base import ApiModel
from backend.app.schemas.models import ModelProvider


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
    llm_provider: ModelProvider | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=255)
    embedding_provider: ModelProvider | None = None
    embedding_model: str | None = Field(default=None, min_length=1, max_length=255)

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

    @model_validator(mode="after")
    def model_selections_must_be_complete(self):
        pairs = (
            ("llm", self.llm_provider, self.llm_model),
            ("embedding", self.embedding_provider, self.embedding_model),
        )
        for label, provider, model in pairs:
            if (provider is None) != (model is None):
                raise ValueError(f"{label}_provider and {label}_model must be supplied together")
            if model is not None:
                normalized = model.strip()
                if not normalized:
                    raise ValueError(f"{label}_model must not be blank")
                if label == "llm":
                    self.llm_model = normalized
                else:
                    self.embedding_model = normalized
        return self


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


class UsageStats(ApiModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class QuizOption(ApiModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=1_000)


class QuizQuestion(ApiModel):
    id: str = Field(min_length=1, max_length=50)
    question: str = Field(min_length=1, max_length=2_000)
    options: list[QuizOption] = Field(min_length=2, max_length=6)
    correct_option_id: str = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=1, max_length=2_000)
    citations: list[Citation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_options(self):
        option_ids = [option.id for option in self.options]
        option_texts = [option.text.casefold().strip() for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("quiz option IDs must be unique")
        if len(option_texts) != len(set(option_texts)):
            raise ValueError("quiz option texts must be unique")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must identify one option")
        return self


class QuizResult(ApiModel):
    questions: list[QuizQuestion] = Field(min_length=1, max_length=20)


class AssistantRunResponse(ApiModel):
    run_id: UUID
    task: ResolvedAssistantTask
    answer: str = Field(min_length=1)
    citations: list[Citation]
    quiz: QuizResult | None = None
    review: ReviewResult
    trace: list[TraceStep] = Field(default_factory=list)
    usage: UsageStats = Field(default_factory=UsageStats)


class AssistantRunAudit(AssistantRunResponse):
    conversation_id: UUID
    document_ids: list[UUID]
    created_at: datetime
