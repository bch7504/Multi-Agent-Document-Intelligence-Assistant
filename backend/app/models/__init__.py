"""Persistence models exported for SQLAlchemy metadata discovery."""

from backend.app.models.assistant_run import AssistantRunRecord
from backend.app.models.conversation import ConversationRecord
from backend.app.models.document import DocumentRecord
from backend.app.models.message import MessageRecord
from backend.app.models.quiz import QuizAttemptRecord, QuizRecord

__all__ = [
    "AssistantRunRecord",
    "ConversationRecord",
    "DocumentRecord",
    "MessageRecord",
    "QuizAttemptRecord",
    "QuizRecord",
]
