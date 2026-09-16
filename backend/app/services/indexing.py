"""Index documents in Milvus and connect to existing collections."""

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_milvus import BM25BuiltInFunction, Milvus
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient, connections
from dotenv import load_dotenv

from backend.app.ingestion.web import add_chunk_provenance, crawl_web


load_dotenv()


DEFAULT_OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_GEMINI_EMBEDDING_MODEL = "models/gemini-embedding-001"
DEFAULT_OPENROUTER_EMBEDDING_MODEL = "openai/text-embedding-3-small"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
SUPPORTED_EMBEDDING_PROVIDERS = {"openrouter", "openai", "gemini", "ollama"}
EMBEDDING_DESCRIPTION_PREFIX = "embedding_model="
RETRIEVAL_PROFILE_PREFIX = "retrieval_profile="
HYBRID_RETRIEVAL_PROFILE = "dense_bm25_v1"
DENSE_VECTOR_FIELD = "dense"
SPARSE_VECTOR_FIELD = "sparse"
COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")
MILVUS_INSERT_BATCH_SIZE = 100
METADATA_TEXT_LIMITS = {
    "source": 2_048,
    "content_type": 255,
    "title": 1_000,
    "description": 4_000,
    "language": 32,
    "doc_name": 255,
    "source_name": 255,
    "document_id": 36,
    "chunk_id": 36,
}


def _validate_collection_name(collection_name: str) -> str:
    collection_name = collection_name.strip()
    if not COLLECTION_NAME_PATTERN.fullmatch(collection_name):
        raise ValueError(
            "Collection name must start with a letter or underscore, contain only "
            "letters, numbers, and underscores, and be at most 255 characters"
        )
    return collection_name


def _embedding_provider(embedding_provider: str | None = None) -> str:
    provider = (embedding_provider or os.getenv("EMBEDDING_PROVIDER", "")).strip().lower()
    if not provider:
        raise ValueError(
            "EMBEDDING_PROVIDER must be selected: openrouter, openai, gemini, or ollama"
        )
    if provider not in SUPPORTED_EMBEDDING_PROVIDERS:
        choices = ", ".join(sorted(SUPPORTED_EMBEDDING_PROVIDERS))
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER '{provider}'. Choose: {choices}")
    return provider


def _configured_value(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def _required_api_key(name: str, provider: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"{name} is required when EMBEDDING_PROVIDER={provider}"
        )
    return value


def _embedding_model_name(embedding_provider: str | None = None) -> str:
    provider = _embedding_provider(embedding_provider)
    model_settings = {
        "openrouter": (
            "OPENROUTER_EMBEDDING_MODEL",
            DEFAULT_OPENROUTER_EMBEDDING_MODEL,
        ),
        "openai": ("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL),
        "gemini": ("GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL),
        "ollama": ("OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL),
    }
    variable, default = model_settings[provider]
    return f"{provider}:{_configured_value(variable, default)}"


def _get_embeddings(embedding_provider: str | None = None):
    provider = _embedding_provider(embedding_provider)
    if provider == "ollama":
        kwargs = {
            "model": _configured_value(
                "OLLAMA_EMBEDDING_MODEL",
                DEFAULT_OLLAMA_EMBEDDING_MODEL,
            )
        }
        if base_url := os.getenv("OLLAMA_BASE_URL"):
            kwargs["base_url"] = base_url
        return OllamaEmbeddings(**kwargs)

    if provider == "openai":
        return OpenAIEmbeddings(
            model=_configured_value(
                "OPENAI_EMBEDDING_MODEL",
                DEFAULT_OPENAI_EMBEDDING_MODEL,
            ),
            api_key=_required_api_key("OPENAI_API_KEY", "openai"),
        )

    if provider == "openrouter":
        return OpenAIEmbeddings(
            model=_configured_value(
                "OPENROUTER_EMBEDDING_MODEL",
                DEFAULT_OPENROUTER_EMBEDDING_MODEL,
            ),
            api_key=_required_api_key("OPENROUTER_API_KEY", "openrouter"),
            base_url=OPENROUTER_BASE_URL,
        )

    if provider == "gemini":
        return GoogleGenerativeAIEmbeddings(
            model=_configured_value(
                "GEMINI_EMBEDDING_MODEL",
                DEFAULT_GEMINI_EMBEDDING_MODEL,
            ),
            google_api_key=_required_api_key("GOOGLE_API_KEY", "gemini"),
        )

    raise AssertionError(f"Unhandled embedding provider: {provider}")


def _hybrid_vectorstore_kwargs(embedding_provider: str | None) -> dict:
    return {
        "embedding_function": _get_embeddings(embedding_provider),
        "builtin_function": BM25BuiltInFunction(
            input_field_names="text",
            output_field_names=SPARSE_VECTOR_FIELD,
        ),
        "vector_field": [DENSE_VECTOR_FIELD, SPARSE_VECTOR_FIELD],
        "enable_dynamic_field": True,
        "index_params": [
            {"index_type": "AUTOINDEX", "metric_type": "COSINE"},
            {"index_type": "AUTOINDEX", "metric_type": "BM25"},
        ],
    }


def _ensure_orm_connection_for_uri(uri: str) -> None:
    """Register the alias that MilvusClient will assign before Milvus uses ORM."""
    client = MilvusClient(uri=uri)
    try:
        alias = client._using
    finally:
        client.close()
    if not connections.has_connection(alias):
        connections.connect(alias=alias, uri=uri)


def _ensure_orm_connection(vectorstore: Milvus) -> None:
    """Register the client connection for langchain-milvus 0.3.x ORM calls."""
    alias = vectorstore.alias
    if not connections.has_connection(alias):
        uri = vectorstore._connection_args.get("uri", "http://localhost:19530")
        connections.connect(alias=alias, uri=uri)


def _collection_description(embedding_provider: str | None) -> str:
    return (
        f"RAG documents; {EMBEDDING_DESCRIPTION_PREFIX}"
        f"{_embedding_model_name(embedding_provider)}; "
        f"{RETRIEVAL_PROFILE_PREFIX}{HYBRID_RETRIEVAL_PROFILE}"
    )


def _embedding_from_description(description: str | None) -> str | None:
    if not description or EMBEDDING_DESCRIPTION_PREFIX not in description:
        return None
    return description.split(EMBEDDING_DESCRIPTION_PREFIX, 1)[1].split(";", 1)[0].strip()


def _retrieval_profile_from_description(description: str | None) -> str | None:
    if not description or RETRIEVAL_PROFILE_PREFIX not in description:
        return None
    return description.split(RETRIEVAL_PROFILE_PREFIX, 1)[1].split(";", 1)[0].strip()


def _temporary_collection_name(collection_name: str, kind: str) -> str:
    suffix = f"__{kind}_{uuid4().hex[:10]}"
    return f"{collection_name[: 255 - len(suffix)]}{suffix}"


def _bounded_metadata_text(value, field: str, fallback: str = "") -> str:
    text = str(value or fallback)
    return text[: METADATA_TEXT_LIMITS[field]]


def _metadata_page_number(metadata: dict) -> int:
    raw_value = metadata.get("page_number")
    if raw_value is None and metadata.get("page") is not None:
        try:
            raw_value = int(metadata["page"]) + 1
        except (TypeError, ValueError):
            raw_value = 0
    try:
        return max(0, int(raw_value or 0))
    except (TypeError, ValueError):
        return 0


def _replace_collection_safely(
    uri: str,
    collection_name: str,
    documents: list[Document],
    embedding_provider: str | None,
) -> Milvus:
    """Build a staging collection, then promote it with rollback on rename failure."""
    collection_name = _validate_collection_name(collection_name)
    if not documents:
        raise ValueError("No non-empty documents were supplied for indexing")

    staging_name = _temporary_collection_name(collection_name, "staging")
    backup_name = _temporary_collection_name(collection_name, "backup")
    manager = MilvusClient(uri=uri)
    staging_promoted = False
    backup_created = False

    try:
        _ensure_orm_connection_for_uri(uri)
        vectorstore = Milvus(
            **_hybrid_vectorstore_kwargs(embedding_provider),
            connection_args={"uri": uri},
            collection_name=staging_name,
            collection_description=_collection_description(embedding_provider),
            drop_old=False,
        )
        _ensure_orm_connection(vectorstore)
        for start in range(0, len(documents), MILVUS_INSERT_BATCH_SIZE):
            batch = documents[start : start + MILVUS_INSERT_BATCH_SIZE]
            vectorstore.add_documents(
                documents=batch,
                ids=[document.metadata["chunk_id"] for document in batch],
            )
        vectorstore.client.close()

        if manager.has_collection(collection_name):
            manager.rename_collection(collection_name, backup_name)
            backup_created = True

        try:
            manager.rename_collection(staging_name, collection_name)
            staging_promoted = True
        except Exception:
            if backup_created and not manager.has_collection(collection_name):
                manager.rename_collection(backup_name, collection_name)
                backup_created = False
            raise

        if backup_created:
            try:
                manager.drop_collection(backup_name)
                backup_created = False
            except Exception as cleanup_error:
                print(f"Warning: could not remove backup collection '{backup_name}': {cleanup_error}")
    except Exception:
        if not staging_promoted and manager.has_collection(staging_name):
            manager.drop_collection(staging_name)
        raise
    finally:
        manager.close()

    return connect_to_milvus(
        uri,
        collection_name,
        embedding_provider=embedding_provider,
    )


def append_documents(
    uri: str,
    collection_name: str,
    documents: list[Document],
    embedding_provider: str | None = None,
) -> int:
    """Append one document's chunks without replacing other indexed documents."""
    collection_name = _validate_collection_name(collection_name)
    if not documents:
        raise ValueError("No non-empty documents were supplied for indexing")
    for document in documents:
        if not str(document.metadata.get("document_id") or "").strip():
            raise ValueError("Every indexed chunk must contain document_id")
        if not str(document.metadata.get("chunk_id") or "").strip():
            raise ValueError("Every indexed chunk must contain chunk_id")

    manager = MilvusClient(uri=uri)
    try:
        collection_exists = manager.has_collection(collection_name)
    finally:
        manager.close()

    if collection_exists:
        vectorstore = connect_to_milvus(
            uri,
            collection_name,
            embedding_provider=embedding_provider,
        )
    else:
        _ensure_orm_connection_for_uri(uri)
        vectorstore = Milvus(
            **_hybrid_vectorstore_kwargs(embedding_provider),
            connection_args={"uri": uri},
            collection_name=collection_name,
            collection_description=_collection_description(embedding_provider),
            drop_old=False,
        )
        _ensure_orm_connection(vectorstore)

    try:
        for start in range(0, len(documents), MILVUS_INSERT_BATCH_SIZE):
            batch = documents[start : start + MILVUS_INSERT_BATCH_SIZE]
            vectorstore.add_documents(
                documents=batch,
                ids=[document.metadata["chunk_id"] for document in batch],
            )
    finally:
        vectorstore.client.close()
    return len(documents)


def delete_document_chunks(uri: str, collection_name: str, document_id: str) -> int:
    """Delete all chunks belonging to one document from the shared collection."""
    collection_name = _validate_collection_name(collection_name)
    normalized_document_id = str(UUID(document_id))
    client = MilvusClient(uri=uri)
    try:
        if not client.has_collection(collection_name):
            return 0
        result = client.delete(
            collection_name=collection_name,
            filter=f'document_id == "{normalized_document_id}"',
        )
        return int(result.get("delete_count", 0))
    finally:
        client.close()


def load_data_from_local_file(filename: str, directory: str) -> tuple[list[dict], str]:
    file_path = Path(directory) / filename
    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("The JSON root must be a list of documents")
    return data, Path(filename).stem.replace("_", " ")


def _documents_from_local_data(local_data: list[dict], doc_name: str) -> list[Document]:
    documents: list[Document] = []
    for index, item in enumerate(local_data):
        if not isinstance(item, dict):
            raise ValueError(f"Document at index {index} must be a JSON object")
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"metadata at index {index} must be a JSON object")

        page_content = item.get("page_content") or ""
        if not isinstance(page_content, str):
            raise ValueError(f"page_content at index {index} must be a string")
        if not page_content.strip():
            continue

        documents.append(
            Document(
                page_content=page_content,
                metadata={
                    "source": _bounded_metadata_text(
                        metadata.get("source"), "source", doc_name
                    ),
                    "content_type": _bounded_metadata_text(
                        metadata.get("content_type"), "content_type", "text/plain"
                    ),
                    "title": _bounded_metadata_text(metadata.get("title"), "title"),
                    "description": _bounded_metadata_text(
                        metadata.get("description"), "description"
                    ),
                    "language": _bounded_metadata_text(
                        metadata.get("language"), "language", "en"
                    ),
                    "doc_name": _bounded_metadata_text(doc_name, "doc_name"),
                    "source_name": _bounded_metadata_text(
                        metadata.get("source_name"), "source_name", doc_name
                    ),
                    "document_id": _bounded_metadata_text(
                        metadata.get("document_id"), "document_id"
                    ),
                    "chunk_id": _bounded_metadata_text(
                        metadata.get("chunk_id"), "chunk_id"
                    ),
                    "chunk_index": metadata.get("chunk_index", index),
                    "page_number": _metadata_page_number(metadata),
                    "start_index": metadata.get("start_index") or 0,
                },
            )
        )
    return add_chunk_provenance(documents, source_name=doc_name)


def seed_milvus(
    URL_link: str,
    collection_name: str,
    filename: str,
    directory: str,
    embedding_provider: str | None = None,
) -> Milvus:
    local_data, doc_name = load_data_from_local_file(filename, directory)
    documents = _documents_from_local_data(local_data, doc_name)
    return _replace_collection_safely(
        URL_link,
        collection_name,
        documents,
        embedding_provider,
    )


def seed_milvus_live(
    url: str,
    URL_link: str,
    collection_name: str,
    doc_name: str,
    embedding_provider: str | None = None,
) -> Milvus:
    documents = crawl_web(url)
    for document in documents:
        document.metadata.update(
            {
                "source": _bounded_metadata_text(
                    document.metadata.get("source"), "source"
                ),
                "content_type": _bounded_metadata_text(
                    document.metadata.get("content_type"), "content_type", "text/plain"
                ),
                "title": _bounded_metadata_text(
                    document.metadata.get("title"), "title"
                ),
                "description": _bounded_metadata_text(
                    document.metadata.get("description"), "description"
                ),
                "language": _bounded_metadata_text(
                    document.metadata.get("language"), "language", "en"
                ),
                "doc_name": _bounded_metadata_text(doc_name, "doc_name"),
                "source_name": _bounded_metadata_text(
                    document.metadata.get("source_name"), "source_name", doc_name
                ),
                "document_id": _bounded_metadata_text(
                    document.metadata.get("document_id"), "document_id"
                ),
                "chunk_id": _bounded_metadata_text(
                    document.metadata.get("chunk_id"), "chunk_id"
                ),
                "start_index": document.metadata.get("start_index") or 0,
            }
        )
    return _replace_collection_safely(
        URL_link,
        collection_name,
        documents,
        embedding_provider,
    )


def connect_to_milvus(
    URL_link: str,
    collection_name: str,
    embedding_provider: str | None = None,
) -> Milvus:
    collection_name = _validate_collection_name(collection_name)
    client = MilvusClient(uri=URL_link)
    try:
        if not client.has_collection(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        description = client.describe_collection(collection_name).get("description")
    finally:
        client.close()

    expected_embedding = _embedding_model_name(embedding_provider)
    actual_embedding = _embedding_from_description(description)
    if actual_embedding and actual_embedding != expected_embedding:
        raise ValueError(
            f"Collection '{collection_name}' uses '{actual_embedding}', but the query is "
            f"configured for '{expected_embedding}'"
        )
    retrieval_profile = _retrieval_profile_from_description(description)
    if retrieval_profile != HYBRID_RETRIEVAL_PROFILE:
        raise ValueError(
            f"Collection '{collection_name}' does not have the native BM25 schema. "
            "Re-index it with backend.app.services.indexing before querying."
        )

    _ensure_orm_connection_for_uri(URL_link)
    vectorstore = Milvus(
        **_hybrid_vectorstore_kwargs(embedding_provider),
        connection_args={"uri": URL_link},
        collection_name=collection_name,
    )
    _ensure_orm_connection(vectorstore)
    return vectorstore


def main() -> None:
    milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    seed_milvus(milvus_uri, "data_test", "stack_ai.json", "data")


if __name__ == "__main__":
    main()
