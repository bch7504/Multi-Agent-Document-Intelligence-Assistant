"""Quiz library and attempt contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from backend.app.schemas.assistant import QuizQuestion
from backend.app.schemas.base import ApiModel


class QuizSummary(ApiModel):
    id: UUID
    run_id: UUID
    conversation_id: UUID
    title: str = Field(min_length=1, max_length=255)
    question_count: int = Field(ge=1)
    attempt_count: int = Field(ge=0)
    best_score_percent: float | None = Field(default=None, ge=0, le=100)
    created_at: datetime
    updated_at: datetime


class QuizList(ApiModel):
    items: list[QuizSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class QuizRead(ApiModel):
    id: UUID
    run_id: UUID
    conversation_id: UUID
    title: str
    questions: list[QuizQuestion] = Field(min_length=1)
    created_at: datetime
    updated_at: datetime


class QuizAttemptCreate(ApiModel):
    answers: dict[str, str] = Field(min_length=1)

    @field_validator("answers")
    @classmethod
    def normalize_answers(cls, answers: dict[str, str]) -> dict[str, str]:
        normalized = {
            str(question_id).strip(): str(option_id).strip()
            for question_id, option_id in answers.items()
            if str(question_id).strip() and str(option_id).strip()
        }
        if len(normalized) != len(answers):
            raise ValueError("Question and option IDs must not be blank")
        return normalized


class QuizAttemptRead(ApiModel):
    id: UUID
    quiz_id: UUID
    answers: dict[str, str]
    correct_count: int = Field(ge=0)
    total_questions: int = Field(ge=1)
    score_percent: float = Field(ge=0, le=100)
    created_at: datetime


class QuizAttemptList(ApiModel):
    items: list[QuizAttemptRead]
    total: int = Field(ge=0)
