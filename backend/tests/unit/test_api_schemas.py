import unittest
from uuid import uuid4

from pydantic import ValidationError

from backend.app.schemas.assistant import AssistantRunRequest
from backend.app.schemas.documents import DocumentRead, DocumentStatus


class ApiSchemaTests(unittest.TestCase):
    def test_assistant_request_accepts_camel_case_contract(self):
        conversation_id = uuid4()
        document_id = uuid4()

        request = AssistantRunRequest.model_validate(
            {
                "conversationId": str(conversation_id),
                "documentIds": [str(document_id)],
                "task": "qa",
                "message": "  RAG là gì?  ",
            }
        )

        self.assertEqual(request.conversation_id, conversation_id)
        self.assertEqual(request.document_ids, [document_id])
        self.assertEqual(request.message, "RAG là gì?")

    def test_assistant_request_rejects_duplicate_documents(self):
        document_id = uuid4()

        with self.assertRaisesRegex(ValidationError, "must not contain duplicates"):
            AssistantRunRequest(
                conversation_id=uuid4(),
                document_ids=[document_id, document_id],
                message="Summarize",
            )

    def test_assistant_request_rejects_blank_message(self):
        with self.assertRaisesRegex(ValidationError, "must not be blank"):
            AssistantRunRequest(
                conversation_id=uuid4(),
                document_ids=[uuid4()],
                message="   ",
            )

    def test_public_schema_serializes_camel_case_aliases(self):
        now = "2026-09-15T00:00:00Z"
        document = DocumentRead.model_validate(
            {
                "id": str(uuid4()),
                "name": "rag.pdf",
                "mimeType": "application/pdf",
                "sourceType": "upload",
                "checksum": "a" * 64,
                "status": DocumentStatus.READY,
                "pageCount": 10,
                "chunkCount": 42,
                "sections": [
                    {
                        "id": str(uuid4()),
                        "title": "Retrieval",
                        "startChunkIndex": 3,
                        "endChunkIndex": 5,
                        "chunkCount": 3,
                    }
                ],
                "createdAt": now,
                "updatedAt": now,
            }
        )

        payload = document.model_dump(mode="json", by_alias=True)
        self.assertEqual(payload["mimeType"], "application/pdf")
        self.assertEqual(payload["pageCount"], 10)
        self.assertEqual(payload["sections"][0]["startChunkIndex"], 3)
        self.assertNotIn("mime_type", payload)


if __name__ == "__main__":
    unittest.main()
