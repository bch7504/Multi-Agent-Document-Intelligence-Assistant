import unittest
from uuid import uuid4

from langchain_core.documents import Document

from backend.app.ingestion.import_json import (
    build_curated_demo_documents,
    derive_document_sections,
)


class JsonImportSectionTests(unittest.TestCase):
    def test_groups_continuation_chunks_under_latest_h1(self):
        document_id = uuid4()
        chunks = [
            Document(page_content="# Overview\nFirst", metadata={"chunk_index": 0}),
            Document(page_content="Continuation", metadata={"chunk_index": 1}),
            Document(page_content="# Security\nStart", metadata={"chunk_index": 2}),
            Document(page_content="# Security\nMore", metadata={"chunk_index": 3}),
        ]

        sections = derive_document_sections(chunks, document_id)

        self.assertEqual([item["title"] for item in sections], ["Overview", "Security"])
        self.assertEqual(sections[0]["chunk_count"], 2)
        self.assertEqual(sections[1]["start_chunk_index"], 2)
        self.assertEqual(sections[1]["end_chunk_index"], 3)

    def test_creates_introduction_for_chunks_before_first_heading(self):
        sections = derive_document_sections(
            [Document(page_content="Preface", metadata={"chunk_index": 4})],
            uuid4(),
        )

        self.assertEqual(sections[0]["title"], "Introduction")

    def test_curated_demo_is_split_into_five_stable_documents(self):
        local_data = [
            {
                "page_content": f"# Section {index}\nContent {index}",
                "metadata": {"source": "https://example.test/llms-full.txt"},
            }
            for index in range(179)
        ]

        first = build_curated_demo_documents(local_data, "stack ai")
        second = build_curated_demo_documents(local_data, "stack ai")

        self.assertEqual(len(first), 5)
        self.assertEqual([item["id"] for item in first], [item["id"] for item in second])
        self.assertEqual(
            [len(item["documents"]) for item in first],
            [19, 11, 10, 19, 6],
        )
        self.assertEqual(len({item["id"] for item in first}), 5)
        for item in first:
            self.assertTrue(
                all(
                    document.metadata["document_id"] == str(item["id"])
                    for document in item["documents"]
                )
            )
            self.assertEqual(
                [document.metadata["chunk_index"] for document in item["documents"]],
                list(range(len(item["documents"]))),
            )


if __name__ == "__main__":
    unittest.main()
