import unittest
from uuid import uuid4

from langchain_core.documents import Document

from backend.app.services.retrieval import normalize_document, retrieve_chunks


class RecordingRetriever:
    def __init__(self, documents):
        self.documents = documents
        self.query = None

    def invoke(self, query):
        self.query = query
        return self.documents


class ScopedRetriever(RecordingRetriever):
    def __init__(self, documents):
        super().__init__(documents)
        self.document_ids = None

    def invoke_scoped(self, query, document_ids):
        self.query = query
        self.document_ids = document_ids
        return self.documents


class RetrievalServiceTests(unittest.TestCase):
    def test_normalizes_explicit_provenance(self):
        document_id = uuid4()
        chunk_id = uuid4()
        chunk = normalize_document(
            Document(
                page_content="  Evidence about RAG.  ",
                metadata={
                    "document_id": str(document_id),
                    "chunk_id": str(chunk_id),
                    "source_name": "rag.pdf",
                    "source": "file:///documents/rag.pdf",
                    "page_number": 5,
                    "chunk_index": 8,
                    "score": "0.91",
                },
            ),
            rank=1,
        )

        self.assertEqual(chunk.document_id, document_id)
        self.assertEqual(chunk.chunk_id, chunk_id)
        self.assertEqual(chunk.content, "Evidence about RAG.")
        self.assertEqual(chunk.page_number, 5)
        self.assertEqual(chunk.chunk_index, 8)
        self.assertEqual(chunk.score, 0.91)

    def test_converts_legacy_zero_based_page_and_stable_ids(self):
        document = Document(
            page_content="Transformer evidence",
            metadata={"source": "paper.pdf", "page": 0, "start_index": 120},
        )

        first = normalize_document(document, rank=1)
        second = normalize_document(document, rank=1)

        self.assertEqual(first.page_number, 1)
        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(first.chunk_id, second.chunk_id)

    def test_retrieve_chunks_preserves_rank_and_query(self):
        retriever = RecordingRetriever(
            [
                Document(page_content="First", metadata={"source": "one"}),
                Document(page_content="Second", metadata={"source": "two"}),
            ]
        )

        chunks = retrieve_chunks(retriever, "  What is RAG?  ")

        self.assertEqual(retriever.query, "What is RAG?")
        self.assertEqual([chunk.rank for chunk in chunks], [1, 2])

    def test_retrieve_chunks_rejects_blank_query(self):
        with self.assertRaisesRegex(ValueError, "must not be blank"):
            retrieve_chunks(RecordingRetriever([]), "  ")

    def test_document_scope_is_pushed_to_retriever_and_enforced(self):
        allowed_id = uuid4()
        retriever = ScopedRetriever(
            [
                Document(
                    page_content="Allowed",
                    metadata={"document_id": str(allowed_id), "source": "one"},
                ),
                Document(
                    page_content="Blocked",
                    metadata={"document_id": str(uuid4()), "source": "two"},
                ),
            ]
        )

        chunks = retrieve_chunks(retriever, "query", document_ids=[allowed_id])

        self.assertEqual(retriever.document_ids, (allowed_id,))
        self.assertEqual([item.content for item in chunks], ["Allowed"])


if __name__ == "__main__":
    unittest.main()
