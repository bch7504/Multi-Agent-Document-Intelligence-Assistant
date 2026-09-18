import unittest
from uuid import uuid4

from backend.app.rag.hybrid_search import (
    MilvusHybridRetriever,
    RetrievalProfile,
    _document_filter,
    _retrieval_profile,
)


class RecordingVectorStore:
    def __init__(self):
        self.query_text = None
        self.kwargs = None
        self.query_rows = []
        self.collection_name = "document_chunks"
        self.client = self
        self.embeddings = self
        self.embedded_query = None

    def embed_query(self, query):
        self.embedded_query = query
        return [0.1, 0.2]

    def search(self, **kwargs):
        self.kwargs = kwargs
        return []

    def query(self, **kwargs):
        self.kwargs = kwargs
        return self.query_rows

    def _parse_documents_from_search_results(self, results):
        return []

    def similarity_search(self, query, **kwargs):
        self.query_text = query
        self.kwargs = kwargs
        return []


class HybridSearchTests(unittest.TestCase):
    def test_document_filter_accepts_only_uuid_values(self):
        document_id = uuid4()
        self.assertEqual(
            _document_filter([document_id]),
            f'document_id in ["{document_id}"]',
        )
        with self.assertRaises(ValueError):
            _document_filter(['not-a-uuid"])'])

    def test_scoped_search_uses_native_rrf_and_filter(self):
        vectorstore = RecordingVectorStore()
        document_id = uuid4()
        retriever = MilvusHybridRetriever(vectorstore, candidate_k=20, rrf_k=60)

        retriever.invoke_scoped("What is RAG?", [document_id])

        self.assertEqual(vectorstore.query_text, "What is RAG?")
        self.assertEqual(vectorstore.kwargs["k"], 20)
        self.assertEqual(vectorstore.kwargs["ranker_type"], "rrf")
        self.assertEqual(vectorstore.kwargs["ranker_params"], {"k": 60})
        self.assertEqual(
            vectorstore.kwargs["expr"],
            f'document_id in ["{document_id}"]',
        )

    def test_dense_and_bm25_profiles_search_only_one_field(self):
        for profile, field, metric in (
            (RetrievalProfile.DENSE_ONLY, "dense", "COSINE"),
            (RetrievalProfile.BM25_ONLY, "sparse", "BM25"),
        ):
            with self.subTest(profile=profile):
                vectorstore = RecordingVectorStore()
                retriever = MilvusHybridRetriever(vectorstore, profile=profile)

                retriever.invoke("query")

                self.assertEqual(vectorstore.kwargs["anns_field"], field)
                self.assertEqual(vectorstore.kwargs["search_params"]["metric_type"], metric)
                if profile == RetrievalProfile.DENSE_ONLY:
                    self.assertEqual(vectorstore.embedded_query, "query")
                    self.assertEqual(vectorstore.kwargs["data"], [[0.1, 0.2]])
                else:
                    self.assertIsNone(vectorstore.embedded_query)
                    self.assertEqual(vectorstore.kwargs["data"], ["query"])

    def test_full_document_load_uses_scalar_query_and_source_order(self):
        vectorstore = RecordingVectorStore()
        document_id = uuid4()
        vectorstore.query_rows = [
            {
                "text": "Second",
                "document_id": str(document_id),
                "chunk_id": str(uuid4()),
                "chunk_index": 1,
                "source_name": "guide.pdf",
            },
            {
                "text": "First",
                "document_id": str(document_id),
                "chunk_id": str(uuid4()),
                "chunk_index": 0,
                "source_name": "guide.pdf",
            },
        ]
        retriever = MilvusHybridRetriever(vectorstore)

        documents = retriever.invoke_all_scoped([document_id])

        self.assertEqual([document.page_content for document in documents], ["First", "Second"])
        self.assertEqual(
            vectorstore.kwargs["filter"],
            f'document_id in ["{document_id}"]',
        )

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown retrieval profile"):
            _retrieval_profile("unknown")


if __name__ == "__main__":
    unittest.main()
