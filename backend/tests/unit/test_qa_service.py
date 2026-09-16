import unittest
from unittest.mock import patch
from uuid import uuid4

from langchain_core.documents import Document

from backend.app.schemas.assistant import AssistantRunRequest
from backend.app.services.citations import CitationValidationError
from backend.app.services.qa import InsufficientContextError, answer_question


class FakeRetriever:
    def __init__(self, documents):
        self.documents = documents
        self.query = None

    def invoke(self, query):
        self.query = query
        return self.documents


class FakeStructuredLlm:
    def __init__(self, response):
        self.response = response
        self.schema = None
        self.messages = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.response


class QaServiceTests(unittest.TestCase):
    def test_returns_only_backend_built_valid_citations(self):
        document_id = uuid4()
        chunk_id = uuid4()
        llm = FakeStructuredLlm(
            {
                "answer": "RAG retrieves evidence before generation.",
                "cited_chunk_ids": [str(chunk_id)],
            }
        )
        retriever = FakeRetriever(
            [
                Document(
                    page_content="RAG retrieves evidence before generation.",
                    metadata={
                        "document_id": str(document_id),
                        "chunk_id": str(chunk_id),
                        "source_name": "rag.pdf",
                        "page_number": 3,
                    },
                )
            ]
        )
        request = AssistantRunRequest(
            conversation_id=uuid4(),
            document_ids=[document_id],
            task="qa",
            message="What is RAG?",
        )

        response = answer_question(request, retriever, llm)

        self.assertEqual(response.answer, "RAG retrieves evidence before generation.")
        self.assertEqual(response.citations[0].chunk_id, chunk_id)
        self.assertEqual(response.citations[0].page_number, 3)
        self.assertEqual(response.review.status, "pass")
        self.assertIn(str(chunk_id), llm.messages[1][1])

    def test_rejects_model_citation_not_present_in_context(self):
        document_id = uuid4()
        retriever = FakeRetriever(
            [
                Document(
                    page_content="Evidence",
                    metadata={
                        "document_id": str(document_id),
                        "chunk_id": str(uuid4()),
                    },
                )
            ]
        )
        llm = FakeStructuredLlm(
            {"answer": "Unsupported", "cited_chunk_ids": [str(uuid4())]}
        )
        request = AssistantRunRequest(
            conversation_id=uuid4(),
            document_ids=[document_id],
            message="Question",
        )

        with self.assertRaisesRegex(CitationValidationError, "not retrieved"):
            answer_question(request, retriever, llm)

    def test_rejects_evidence_outside_selected_documents(self):
        retriever = FakeRetriever(
            [
                Document(
                    page_content="Evidence",
                    metadata={"document_id": str(uuid4())},
                )
            ]
        )
        request = AssistantRunRequest(
            conversation_id=uuid4(),
            document_ids=[uuid4()],
            message="Question",
        )

        with self.assertRaisesRegex(InsufficientContextError, "selected documents"):
            answer_question(request, retriever, FakeStructuredLlm({}))

    @patch(
        "backend.app.services.qa.rewrite_query",
        return_value="Standalone retrieval query",
    )
    def test_follow_up_uses_rewritten_query_and_traces_it(self, rewrite):
        document_id = uuid4()
        chunk_id = uuid4()
        retriever = FakeRetriever(
            [
                Document(
                    page_content="Evidence",
                    metadata={
                        "document_id": str(document_id),
                        "chunk_id": str(chunk_id),
                    },
                )
            ]
        )
        request = AssistantRunRequest(
            conversation_id=uuid4(),
            document_ids=[document_id],
            message="How does it work?",
        )
        llm = FakeStructuredLlm(
            {"answer": "Evidence", "cited_chunk_ids": [str(chunk_id)]}
        )

        response = answer_question(
            request,
            retriever,
            llm,
            history=[{"role": "user", "content": "Explain RAG"}],
        )

        rewrite.assert_called_once()
        self.assertEqual(retriever.query, "Standalone retrieval query")
        self.assertEqual(response.trace[0].id, "rewrite_query")


if __name__ == "__main__":
    unittest.main()
