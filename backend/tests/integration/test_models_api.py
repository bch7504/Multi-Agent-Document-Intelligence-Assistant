import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app.main import app


class ModelsApiTests(unittest.TestCase):
    def test_catalog_reports_availability_without_exposing_keys(self):
        environment = {
            "LLM_PROVIDER": "openrouter",
            "EMBEDDING_PROVIDER": "openai",
            "OPENROUTER_API_KEY": "secret-openrouter-key",
            "OPENROUTER_MODEL": "vendor/chat-model",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-large",
            "OLLAMA_ENABLED": "false",
        }
        with patch.dict(os.environ, environment, clear=True):
            with TestClient(app) as client:
                response = client.get("/api/v1/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["activeChat"]["model"], "vendor/chat-model")
        self.assertEqual(
            payload["activeEmbedding"]["model"], "text-embedding-3-large"
        )
        providers = {item["provider"]: item for item in payload["providers"]}
        self.assertTrue(providers["openrouter"]["configured"])
        self.assertFalse(providers["ollama"]["configured"])
        self.assertNotIn("secret-openrouter-key", response.text)

    @patch("backend.app.api.models._get_embeddings")
    @patch("backend.app.api.models.create_llm")
    def test_validate_models_reports_both_models_as_usable(
        self,
        create_llm: Mock,
        get_embeddings: Mock,
    ):
        create_llm.return_value.invoke.return_value = "OK"
        get_embeddings.return_value.embed_query.return_value = [0.1, 0.2, 0.3]
        payload = {
            "chat": {"provider": "openrouter", "model": "vendor/chat"},
            "embedding": {"provider": "openai", "model": "text-embedding"},
        }

        with TestClient(app) as client:
            response = client.post("/api/v1/models/validate", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["usable"])
        self.assertTrue(response.json()["chat"]["usable"])
        self.assertEqual(
            response.json()["embedding"]["message"],
            "Embedding model responded with 3 dimensions",
        )

    @patch("backend.app.api.models._get_embeddings")
    @patch("backend.app.api.models.create_llm")
    def test_validate_models_reports_failure_without_exposing_secrets(
        self,
        create_llm: Mock,
        get_embeddings: Mock,
    ):
        create_llm.side_effect = ValueError("OPENAI_API_KEY is required when using OpenAI")
        get_embeddings.return_value.embed_query.return_value = [0.1]
        payload = {
            "chat": {"provider": "openai", "model": "missing-model"},
            "embedding": {"provider": "openrouter", "model": "embedding-model"},
        }

        with TestClient(app) as client:
            response = client.post("/api/v1/models/validate", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["usable"])
        self.assertFalse(response.json()["chat"]["usable"])
        self.assertNotIn("secret", response.text.lower())


if __name__ == "__main__":
    unittest.main()
