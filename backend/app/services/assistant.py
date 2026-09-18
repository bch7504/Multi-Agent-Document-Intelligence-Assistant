"""Application service for scoped execution and durable conversation memory."""

import logging
from functools import lru_cache
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.llm import create_llm
from backend.app.core.observability import log_event
from backend.app.graph.graph import AssistantGraphRuntime, create_assistant_runtime
from backend.app.guardrails.input import validate_assistant_input
from backend.app.models.assistant_run import AssistantRunRecord
from backend.app.models.conversation import ConversationRecord
from backend.app.models.document import DocumentRecord, utc_now
from backend.app.models.message import MessageRecord
from backend.app.models.quiz import QuizRecord
from backend.app.rag.hybrid_search import get_retriever
from backend.app.schemas.assistant import (
    AssistantRunAudit,
    AssistantRunRequest,
    AssistantRunResponse,
)
from backend.app.schemas.documents import DocumentStatus


class AssistantDocumentNotFoundError(LookupError):
    pass


class AssistantDocumentNotReadyError(RuntimeError):
    pass


class AssistantRunNotFoundError(LookupError):
    pass


class AssistantEmbeddingMismatchError(ValueError):
    pass


@lru_cache(maxsize=32)
def get_assistant_runtime(
    llm_provider: str | None = None,
    llm_model: str | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> AssistantGraphRuntime:
    """Build one process-local graph and checkpointer lazily."""
    settings = get_settings()
    retriever = get_retriever(
        collection_name=settings.document_collection_name,
        milvus_uri=settings.milvus_uri,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
    return create_assistant_runtime(
        retriever,
        create_llm(llm_provider, model_name=llm_model),
    )


class AssistantService:
    def __init__(
        self,
        session: Session,
        runtime: AssistantGraphRuntime | None = None,
    ) -> None:
        self.session = session
        self.runtime = runtime

    def _validate_documents(self, document_ids: list[UUID]) -> list[DocumentRecord]:
        records = list(
            self.session.scalars(
                select(DocumentRecord).where(DocumentRecord.id.in_(document_ids))
            )
        )
        by_id = {record.id: record for record in records}
        missing = [document_id for document_id in document_ids if document_id not in by_id]
        if missing:
            raise AssistantDocumentNotFoundError(
                "Selected documents were not found: "
                + ", ".join(str(document_id) for document_id in missing)
            )
        not_ready = [
            record.id
            for record in records
            if record.status != DocumentStatus.READY.value
        ]
        if not_ready:
            raise AssistantDocumentNotReadyError(
                "Selected documents are not ready: "
                + ", ".join(str(document_id) for document_id in not_ready)
            )
        return records

    @staticmethod
    def _embedding_for_run(
        request: AssistantRunRequest,
        records: list[DocumentRecord],
    ) -> tuple[str | None, str | None]:
        indexed_models = {
            record.embedding_model
            for record in records
            if record.embedding_model
        }
        if len(indexed_models) > 1:
            raise AssistantEmbeddingMismatchError(
                "Selected documents were indexed with different embedding models"
            )
        indexed = next(iter(indexed_models), None)
        requested = (
            f"{request.embedding_provider.value}:{request.embedding_model}"
            if request.embedding_provider and request.embedding_model
            else None
        )
        if indexed and requested and indexed != requested:
            raise AssistantEmbeddingMismatchError(
                f"Selected documents use '{indexed}', not '{requested}'. Re-index before changing embeddings."
            )
        effective = requested or indexed
        if not effective:
            return None, None
        provider, separator, model = effective.partition(":")
        if not separator or not model:
            raise AssistantEmbeddingMismatchError(
                f"Invalid stored embedding model '{effective}'"
            )
        return provider, model

    def _load_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        limit = get_settings().memory_max_messages
        if limit < 1:
            raise ValueError("MEMORY_MAX_MESSAGES must be positive")
        records = list(
            self.session.scalars(
                select(MessageRecord)
                .where(MessageRecord.conversation_id == conversation_id)
                .order_by(MessageRecord.created_at.desc())
                .limit(limit)
            )
        )
        return [
            {"role": record.role, "content": record.content}
            for record in reversed(records)
        ]

    def _persist_run(
        self,
        request: AssistantRunRequest,
        response: AssistantRunResponse,
    ) -> None:
        try:
            conversation = self.session.get(
                ConversationRecord, request.conversation_id
            )
            now = utc_now()
            if conversation is None:
                conversation = ConversationRecord(
                    id=request.conversation_id,
                    title=request.message[:255],
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(conversation)
                # These models intentionally do not expose ORM relationships.
                # Flush the parent explicitly so PostgreSQL can satisfy the
                # foreign keys of messages, runs, and quizzes below.
                self.session.flush()
            else:
                conversation.updated_at = now

            records = [
                MessageRecord(
                    conversation_id=request.conversation_id,
                    role="user",
                    content=request.message,
                    task=response.task.value,
                ),
                MessageRecord(
                    conversation_id=request.conversation_id,
                    role="assistant",
                    content=response.answer,
                    task=response.task.value,
                ),
                AssistantRunRecord(
                    id=response.run_id,
                    conversation_id=request.conversation_id,
                    task=response.task.value,
                    status=response.review.status.value,
                    answer=response.answer,
                    review_feedback=response.review.feedback,
                    retry_count=response.review.retry_count,
                    document_ids=[str(item) for item in request.document_ids],
                    citations=[
                        item.model_dump(mode="json", by_alias=True)
                        for item in response.citations
                    ],
                    trace=[
                        item.model_dump(mode="json", by_alias=True)
                        for item in response.trace
                    ],
                    quiz=(
                        response.quiz.model_dump(mode="json", by_alias=True)
                        if response.quiz is not None
                        else None
                    ),
                    usage=response.usage.model_dump(mode="json", by_alias=True),
                ),
            ]
            self.session.add_all(records)
            # A saved quiz references both the conversation and assistant run.
            # Persist those parents before inserting the quiz record.
            self.session.flush()
            if response.quiz is not None:
                self.session.add(
                    QuizRecord(
                        id=response.run_id,
                        run_id=response.run_id,
                        conversation_id=request.conversation_id,
                        title=request.message[:255],
                        questions=[
                            question.model_dump(mode="json", by_alias=True)
                            for question in response.quiz.questions
                        ],
                        created_at=now,
                        updated_at=now,
                    )
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def run(self, request: AssistantRunRequest) -> AssistantRunResponse:
        validate_assistant_input(request)
        records = self._validate_documents(request.document_ids)
        embedding_provider, embedding_model = self._embedding_for_run(
            request, records
        )
        history = self._load_history(request.conversation_id)
        runtime = self.runtime or get_assistant_runtime(
            request.llm_provider.value if request.llm_provider else None,
            request.llm_model,
            embedding_provider,
            embedding_model,
        )
        response = runtime.invoke(request, history=history)
        self._persist_run(request, response)
        total_step = next(
            (step for step in reversed(response.trace) if step.id == "total"),
            None,
        )
        log_event(
            logging.getLogger("document_assistant.assistant"),
            "assistant_run_complete",
            run_id=response.run_id,
            conversation_id=request.conversation_id,
            task=response.task.value,
            status=response.review.status.value,
            retry_count=response.review.retry_count,
            document_count=len(request.document_ids),
            citation_count=len(response.citations),
            duration_ms=total_step.duration_ms if total_step else None,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
        )
        return response

    def get_run(self, run_id: UUID) -> AssistantRunAudit:
        record = self.session.get(AssistantRunRecord, run_id)
        if record is None:
            raise AssistantRunNotFoundError(f"Assistant run '{run_id}' was not found")
        return AssistantRunAudit.model_validate(
            {
                "run_id": record.id,
                "conversation_id": record.conversation_id,
                "document_ids": record.document_ids,
                "task": record.task,
                "answer": record.answer,
                "citations": record.citations,
                "quiz": record.quiz,
                "review": {
                    "status": record.status,
                    "retry_count": record.retry_count,
                    "feedback": record.review_feedback,
                },
                "trace": record.trace,
                "usage": record.usage,
                "created_at": record.created_at,
            }
        )
