import unittest
from tempfile import NamedTemporaryFile
from unittest.mock import patch
from uuid import uuid4

from backend.app.ingestion.pdf import EmptyPdfError, parse_and_chunk_pdf, parse_pdf_pages


class _Page:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class PdfIngestionTests(unittest.TestCase):
    @patch("backend.app.ingestion.pdf.PdfReader")
    def test_parser_preserves_one_based_page_numbers(self, reader_factory):
        reader_factory.return_value.pages = [_Page("Trang một"), _Page("Trang hai")]
        document_id = uuid4()

        pages, page_count = parse_pdf_pages("sample.pdf", document_id, "sample.pdf")

        self.assertEqual(page_count, 2)
        self.assertEqual([page.metadata["page_number"] for page in pages], [1, 2])
        self.assertTrue(all(page.metadata["document_id"] == str(document_id) for page in pages))

    @patch("backend.app.ingestion.pdf.PdfReader")
    def test_empty_or_scanned_pdf_fails_clearly(self, reader_factory):
        reader_factory.return_value.pages = [_Page(""), _Page(None)]

        with self.assertRaisesRegex(EmptyPdfError, "extractable text"):
            parse_pdf_pages("sample.pdf", uuid4(), "sample.pdf")

    @patch("backend.app.ingestion.pdf.PdfReader")
    def test_chunk_metadata_keeps_page_and_stable_document_id(self, reader_factory):
        reader_factory.return_value.pages = [_Page("Một đoạn nội dung ngắn.")]
        document_id = uuid4()

        chunks, page_count = parse_and_chunk_pdf("sample.pdf", document_id, "sample.pdf")

        self.assertEqual(page_count, 1)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["page_number"], 1)
        self.assertEqual(chunks[0].metadata["document_id"], str(document_id))
        self.assertTrue(chunks[0].metadata["chunk_id"])


if __name__ == "__main__":
    unittest.main()
