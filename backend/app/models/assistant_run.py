"""Persistent assistant run, review, trace, and citation audit record."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.postgres import Base
from backend.app.models.document import utc_now


class AssistantRunRecord(Base):
    __tablename__ = "assistant_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    review_feedback: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, nullable=False)
    trace: Mapped[list] = mapped_column(JSON, nullable=False)
    quiz: Mapped[dict | None] = mapped_column(JSON)
    usage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
