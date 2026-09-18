"""Conversation history queries and lifecycle operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from backend.app.models.assistant_run import AssistantRunRecord
from backend.app.models.conversation import ConversationRecord
from backend.app.models.document import utc_now
from backend.app.models.message import MessageRecord
from backend.app.models.quiz import QuizAttemptRecord, QuizRecord
from backend.app.schemas.conversations import ConversationSummary


class ConversationNotFoundError(LookupError):
    pass


class ConversationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, limit: int, offset: int) -> tuple[list[ConversationSummary], int]:
        records = list(
            self.session.scalars(
                select(ConversationRecord)
                .order_by(ConversationRecord.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        counts = dict(
            self.session.execute(
                select(MessageRecord.conversation_id, func.count(MessageRecord.id))
                .where(MessageRecord.conversation_id.in_([item.id for item in records]))
                .group_by(MessageRecord.conversation_id)
            ).all()
        ) if records else {}
        items = [
            ConversationSummary(
                id=record.id,
                title=record.title,
                message_count=int(counts.get(record.id, 0)),
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
        total = self.session.scalar(select(func.count()).select_from(ConversationRecord)) or 0
        return items, int(total)

    def get(self, conversation_id: UUID) -> ConversationRecord:
        record = self.session.get(ConversationRecord, conversation_id)
        if record is None:
            raise ConversationNotFoundError(
                f"Conversation '{conversation_id}' was not found"
            )
        return record

    def messages(self, conversation_id: UUID) -> list[MessageRecord]:
        self.get(conversation_id)
        return list(
            self.session.scalars(
                select(MessageRecord)
                .where(MessageRecord.conversation_id == conversation_id)
                .order_by(
                    MessageRecord.created_at.asc(),
                    case((MessageRecord.role == "user", 0), else_=1),
                    MessageRecord.id.asc(),
                )
            )
        )

    def rename(self, conversation_id: UUID, title: str) -> ConversationRecord:
        record = self.get(conversation_id)
        record.title = title.strip()[:255]
        record.updated_at = utc_now()
        self.session.commit()
        self.session.refresh(record)
        return record

    def delete(self, conversation_id: UUID) -> None:
        record = self.get(conversation_id)
        quiz_ids = select(QuizRecord.id).where(
            QuizRecord.conversation_id == conversation_id
        )
        self.session.execute(
            delete(QuizAttemptRecord).where(QuizAttemptRecord.quiz_id.in_(quiz_ids))
        )
        self.session.execute(
            delete(QuizRecord).where(QuizRecord.conversation_id == conversation_id)
        )
        self.session.execute(
            delete(AssistantRunRecord).where(
                AssistantRunRecord.conversation_id == conversation_id
            )
        )
        self.session.execute(
            delete(MessageRecord).where(MessageRecord.conversation_id == conversation_id)
        )
        self.session.delete(record)
        self.session.commit()
