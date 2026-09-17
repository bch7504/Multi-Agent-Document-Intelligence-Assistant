import os
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
