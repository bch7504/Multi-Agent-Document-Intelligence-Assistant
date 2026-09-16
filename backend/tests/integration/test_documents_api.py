import io
import unittest
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from langchain_core.documents import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.api.documents import get_document_service
from backend.app.database.postgres import Base
from backend.app.main import app
from backend.app.services.documents import DocumentService
from backend.app.storage.local import LocalDocumentStorage


class DocumentsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.indexed_chunks = []
        self.deleted_document_ids = []

        def parse_pdf(path, document_id, name):
            return (
                [
                    Document(
                        page_content="Nội dung trang một",
                        metadata={
                            "document_id": str(document_id),
                            "chunk_id": "660ca553-f4c7-4e5e-86bc-b82eed0870c0",
                            "page_number": 1,
                            "source_name": name,
                        },
                    )
                ],
                2,
            )

        def index_chunks(chunks):
            self.indexed_chunks.extend(chunks)
            return len(chunks)

        self.service = DocumentService(
            session=self.session,
            storage=LocalDocumentStorage(self.temp.name, 1024 * 1024),
            parser=parse_pdf,
            indexer=index_chunks,
            chunk_deleter=lambda document_id: self.deleted_document_ids.append(document_id) or 1,
            embedding_name=lambda: "openai:text-embedding-3-small",
        )
        app.dependency_overrides[get_document_service] = lambda: self.service
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.session.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_upload_index_list_get_and_delete(self):
        upload = self.client.post(
            "/api/v1/documents",
            files={"file": ("guide.pdf", io.BytesIO(b"%PDF-1.4\ntest"), "application/pdf")},
        )
        self.assertEqual(upload.status_code, 201)
        document = upload.json()
        self.assertEqual(document["status"], "ready")
        self.assertEqual(document["pageCount"], 2)
        self.assertEqual(document["chunkCount"], 1)
        self.assertEqual(len(self.indexed_chunks), 1)
        self.assertEqual(self.indexed_chunks[0].metadata["document_id"], document["id"])

        listing = self.client.get("/api/v1/documents").json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["id"], document["id"])

        detail = self.client.get(f"/api/v1/documents/{document['id']}")
        self.assertEqual(detail.status_code, 200)

        deleted = self.client.delete(f"/api/v1/documents/{document['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(len(self.deleted_document_ids), 1)
        self.assertEqual(self.client.get("/api/v1/documents").json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
