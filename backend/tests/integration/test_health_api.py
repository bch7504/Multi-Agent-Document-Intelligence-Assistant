import unittest
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fastapi.testclient import TestClient

from backend.app.api.health import get_milvus_client
from backend.app.database.postgres import get_db_session
from backend.app.main import app


class HealthApiTests(unittest.TestCase):
    def test_liveness_does_not_require_external_services(self):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/health/live",
                headers={"X-Request-ID": "test-request-id"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["version"], "0.1.0")
        self.assertEqual(response.headers["X-Request-ID"], "test-request-id")

    def test_readiness_checks_postgres_and_milvus(self):
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        session = Session(engine)
        milvus = Mock()
        milvus.list_collections.return_value = []
        app.dependency_overrides[get_db_session] = lambda: session
        app.dependency_overrides[get_milvus_client] = lambda: milvus
        try:
            with TestClient(app) as client:
                response = client.get("/api/v1/health/ready")
        finally:
            app.dependency_overrides.clear()
            session.close()
            engine.dispose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["dependencies"],
            {"postgres": "ok", "milvus": "ok"},
        )


if __name__ == "__main__":
    unittest.main()
