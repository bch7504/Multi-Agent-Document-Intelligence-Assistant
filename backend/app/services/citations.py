"""Build and deterministically validate citations against retrieved evidence."""

import re
from collections.abc import Iterable
from uuid import UUID

from backend.app.rag.schemas import RetrievedChunk
from backend.app.schemas.assistant import Citation


DEFAULT_EXCERPT_LENGTH = 320


class CitationValidationError(ValueError):
    """Raised when a citation cannot be traced to retrieved evidence."""


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def citation_from_chunk(
    chunk: RetrievedChunk,
    excerpt_length: int = DEFAULT_EXCERPT_LENGTH,
) -> Citation:
    if excerpt_length < 1:
        raise ValueError("excerpt_length must be positive")
    excerpt = _normalized_text(chunk.content)[:excerpt_length]
    return Citation(
        document_id=chunk.document_id,
        document_name=chunk.source_name,
        page_number=chunk.page_number,
        chunk_id=chunk.chunk_id,
        excerpt=excerpt,
        source_uri=chunk.source_uri,
    )


def citations_from_chunks(chunks: Iterable[RetrievedChunk]) -> list[Citation]:
    """Build one unique citation per retrieved chunk, preserving rank order."""
    citations: list[Citation] = []
    seen: set[UUID] = set()
    for chunk in sorted(chunks, key=lambda item: item.rank):
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        citations.append(citation_from_chunk(chunk))
    return citations


def validate_citations(
    citations: Iterable[Citation],
    chunks: Iterable[RetrievedChunk],
    allowed_document_ids: Iterable[UUID],
) -> None:
    """Ensure every citation is supported and remains inside request scope."""
    evidence = {chunk.chunk_id: chunk for chunk in chunks}
    allowed = set(allowed_document_ids)
    seen: set[UUID] = set()

    for citation in citations:
        if citation.chunk_id in seen:
            raise CitationValidationError(
                f"Duplicate citation for chunk '{citation.chunk_id}'"
            )
        seen.add(citation.chunk_id)

        chunk = evidence.get(citation.chunk_id)
        if chunk is None:
            raise CitationValidationError(
                f"Citation chunk '{citation.chunk_id}' was not retrieved"
            )
        if citation.document_id not in allowed:
            raise CitationValidationError(
                f"Citation document '{citation.document_id}' is outside request scope"
            )
        if citation.document_id != chunk.document_id:
            raise CitationValidationError("Citation document does not match its chunk")
        if citation.page_number != chunk.page_number:
            raise CitationValidationError("Citation page does not match its chunk")

        excerpt = _normalized_text(citation.excerpt)
        content = _normalized_text(chunk.content)
        if excerpt not in content:
            raise CitationValidationError(
                "Citation excerpt is not present in its retrieved chunk"
            )
