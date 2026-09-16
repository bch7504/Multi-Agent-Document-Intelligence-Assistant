import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import UploadFile
from langchain_core.documents import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from backend.app.database.postgres import Base
from backend.app.ingestion.pdf import EmptyPdfError
from backend.app.schemas.documents import DocumentStatus
from backend.app.services.documents import DocumentService
from backend.app.storage.local import LocalDocumentStorage, UploadTooLargeError


def _upload(content: bytes = b"%PDF-1.4\ntest") -> UploadFile:
    return UploadFile(
        filename="guide.pdf",
        file=io.BytesIO(content),
        headers=Headers({"content-type": "application/pdf"}),
    )


class DocumentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.deleted_ids = []

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp.cleanup()

    def _service(self, parser=None, indexer=None, max_bytes=1024):
        parser = parser or (
            lambda path, document_id, name: (
                [
                    Document(
                        page_content="Nội dung",
                        metadata={
                            "document_id": str(document_id),
                            "chunk_id": "b6b3e33f-f42c-4c15-9bf7-32daaa6cedaa",
                            "page_number": 1,
                        },
                    )
                ],
                1,
            )
        )
        return DocumentService(
            session=self.session,
            storage=LocalDocumentStorage(self.temp.name, max_bytes),
            parser=parser,
            indexer=indexer or (lambda chunks: len(chunks)),
            chunk_deleter=lambda document_id: self.deleted_ids.append(document_id) or 1,
            embedding_name=lambda: "openai:text-embedding-3-small",
        )

    async def test_upload_runs_full_lifecycle_to_ready(self):
        record = await self._service().create_from_upload(_upload())

        self.assertEqual(record.status, DocumentStatus.READY.value)
        self.assertEqual(record.page_count, 1)
        self.assertEqual(record.chunk_count, 1)
        self.assertEqual(record.embedding_model, "openai:text-embedding-3-small")
        self.assertTrue((Path(self.temp.name) / record.storage_key).exists())

    async def test_parse_failure_is_persisted_as_safe_failed_status(self):
        def fail_parser(path, document_id, name):
            raise EmptyPdfError("PDF does not contain extractable text")

        record = await self._service(parser=fail_parser).create_from_upload(_upload())

        self.assertEqual(record.status, DocumentStatus.FAILED.value)
        self.assertEqual(record.error_message, "PDF does not contain extractable text")

    async def test_index_failure_is_failed_and_cleans_partial_chunks(self):
        def fail_index(chunks):
            raise RuntimeError("provider response must not leak")

        record = await self._service(indexer=fail_index).create_from_upload(_upload())

        self.assertEqual(record.status, DocumentStatus.FAILED.value)
        self.assertEqual(record.error_message, "Document could not be indexed")
        self.assertEqual(self.deleted_ids, [record.id])

    async def test_upload_limit_removes_partial_file(self):
        with self.assertRaises(UploadTooLargeError):
            await self._service(max_bytes=5).create_from_upload(_upload())
        self.assertEqual(list(Path(self.temp.name).glob("*")), [])

    async def test_delete_removes_database_file_and_chunks(self):
        service = self._service()
        record = await service.create_from_upload(_upload())

        service.delete(record.id)

        self.assertEqual(self.deleted_ids, [record.id])
        self.assertFalse((Path(self.temp.name) / record.storage_key).exists())
        self.assertEqual(service.list(50, 0)[1], 0)


if __name__ == "__main__":
    unittest.main()
