"""Conversation history API contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from backend.app.schemas.base import ApiModel


class ConversationSummary(ApiModel):
    id: UUID
    title: str | None = Field(default=None, max_length=255)
    message_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class ConversationList(ApiModel):
    items: list[ConversationSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ConversationUpdate(ApiModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, title: str) -> str:
        title = title.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title


class MessageRead(ApiModel):
    id: UUID
    conversation_id: UUID
    role: str = Field(pattern="^(user|assistant)$")
    content: str
    task: str | None = None
    created_at: datetime


class MessageList(ApiModel):
    items: list[MessageRead]
    total: int = Field(ge=0)
