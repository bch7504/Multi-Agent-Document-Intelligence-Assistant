import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database.postgres import Base
from backend.app.models.document import DocumentRecord
from backend.app.models.assistant_run import AssistantRunRecord
from backend.app.models.conversation import ConversationRecord
from backend.app.models.message import MessageRecord
from backend.app.models.quiz import QuizRecord
from backend.app.schemas.assistant import (
    AssistantRunRequest,
    AssistantRunResponse,
    Citation,
    QuizOption,
    QuizQuestion,
    QuizResult,
    ResolvedAssistantTask,
    ReviewResult,
    ReviewStatus,
)
from backend.app.schemas.documents import DocumentStatus
from backend.app.services.assistant import (
    AssistantDocumentNotFoundError,
    AssistantDocumentNotReadyError,
    AssistantEmbeddingMismatchError,
    AssistantService,
)


class FakeRuntime:
    def __init__(self):
        self.request = None
        self.histories = []

    def invoke(self, request, history=None):
        self.request = request
        self.histories.append(history or [])
        return AssistantRunResponse(
            run_id=uuid4(),
            task=ResolvedAssistantTask.QA,
            answer="Grounded answer",
            citations=[],
            review=ReviewResult(status=ReviewStatus.PASS, retry_count=0),
        )


class FakeQuizRuntime(FakeRuntime):
    def invoke(self, request, history=None):
        self.request = request
        self.histories.append(history or [])
        return AssistantRunResponse(
            run_id=uuid4(),
            task=ResolvedAssistantTask.QUIZ,
            answer="Generated one grounded quiz question.",
            citations=[],
            quiz=QuizResult(
                questions=[
                    QuizQuestion(
                        id="q1",
                        question="What is RAG?",
                        options=[
                            QuizOption(id="a", text="Retrieval augmented generation"),
                            QuizOption(id="b", text="A database"),
                        ],
                        correct_option_id="a",
                        explanation="RAG combines retrieval and generation.",
                        citations=[
                            Citation(
                                document_id=request.document_ids[0],
                                document_name="guide.pdf",
                                page_number=1,
                                chunk_id=uuid4(),
                                excerpt="RAG combines retrieval and generation.",
                            )
                        ],
                    )
                ]
            ),
            review=ReviewResult(status=ReviewStatus.PASS, retry_count=0),
        )


class AssistantServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.runtime = FakeRuntime()
        self.service = AssistantService(self.session, self.runtime)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_document(self, status, embedding_model=None):
        document_id = uuid4()
        now = datetime.now(timezone.utc)
        self.session.add(
            DocumentRecord(
                id=document_id,
                name="guide.pdf",
                mime_type="application/pdf",
                source_type="upload",
                storage_key=f"{document_id}/guide.pdf",
                checksum="a" * 64,
                size_bytes=100,
                status=status,
                embedding_model=embedding_model,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        return document_id

    def request(self, document_id, conversation_id=None, message="Question"):
        return AssistantRunRequest(
            conversation_id=conversation_id or uuid4(),
            document_ids=[document_id],
            task="qa",
            message=message,
        )

    def test_ready_documents_are_sent_to_graph(self):
        document_id = self.add_document(DocumentStatus.READY.value)

        response = self.service.run(self.request(document_id))

        self.assertEqual(response.answer, "Grounded answer")
        self.assertEqual(self.runtime.request.document_ids, [document_id])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(ConversationRecord)),
            1,
        )
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(MessageRecord)),
            2,
        )
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(AssistantRunRecord)),
            1,
        )
        audit = self.service.get_run(response.run_id)
        self.assertEqual(audit.answer, "Grounded answer")
        self.assertEqual(audit.conversation_id, self.runtime.request.conversation_id)

    def test_persisted_history_is_reloaded_after_runtime_restart(self):
        document_id = self.add_document(DocumentStatus.READY.value)
        conversation_id = uuid4()
        self.service.run(self.request(document_id, conversation_id, "First question"))
        restarted_runtime = FakeRuntime()
        restarted_service = AssistantService(self.session, restarted_runtime)

        restarted_service.run(
            self.request(document_id, conversation_id, "Follow-up question")
        )

        self.assertEqual(
            restarted_runtime.histories[0],
            [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "Grounded answer"},
            ],
        )

    def test_quiz_run_is_added_to_library(self):
        document_id = self.add_document(DocumentStatus.READY.value)
        runtime = FakeQuizRuntime()
        service = AssistantService(self.session, runtime)
        request = AssistantRunRequest(
            conversation_id=uuid4(),
            document_ids=[document_id],
            task="quiz",
            message="Create a RAG quiz",
        )

        response = service.run(request)

        quiz = self.session.get(QuizRecord, response.run_id)
        self.assertIsNotNone(quiz)
        self.assertEqual(quiz.title, "Create a RAG quiz")
        self.assertEqual(quiz.questions[0]["correctOptionId"], "a")

    def test_missing_document_is_rejected(self):
        with self.assertRaises(AssistantDocumentNotFoundError):
            self.service.run(self.request(uuid4()))

    def test_non_ready_document_is_rejected(self):
        document_id = self.add_document(DocumentStatus.PROCESSING.value)

        with self.assertRaises(AssistantDocumentNotReadyError):
            self.service.run(self.request(document_id))

    def test_request_embedding_must_match_indexed_document(self):
        document_id = self.add_document(
            DocumentStatus.READY.value,
            embedding_model="openai:text-embedding-3-small",
        )
        request = AssistantRunRequest(
            conversation_id=uuid4(),
            document_ids=[document_id],
            task="qa",
            message="Question",
            embedding_provider="openrouter",
            embedding_model="openai/text-embedding-3-small",
        )

        with self.assertRaises(AssistantEmbeddingMismatchError):
            self.service.run(request)


if __name__ == "__main__":
    unittest.main()
