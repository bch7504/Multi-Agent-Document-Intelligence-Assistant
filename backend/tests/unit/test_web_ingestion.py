import unittest

from langchain_core.documents import Document

from backend.app.ingestion.web import (
    _crawl_exclude_dirs,
    _validate_url,
    add_chunk_provenance,
)


class CrawlTests(unittest.TestCase):
    def test_validate_url_requires_an_absolute_http_url(self):
        self.assertEqual(_validate_url("https://example.com/docs"), "https://example.com/docs")
        for invalid_url in ("example.com", "file:///tmp/data", "javascript:alert(1)"):
            with self.subTest(invalid_url=invalid_url):
                with self.assertRaises(ValueError):
                    _validate_url(invalid_url)

    def test_gitbook_resource_paths_are_excluded_for_the_selected_host(self):
        self.assertEqual(
            _crawl_exclude_dirs("https://docs.example.com/start"),
            (
                "https://docs.example.com/~gitbook/image",
                "https://docs.example.com/spaces/",
                "https://docs.example.com/files/",
            ),
        )

    def test_chunk_provenance_is_stable_and_unique(self):
        documents = [
            Document(page_content="First", metadata={"source": "https://example.com"}),
            Document(page_content="Second", metadata={"source": "https://example.com"}),
        ]

        first_pass = add_chunk_provenance(documents)
        first_ids = [document.metadata["chunk_id"] for document in first_pass]
        second_pass = add_chunk_provenance(documents)

        self.assertEqual(first_pass[0].metadata["document_id"], first_pass[1].metadata["document_id"])
        self.assertEqual(first_ids, [document.metadata["chunk_id"] for document in second_pass])
        self.assertEqual(len(set(first_ids)), 2)
        self.assertEqual([document.metadata["chunk_index"] for document in first_pass], [0, 1])


if __name__ == "__main__":
    unittest.main()
