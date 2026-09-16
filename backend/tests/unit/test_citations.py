import unittest
from uuid import uuid4

from backend.app.rag.schemas import RetrievedChunk
from backend.app.schemas.assistant import Citation
from backend.app.services.citations import (
    CitationValidationError,
    citation_from_chunk,
    citations_from_chunks,
    validate_citations,
)


def make_chunk(rank: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content="RAG retrieves relevant evidence before generating an answer.",
        source_name="rag.pdf",
        source_uri=None,
        page_number=5,
        chunk_index=2,
        rank=rank,
        score=0.9,
    )


class CitationServiceTests(unittest.TestCase):
    def test_builds_and_validates_citation_from_evidence(self):
        chunk = make_chunk()
        citation = citation_from_chunk(chunk)

        validate_citations([citation], [chunk], [chunk.document_id])

        self.assertEqual(citation.chunk_id, chunk.chunk_id)
        self.assertEqual(citation.page_number, 5)

    def test_deduplicates_chunks_and_preserves_rank(self):
        first = make_chunk(rank=2)
        second = make_chunk(rank=1)

        citations = citations_from_chunks([first, second, first])

        self.assertEqual(
            [citation.chunk_id for citation in citations],
            [second.chunk_id, first.chunk_id],
        )

    def test_rejects_citation_outside_document_scope(self):
        chunk = make_chunk()
        citation = citation_from_chunk(chunk)

        with self.assertRaisesRegex(CitationValidationError, "outside request scope"):
            validate_citations([citation], [chunk], [uuid4()])

    def test_rejects_excerpt_not_found_in_evidence(self):
        chunk = make_chunk()
        citation = Citation(
            document_id=chunk.document_id,
            document_name=chunk.source_name,
            page_number=chunk.page_number,
            chunk_id=chunk.chunk_id,
            excerpt="Unsupported claim",
        )

        with self.assertRaisesRegex(CitationValidationError, "not present"):
            validate_citations([citation], [chunk], [chunk.document_id])


if __name__ == "__main__":
    unittest.main()
