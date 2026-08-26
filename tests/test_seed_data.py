import unittest

from seed_data import (
    _documents_from_local_data,
    _embedding_from_description,
    _temporary_collection_name,
    _validate_collection_name,
)


class SeedDataTests(unittest.TestCase):
    def test_collection_name_validation(self):
        self.assertEqual(_validate_collection_name("data_test_2"), "data_test_2")
        for invalid_name in ("", "2data", "data-test", "data test"):
            with self.subTest(invalid_name=invalid_name):
                with self.assertRaises(ValueError):
                    _validate_collection_name(invalid_name)

    def test_temporary_collection_name_stays_valid_and_bounded(self):
        name = _temporary_collection_name("a" * 255, "staging")
        self.assertLessEqual(len(name), 255)
        self.assertEqual(_validate_collection_name(name), name)

    def test_embedding_marker_is_read_from_description(self):
        description = "RAG documents; embedding_model=ollama:nomic-embed-text"
        self.assertEqual(
            _embedding_from_description(description),
            "ollama:nomic-embed-text",
        )

    def test_empty_documents_are_not_indexed(self):
        documents = _documents_from_local_data(
            [
                {"page_content": "", "metadata": {}},
                {"page_content": "Nội dung", "metadata": {"source": "test"}},
            ],
            "sample",
        )
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].page_content, "Nội dung")

    def test_oversized_metadata_is_bounded_for_milvus(self):
        documents = _documents_from_local_data(
            [{"page_content": "Nội dung", "metadata": {"title": "x" * 70_000}}],
            "sample",
        )
        self.assertEqual(len(documents[0].metadata["title"]), 1_000)


if __name__ == "__main__":
    unittest.main()
