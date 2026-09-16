"""Normalize legacy LangChain retrieval results for API and graph consumers."""

from collections.abc import Iterable
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from langchain_core.documents import Document

from backend.app.rag.schemas import RetrievedChunk


def _uuid_or_stable(value: Any, fallback: str) -> UUID:
    if value:
        try:
            return UUID(str(value))
        except ValueError:
            return uuid5(NAMESPACE_URL, str(value))
    return uuid5(NAMESPACE_URL, fallback)


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _page_number(metadata: dict[str, Any]) -> int | None:
    raw_page = metadata.get("page_number", metadata.get("page"))
    page = _optional_non_negative_int(raw_page)
    if page is None:
        return None

    # Common PDF loaders expose a zero-based `page`; the new contract stores
    # one-based `page_number` explicitly.
    if "page_number" not in metadata:
        return page + 1
    return page if page >= 1 else None


def normalize_document(document: Document, rank: int) -> RetrievedChunk:
    """Convert a LangChain Document into the stable retrieval contract."""
    content = document.page_content.strip()
    if not content:
        raise ValueError("Retrieved documents must contain non-blank content")

    metadata = dict(document.metadata or {})
    source_uri = str(metadata.get("source") or "").strip() or None
    source_name = str(
        metadata.get("source_name")
        or metadata.get("doc_name")
        or metadata.get("title")
        or source_uri
        or "Unknown document"
    )[:255]
    start_index = _optional_non_negative_int(metadata.get("start_index")) or 0
    document_seed = source_uri or source_name
    document_id = _uuid_or_stable(
        metadata.get("document_id"),
        f"document::{document_seed}",
    )
    chunk_id = _uuid_or_stable(
        metadata.get("chunk_id"),
        f"chunk::{document_id}::{start_index}::{content}",
    )
    raw_score = metadata.get("score")
    try:
        score = float(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        score = None

    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        content=content,
        source_name=source_name,
        source_uri=source_uri,
        page_number=_page_number(metadata),
        chunk_index=_optional_non_negative_int(metadata.get("chunk_index")),
        rank=rank,
        score=score,
    )


def normalize_documents(documents: Iterable[Document]) -> list[RetrievedChunk]:
    return [
        normalize_document(document, rank=rank)
        for rank, document in enumerate(documents, start=1)
    ]


def retrieve_chunks(
    retriever: Any,
    query: str,
    document_ids: Iterable[UUID] | None = None,
) -> list[RetrievedChunk]:
    """Retrieve structured evidence, pushing document scope down when supported."""
    query = query.strip()
    if not query:
        raise ValueError("Retrieval query must not be blank")
    allowed_ids = tuple(dict.fromkeys(document_ids or ()))
    allowed = set(allowed_ids)
    if allowed and hasattr(retriever, "invoke_scoped"):
        documents = retriever.invoke_scoped(query, allowed_ids)
    else:
        documents = retriever.invoke(query)

    chunks = normalize_documents(documents)
    if allowed:
        # Defense in depth for legacy/fake retrievers that cannot filter at source.
        chunks = [chunk for chunk in chunks if chunk.document_id in allowed]
    return chunks
