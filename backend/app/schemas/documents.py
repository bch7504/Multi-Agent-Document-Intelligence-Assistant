"""Document lifecycle contracts shared by API and services."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from backend.app.schemas.base import ApiModel


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentSourceType(str, Enum):
    UPLOAD = "upload"
    URL = "url"
    JSON = "json"


class DocumentRead(ApiModel):
    id: UUID
    name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=255)
    source_type: DocumentSourceType
    source_uri: str | None = Field(default=None, max_length=2_048)
    checksum: str = Field(min_length=64, max_length=64)
    status: DocumentStatus
    page_count: int | None = Field(default=None, ge=0)
    chunk_count: int | None = Field(default=None, ge=0)
    embedding_model: str | None = Field(default=None, max_length=255)
    error_message: str | None = Field(default=None, max_length=1_000)
    created_at: datetime
    updated_at: datetime


class DocumentList(ApiModel):
    items: list[DocumentRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
