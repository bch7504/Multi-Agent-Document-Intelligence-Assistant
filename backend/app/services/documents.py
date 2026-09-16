"""Synchronous MVP document lifecycle orchestration."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from langchain_core.documents import Document
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.ingestion.pdf import EmptyPdfError, parse_and_chunk_pdf
from backend.app.models.document import DocumentRecord, utc_now
from backend.app.schemas.documents import DocumentSourceType, DocumentStatus
from backend.app.services.indexing import (
    _embedding_model_name,
    append_documents,
    delete_document_chunks,
)
from backend.app.storage.local import LocalDocumentStorage


class DocumentNotFoundError(LookupError):
    pass


class UnsupportedDocumentError(ValueError):
    pass


PdfParser = Callable[[str | Path, UUID, str], tuple[list[Document], int]]
DocumentIndexer = Callable[[list[Document]], int]
ChunkDeleter = Callable[[UUID], int]
EmbeddingNameResolver = Callable[[], str]


class DocumentService:
    def __init__(
        self,
        session: Session,
        storage: LocalDocumentStorage,
        parser: PdfParser,
        indexer: DocumentIndexer,
        chunk_deleter: ChunkDeleter,
        embedding_name: EmbeddingNameResolver,
    ) -> None:
        self.session = session
        self.storage = storage
        self.parser = parser
        self.indexer = indexer
        self.chunk_deleter = chunk_deleter
        self.embedding_name = embedding_name

    @staticmethod
    def _validate_upload(upload: UploadFile) -> str:
        filename = Path(upload.filename or "").name.strip()
        if not filename or not filename.lower().endswith(".pdf"):
            raise UnsupportedDocumentError("Only .pdf files are supported in the MVP")
        if upload.content_type not in {"application/pdf", "application/octet-stream"}:
            raise UnsupportedDocumentError("Only application/pdf uploads are supported")
        return filename[:255]

    async def create_from_upload(self, upload: UploadFile) -> DocumentRecord:
        filename = self._validate_upload(upload)
        document_id = uuid4()
        stored = await self.storage.save_pdf(document_id, upload)
        record = DocumentRecord(
            id=document_id,
            name=filename,
            mime_type="application/pdf",
            source_type=DocumentSourceType.UPLOAD.value,
            source_uri=None,
            storage_key=stored.key,
            checksum=stored.checksum,
            size_bytes=stored.size_bytes,
            status=DocumentStatus.UPLOADED.value,
        )
        try:
            self.session.add(record)
            self.session.commit()
            self.session.refresh(record)
        except Exception:
            self.session.rollback()
            self.storage.delete(stored.key)
            raise
        return self._process(record, stored.path)

    def _process(self, record: DocumentRecord, path: Path) -> DocumentRecord:
        record.status = DocumentStatus.PROCESSING.value
        record.error_message = None
        record.updated_at = utc_now()
        self.session.commit()

        try:
            chunks, page_count = self.parser(path, record.id, record.name)
        except EmptyPdfError as error:
            return self._mark_failed(record, str(error))
        except Exception:
            return self._mark_failed(record, "PDF could not be parsed")

        try:
            embedding_model = self.embedding_name()
            chunk_count = self.indexer(chunks)
        except Exception:
            try:
                self.chunk_deleter(record.id)
            except Exception:
                pass
            return self._mark_failed(record, "Document could not be indexed")

        record.status = DocumentStatus.READY.value
        record.page_count = page_count
        record.chunk_count = chunk_count
        record.embedding_model = embedding_model[:255]
        record.error_message = None
        record.updated_at = utc_now()
        self.session.commit()
        self.session.refresh(record)
        return record

    def _mark_failed(self, record: DocumentRecord, message: str) -> DocumentRecord:
        record.status = DocumentStatus.FAILED.value
        record.error_message = message[:1_000]
        record.updated_at = utc_now()
        self.session.commit()
        self.session.refresh(record)
        return record

    def list(self, limit: int, offset: int) -> tuple[list[DocumentRecord], int]:
        items = list(
            self.session.scalars(
                select(DocumentRecord)
                .order_by(DocumentRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(DocumentRecord)) or 0
        return items, total

    def get(self, document_id: UUID) -> DocumentRecord:
        record = self.session.get(DocumentRecord, document_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {document_id} was not found")
        return record

    def delete(self, document_id: UUID) -> None:
        record = self.get(document_id)
        self.chunk_deleter(document_id)
        self.storage.delete(record.storage_key)
        self.session.delete(record)
        self.session.commit()


def build_document_service(session: Session, settings: Settings | None = None) -> DocumentService:
    settings = settings or get_settings()
    return DocumentService(
        session=session,
        storage=LocalDocumentStorage(
            settings.document_storage_path,
            settings.max_upload_bytes,
        ),
        parser=parse_and_chunk_pdf,
        indexer=lambda chunks: append_documents(
            settings.milvus_uri,
            settings.document_collection_name,
            chunks,
        ),
        chunk_deleter=lambda document_id: delete_document_chunks(
            settings.milvus_uri,
            settings.document_collection_name,
            str(document_id),
        ),
        embedding_name=lambda: _embedding_model_name(),
    )
