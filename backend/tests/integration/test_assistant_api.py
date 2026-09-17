import unittest
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.assistant import get_assistant_service
from backend.app.main import app
from backend.app.schemas.assistant import (
    AssistantRunAudit,
    AssistantRunResponse,
    ResolvedAssistantTask,
    ReviewResult,
    ReviewStatus,
)


class FakeAssistantService:
    def __init__(self):
        self.request = None
        self.run_id = uuid4()
        self.conversation_id = uuid4()
        self.document_id = uuid4()

    def run(self, request):
        self.request = request
        return AssistantRunResponse(
            run_id=self.run_id,
            task=ResolvedAssistantTask.SUMMARY,
            answer="Grounded document summary",
            citations=[],
            review=ReviewResult(status=ReviewStatus.PASS, retry_count=0),
            trace=[],
        )

    def get_run(self, run_id):
        return AssistantRunAudit(
            run_id=run_id,
            conversation_id=self.conversation_id,
            document_ids=[self.document_id],
            task=ResolvedAssistantTask.SUMMARY,
            answer="Grounded document summary",
            citations=[],
            review=ReviewResult(status=ReviewStatus.PASS, retry_count=0),
            trace=[],
            created_at=datetime.now(UTC),
        )


class AssistantApiTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeAssistantService()
        app.dependency_overrides[get_assistant_service] = lambda: self.service
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_one_endpoint_accepts_summary_and_returns_structured_response(self):
        conversation_id = uuid4()
        document_id = uuid4()

        response = self.client.post(
            "/api/v1/assistant/runs",
            json={
                "conversationId": str(conversation_id),
                "documentIds": [str(document_id)],
                "task": "summary",
                "message": "Summarize the selected document",
                "llmProvider": "openrouter",
                "llmModel": "vendor/chat-model",
                "embeddingProvider": "openai",
                "embeddingModel": "text-embedding-3-small",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task"], "summary")
        self.assertEqual(payload["answer"], "Grounded document summary")
        self.assertEqual(self.service.request.conversation_id, conversation_id)
        self.assertEqual(self.service.request.document_ids, [document_id])
        self.assertEqual(self.service.request.llm_provider.value, "openrouter")
        self.assertEqual(self.service.request.llm_model, "vendor/chat-model")

    def test_get_run_returns_persisted_audit_contract(self):
        response = self.client.get(f"/api/v1/assistant/runs/{self.service.run_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runId"], str(self.service.run_id))
        self.assertEqual(payload["conversationId"], str(self.service.conversation_id))
        self.assertEqual(payload["documentIds"], [str(self.service.document_id)])
        self.assertEqual(payload["usage"]["totalTokens"], 0)


if __name__ == "__main__":
    unittest.main()
