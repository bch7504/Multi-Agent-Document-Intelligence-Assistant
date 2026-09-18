"""Milvus-native dense + BM25 retrieval with scoped RRF fusion."""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable
from uuid import UUID

from langchain_core.documents import Document

from backend.app.services.indexing import (
    DENSE_VECTOR_FIELD,
    SPARSE_VECTOR_FIELD,
    connect_to_milvus,
)


DEFAULT_MILVUS_URI = "http://localhost:19530"
DEFAULT_RETRIEVAL_CANDIDATES = 20
DEFAULT_RRF_K = 60
DEFAULT_FULL_DOCUMENT_MAX_CHUNKS = 5_000
DOCUMENT_QUERY_FIELDS = [
    "text",
    "document_id",
    "chunk_id",
    "chunk_index",
    "page_number",
    "start_index",
    "source",
    "source_name",
    "doc_name",
    "title",
]


class RetrievalProfile(str, Enum):
    DENSE_ONLY = "dense_only"
    BM25_ONLY = "bm25_only"
    HYBRID_RRF = "hybrid_rrf"


DEFAULT_RETRIEVAL_PROFILE = RetrievalProfile.HYBRID_RRF


def _retrieval_profile(value: RetrievalProfile | str | None) -> RetrievalProfile:
    configured = value or os.getenv("RETRIEVAL_PROFILE", DEFAULT_RETRIEVAL_PROFILE.value)
    try:
        return RetrievalProfile(configured)
    except ValueError as error:
        choices = ", ".join(profile.value for profile in RetrievalProfile)
        raise ValueError(f"Unknown retrieval profile '{configured}'. Choose: {choices}") from error


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _document_filter(document_ids: Iterable[UUID | str] | None) -> str | None:
    if not document_ids:
        return None
    normalized = [str(UUID(str(document_id))) for document_id in document_ids]
    if not normalized:
        return None
    quoted = ", ".join(f'"{document_id}"' for document_id in normalized)
    return f"document_id in [{quoted}]"


@dataclass
class MilvusHybridRetriever:
    """Small adapter that keeps document scoping inside the vector query."""

    vectorstore: Any
    candidate_k: int = DEFAULT_RETRIEVAL_CANDIDATES
    rrf_k: int = DEFAULT_RRF_K
    profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE

    def _ranking_kwargs(self) -> dict[str, Any]:
        if self.profile == RetrievalProfile.HYBRID_RRF:
            return {"ranker_type": "rrf", "ranker_params": {"k": self.rrf_k}}
        raise AssertionError(f"Profile does not use hybrid ranking: {self.profile}")

    def _single_field_search(self, query: str, document_ids=None):
        expression = _document_filter(document_ids) or ""
        if self.profile == RetrievalProfile.DENSE_ONLY:
            embeddings = self.vectorstore.embeddings
            if isinstance(embeddings, list):
                embeddings = embeddings[0]
            if embeddings is None:
                raise RuntimeError("Dense retrieval requires an embedding function")
            data = [embeddings.embed_query(query)]
            field = DENSE_VECTOR_FIELD
            metric = "COSINE"
        elif self.profile == RetrievalProfile.BM25_ONLY:
            data = [query]
            field = SPARSE_VECTOR_FIELD
            metric = "BM25"
        else:
            raise AssertionError(f"Not a single-field profile: {self.profile}")

        results = self.vectorstore.client.search(
            collection_name=self.vectorstore.collection_name,
            data=data,
            anns_field=field,
            filter=expression,
            limit=self.candidate_k,
            output_fields=["*"],
            search_params={"metric_type": metric, "params": {}},
        )
        parsed = self.vectorstore._parse_documents_from_search_results(results)
        documents = []
        for document, score in parsed:
            document.metadata["score"] = score
            documents.append(document)
        return documents

    def _search(self, query: str, document_ids=None):
        if self.profile != RetrievalProfile.HYBRID_RRF:
            return self._single_field_search(query, document_ids=document_ids)
        kwargs: dict[str, Any] = {
            "k": self.candidate_k,
            **self._ranking_kwargs(),
        }
        if expression := _document_filter(document_ids):
            kwargs["expr"] = expression
        return self.vectorstore.similarity_search(query, **kwargs)

    def invoke(self, query: str, config: Any = None, **kwargs):
        """Remain compatible with LangChain tools and the legacy call sites."""
        del config, kwargs
        return self._search(query)

    def invoke_scoped(self, query: str, document_ids):
        return self._search(query, document_ids=document_ids)

    def invoke_all_scoped(self, document_ids):
        """Load complete documents in their original chunk order, without ANN search."""
        document_ids = tuple(document_ids)
        expression = _document_filter(document_ids)
        if not expression:
            return []
        max_chunks = _positive_int_env(
            "SUMMARY_FULL_DOCUMENT_MAX_CHUNKS",
            DEFAULT_FULL_DOCUMENT_MAX_CHUNKS,
        )
        rows = self.vectorstore.client.query(
            collection_name=self.vectorstore.collection_name,
            filter=expression,
            output_fields=DOCUMENT_QUERY_FIELDS,
            limit=max_chunks + 1,
        )
        if len(rows) > max_chunks:
            raise ValueError(
                "Selected documents exceed SUMMARY_FULL_DOCUMENT_MAX_CHUNKS="
                f"{max_chunks}; raise the limit explicitly to summarize all content"
            )

        document_order = {
            str(document_id): index for index, document_id in enumerate(document_ids)
        }

        def order_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
            return (
                document_order.get(str(row.get("document_id")), len(document_order)),
                int(row.get("chunk_index") or 0),
                int(row.get("page_number") or 0),
                int(row.get("start_index") or 0),
            )

        documents: list[Document] = []
        for row in sorted(rows, key=order_key):
            content = str(row.get("text") or "").strip()
            if not content:
                continue
            metadata = {
                field: row[field]
                for field in DOCUMENT_QUERY_FIELDS
                if field != "text" and row.get(field) is not None
            }
            documents.append(Document(page_content=content, metadata=metadata))
        return documents


def get_retriever(
    collection_name: str = "data_test",
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    milvus_uri: str | None = None,
    profile: RetrievalProfile | str | None = None,
) -> MilvusHybridRetriever:
    """Connect to a native dense/BM25 collection with a measurable profile."""
    vectorstore = connect_to_milvus(
        milvus_uri or os.getenv("MILVUS_URI", DEFAULT_MILVUS_URI),
        collection_name,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
    return MilvusHybridRetriever(
        vectorstore=vectorstore,
        candidate_k=_positive_int_env(
            "RETRIEVAL_CANDIDATE_K",
            DEFAULT_RETRIEVAL_CANDIDATES,
        ),
        rrf_k=_positive_int_env("RETRIEVAL_RRF_K", DEFAULT_RRF_K),
        profile=_retrieval_profile(profile),
    )
