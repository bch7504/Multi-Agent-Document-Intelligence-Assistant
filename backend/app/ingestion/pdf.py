"""Page-preserving PDF parser and token-aware chunker."""

from pathlib import Path
from uuid import UUID

from langchain_core.documents import Document
from pypdf import PdfReader

from backend.app.ingestion.web import add_chunk_provenance, build_text_splitter


class EmptyPdfError(ValueError):
    pass


def parse_pdf_pages(path: str | Path, document_id: UUID, document_name: str) -> tuple[list[Document], int]:
    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    pages: list[Document] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        pages.append(
            Document(
                page_content=text,
                metadata={
                    "document_id": str(document_id),
                    "source": f"document://{document_id}",
                    "source_name": document_name,
                    "doc_name": document_name,
                    "content_type": "application/pdf",
                    "page_number": page_number,
                },
            )
        )

    if not pages:
        raise EmptyPdfError("PDF does not contain extractable text")
    return pages, page_count


def parse_and_chunk_pdf(
    path: str | Path,
    document_id: UUID,
    document_name: str,
) -> tuple[list[Document], int]:
    pages, page_count = parse_pdf_pages(path, document_id, document_name)
    chunks = build_text_splitter().split_documents(pages)
    chunks = [chunk for chunk in chunks if chunk.page_content.strip()]
    if not chunks:
        raise EmptyPdfError("PDF does not contain indexable text")
    return add_chunk_provenance(chunks, source_name=document_name), page_count
