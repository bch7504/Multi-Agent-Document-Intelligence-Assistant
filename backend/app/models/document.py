"""PostgreSQL model for the document ingestion lifecycle."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.postgres import Base
from backend.app.schemas.documents import DocumentSourceType, DocumentStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentSourceType.UPLOAD.value,
    )
    source_uri: Mapped[str | None] = mapped_column(String(2_048))
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
        index=True,
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    sections: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
