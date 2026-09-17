"""Import a pre-chunked local JSON dataset into the production document store."""

import argparse
import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.database.postgres import get_session_factory
from backend.app.models.document import DocumentRecord, utc_now
from backend.app.schemas.documents import DocumentSourceType, DocumentStatus
from backend.app.services.indexing import (
    _documents_from_local_data,
    _embedding_model_name,
    append_documents,
    delete_document_chunks,
    load_data_from_local_file,
)


SECTION_NAMESPACE = UUID("6e6e8508-70e2-4fd7-99e7-2c8bfcc72261")
H1_PATTERN = re.compile(r"(?m)^#\s+([^#\r\n].*?)\s*$")


def derive_document_sections(documents: list, document_id: UUID) -> list[dict]:
    """Group consecutive chunks under their first Markdown H1 heading."""
    ordered = sorted(
        documents,
        key=lambda item: int(item.metadata.get("chunk_index") or 0),
    )
    sections: list[dict] = []
    current: dict | None = None

    for document in ordered:
        chunk_index = int(document.metadata.get("chunk_index") or 0)
        match = H1_PATTERN.search(document.page_content or "")
        heading = " ".join(match.group(1).strip().split())[:255] if match else None

        if current is None or (heading and heading != current["title"]):
            title = heading or "Introduction"
            current = {
                "id": str(uuid5(SECTION_NAMESPACE, f"{document_id}:{chunk_index}:{title}")),
                "title": title,
                "start_chunk_index": chunk_index,
                "end_chunk_index": chunk_index,
                "chunk_count": 0,
            }
            sections.append(current)

        current["end_chunk_index"] = chunk_index
        current["chunk_count"] += 1

    return sections


def import_json_dataset(path: Path, name: str) -> DocumentRecord:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Dataset '{path}' was not found")

    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    local_data, doc_name = load_data_from_local_file(path.name, str(path.parent))
    documents = _documents_from_local_data(local_data, doc_name)
    document_ids = {
        str(document.metadata.get("document_id") or "") for document in documents
    }
    document_ids.discard("")
    if len(document_ids) != 1:
        raise ValueError(
            "A production import must contain exactly one stable document_id"
        )
    document_id = UUID(next(iter(document_ids)))
    sections = derive_document_sections(documents, document_id)
    source_uri = str(documents[0].metadata.get("source") or "") or None
    settings = get_settings()
    session_factory = get_session_factory()

    with session_factory() as session:
        existing = session.get(DocumentRecord, document_id)
        if (
            existing is not None
            and existing.checksum == checksum
            and existing.status == DocumentStatus.READY.value
        ):
            if existing.sections != sections:
                existing.sections = sections
                existing.updated_at = utc_now()
                session.commit()
                session.refresh(existing)
            return existing

        delete_document_chunks(
            settings.milvus_uri,
            settings.document_collection_name,
            str(document_id),
        )
        chunk_count = append_documents(
            settings.milvus_uri,
            settings.document_collection_name,
            documents,
        )
        page_numbers = {
            int(document.metadata.get("page_number") or 0)
            for document in documents
            if int(document.metadata.get("page_number") or 0) > 0
        }
        now = utc_now()
        record = existing or DocumentRecord(id=document_id)
        record.name = name[:255]
        record.mime_type = "application/json"
        record.source_type = DocumentSourceType.JSON.value
        record.source_uri = source_uri
        record.storage_key = f"local-json:{path.name}"
        record.checksum = checksum
        record.size_bytes = len(raw)
        record.status = DocumentStatus.READY.value
        record.page_count = len(page_numbers) or 1
        record.chunk_count = chunk_count
        record.sections = sections
        record.embedding_model = _embedding_model_name()
        record.error_message = None
        record.updated_at = now
        if existing is None:
            record.created_at = now
            session.add(record)
        session.commit()
        session.refresh(record)
        return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--name", default="Stack AI Documentation")
    args = parser.parse_args()
    record = import_json_dataset(args.path, args.name)
    print(
        f"Imported document_id={record.id} status={record.status} "
        f"chunks={record.chunk_count} embedding={record.embedding_model}"
    )


if __name__ == "__main__":
    main()
