import unittest
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.api.conversations import get_conversation_service
from backend.app.api.quizzes import get_quiz_service
from backend.app.database.postgres import Base
from backend.app.main import app
from backend.app.models.assistant_run import AssistantRunRecord
from backend.app.models.conversation import ConversationRecord
from backend.app.models.message import MessageRecord
from backend.app.models.quiz import QuizRecord
from backend.app.services.conversations import ConversationService
from backend.app.services.quizzes import QuizService


class HistoryAndQuizApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.conversation_id = uuid4()
        self.run_id = uuid4()
        now = datetime.now(UTC)
        self.session.add(
            ConversationRecord(
                id=self.conversation_id,
                title="Security questions",
                created_at=now,
                updated_at=now,
            )
        )
        self.session.add_all(
            [
                MessageRecord(
                    conversation_id=self.conversation_id,
                    role="user",
                    content="Create a quiz",
                    task="quiz",
                    created_at=now,
                ),
                MessageRecord(
                    conversation_id=self.conversation_id,
                    role="assistant",
                    content="Generated one quiz question.",
                    task="quiz",
                    created_at=now,
                ),
                AssistantRunRecord(
                    id=self.run_id,
                    conversation_id=self.conversation_id,
                    task="quiz",
                    status="pass",
                    answer="Generated one quiz question.",
                    retry_count=0,
                    document_ids=[],
                    citations=[],
                    trace=[],
                    quiz={"questions": []},
                    usage={},
                    created_at=now,
                ),
            ]
        )
        self.question_id = "q1"
        self.quiz = QuizRecord(
            id=self.run_id,
            run_id=self.run_id,
            conversation_id=self.conversation_id,
            title="Security quiz",
            questions=[
                {
                    "id": self.question_id,
                    "question": "Which control limits access?",
                    "options": [
                        {"id": "a", "text": "RBAC"},
                        {"id": "b", "text": "Caching"},
                    ],
                    "correctOptionId": "a",
                    "explanation": "RBAC controls access by role.",
                    "citations": [
                        {
                            "documentId": str(uuid4()),
                            "documentName": "guide.pdf",
                            "pageNumber": 1,
                            "chunkId": str(uuid4()),
                            "excerpt": "RBAC limits access by role.",
                            "sourceUri": None,
                        }
                    ],
                }
            ],
            created_at=now,
            updated_at=now,
        )
        self.session.add(self.quiz)
        self.session.commit()

        app.dependency_overrides[get_conversation_service] = lambda: ConversationService(self.session)
        app.dependency_overrides[get_quiz_service] = lambda: QuizService(self.session)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.session.close()
        self.engine.dispose()

    def test_conversation_list_messages_and_rename(self):
        listing = self.client.get("/api/v1/conversations").json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["messageCount"], 2)

        messages = self.client.get(
            f"/api/v1/conversations/{self.conversation_id}/messages"
        ).json()
        self.assertEqual([item["role"] for item in messages["items"]], ["user", "assistant"])

        renamed = self.client.patch(
            f"/api/v1/conversations/{self.conversation_id}",
            json={"title": "Updated title"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["title"], "Updated title")

        blank = self.client.patch(
            f"/api/v1/conversations/{self.conversation_id}",
            json={"title": "   "},
        )
        self.assertEqual(blank.status_code, 422)

    def test_quiz_attempt_is_scored_and_listed(self):
        listing = self.client.get("/api/v1/quizzes").json()
        self.assertEqual(listing["items"][0]["questionCount"], 1)

        attempt = self.client.post(
            f"/api/v1/quizzes/{self.quiz.id}/attempts",
            json={"answers": {self.question_id: "a"}},
        )
        self.assertEqual(attempt.status_code, 201)
        self.assertEqual(attempt.json()["scorePercent"], 100.0)

        attempts = self.client.get(
            f"/api/v1/quizzes/{self.quiz.id}/attempts"
        ).json()
        self.assertEqual(attempts["total"], 1)

    def test_deleting_conversation_removes_history_and_quiz(self):
        deleted = self.client.delete(f"/api/v1/conversations/{self.conversation_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/conversations").json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/quizzes").json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
