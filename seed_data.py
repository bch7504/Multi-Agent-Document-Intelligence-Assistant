import json
import os
import re
from pathlib import Path
from uuid import uuid4

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus
from langchain_ollama import OllamaEmbeddings
from pymilvus import MilvusClient, connections

from crawl import crawl_web


HUGGINGFACE_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DESCRIPTION_PREFIX = "embedding_model="
COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")
MILVUS_INSERT_BATCH_SIZE = 100
METADATA_TEXT_LIMITS = {
    "source": 2_048,
    "content_type": 255,
    "title": 1_000,
    "description": 4_000,
    "language": 32,
    "doc_name": 255,
}


def _validate_collection_name(collection_name: str) -> str:
    collection_name = collection_name.strip()
    if not COLLECTION_NAME_PATTERN.fullmatch(collection_name):
        raise ValueError(
            "Collection name must start with a letter or underscore, contain only "
            "letters, numbers, and underscores, and be at most 255 characters"
        )
    return collection_name


def _embedding_model_name(use_ollama: bool) -> str:
    if use_ollama:
        return f"ollama:{OLLAMA_EMBEDDING_MODEL}"
    return f"huggingface:{HUGGINGFACE_EMBEDDING_MODEL}"


def _get_embeddings(use_ollama: bool):
    if use_ollama:
        return OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL)
    return HuggingFaceEmbeddings(model_name=HUGGINGFACE_EMBEDDING_MODEL)


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


def _collection_description(use_ollama: bool) -> str:
    return f"RAG documents; {EMBEDDING_DESCRIPTION_PREFIX}{_embedding_model_name(use_ollama)}"


def _embedding_from_description(description: str | None) -> str | None:
    if not description or EMBEDDING_DESCRIPTION_PREFIX not in description:
        return None
    return description.split(EMBEDDING_DESCRIPTION_PREFIX, 1)[1].split(";", 1)[0].strip()


def _temporary_collection_name(collection_name: str, kind: str) -> str:
    suffix = f"__{kind}_{uuid4().hex[:10]}"
    return f"{collection_name[: 255 - len(suffix)]}{suffix}"


def _bounded_metadata_text(value, field: str, fallback: str = "") -> str:
    text = str(value or fallback)
    return text[: METADATA_TEXT_LIMITS[field]]


def _replace_collection_safely(
    uri: str,
    collection_name: str,
    documents: list[Document],
    use_ollama: bool,
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
            embedding_function=_get_embeddings(use_ollama),
            connection_args={"uri": uri},
            collection_name=staging_name,
            collection_description=_collection_description(use_ollama),
            drop_old=False,
        )
        _ensure_orm_connection(vectorstore)
        for start in range(0, len(documents), MILVUS_INSERT_BATCH_SIZE):
            batch = documents[start : start + MILVUS_INSERT_BATCH_SIZE]
            vectorstore.add_documents(
                documents=batch,
                ids=[str(uuid4()) for _ in batch],
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

    return connect_to_milvus(uri, collection_name, use_ollama=use_ollama)


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
                    "start_index": metadata.get("start_index") or 0,
                },
            )
        )
    return documents


def seed_milvus(
    URL_link: str,
    collection_name: str,
    filename: str,
    directory: str,
    use_ollama: bool = False,
) -> Milvus:
    local_data, doc_name = load_data_from_local_file(filename, directory)
    documents = _documents_from_local_data(local_data, doc_name)
    return _replace_collection_safely(URL_link, collection_name, documents, use_ollama)


def seed_milvus_live(
    url: str,
    URL_link: str,
    collection_name: str,
    doc_name: str,
    use_ollama: bool = False,
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
                "start_index": document.metadata.get("start_index") or 0,
            }
        )
    return _replace_collection_safely(URL_link, collection_name, documents, use_ollama)


def connect_to_milvus(
    URL_link: str,
    collection_name: str,
    use_ollama: bool = False,
) -> Milvus:
    collection_name = _validate_collection_name(collection_name)
    client = MilvusClient(uri=URL_link)
    try:
        if not client.has_collection(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        description = client.describe_collection(collection_name).get("description")
    finally:
        client.close()

    expected_embedding = _embedding_model_name(use_ollama)
    actual_embedding = _embedding_from_description(description)
    if actual_embedding and actual_embedding != expected_embedding:
        raise ValueError(
            f"Collection '{collection_name}' uses '{actual_embedding}', but the query is "
            f"configured for '{expected_embedding}'"
        )

    _ensure_orm_connection_for_uri(URL_link)
    vectorstore = Milvus(
        embedding_function=_get_embeddings(use_ollama),
        connection_args={"uri": URL_link},
        collection_name=collection_name,
    )
    _ensure_orm_connection(vectorstore)
    return vectorstore


def main() -> None:
    milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    seed_milvus(milvus_uri, "data_test", "stack_ai.json", "data", use_ollama=False)


if __name__ == "__main__":
    main()
