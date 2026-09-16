"""Internal retrieval contracts independent from a vector-store provider."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RetrievedChunk(BaseModel):
    """Normalized evidence returned by any retrieval implementation."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    document_id: UUID
    content: str = Field(min_length=1)
    source_name: str = Field(min_length=1, max_length=255)
    source_uri: str | None = Field(default=None, max_length=2_048)
    page_number: int | None = Field(default=None, ge=1)
    chunk_index: int | None = Field(default=None, ge=0)
    rank: int = Field(ge=1)
    score: float | None = None
