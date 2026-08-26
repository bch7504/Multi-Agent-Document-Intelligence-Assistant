import unittest
import os
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from main import _default_llm_preset


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StreamlitAppTests(unittest.TestCase):
    def test_default_llm_uses_an_available_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_default_llm_preset(), "Qwen2.5 7B (Local)")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            self.assertEqual(
                _default_llm_preset(),
                "GPT-5.6 Luna (OpenRouter)",
            )
        with patch.dict(
            os.environ,
            {"GOOGLE_API_KEY": "test-key", "OPENROUTER_API_KEY": "test-key"},
            clear=True,
        ):
            self.assertEqual(_default_llm_preset(), "Gemini 2.5 Flash")

    def test_app_starts_without_external_services(self):
        app = AppTest.from_file(PROJECT_ROOT / "main.py").run(timeout=30)

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.selectbox[0].options,
            [
                "Gemini 2.5 Flash",
                "GPT-5.6 Luna (OpenRouter)",
                "Qwen2.5 7B (Local)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
