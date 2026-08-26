import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent import create_llm, invoke_agent


class RecordingAgent:
    def __init__(self):
        self.payload = None

    def invoke(self, payload):
        self.payload = payload
        return {"messages": [AIMessage(content="Câu trả lời thử nghiệm")]}


class AgentTests(unittest.TestCase):
    def test_invoke_agent_uses_langchain_messages_schema(self):
        agent = RecordingAgent()

        output = invoke_agent(
            agent,
            [
                {"role": "human", "content": "Xin chào"},
                {"role": "assistant", "content": "Chào bạn"},
            ],
        )

        self.assertEqual(output, "Câu trả lời thử nghiệm")
        self.assertEqual(
            agent.payload,
            {
                "messages": [
                    {"role": "user", "content": "Xin chào"},
                    {"role": "assistant", "content": "Chào bạn"},
                ]
            },
        )

    def test_openrouter_key_is_only_required_for_openrouter(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                create_llm("OpenRouter")

            ollama = create_llm("Ollama")
            self.assertEqual(ollama.model, "qwen2.5:7b")

    def test_openrouter_client_uses_selected_model(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            llm = create_llm("OpenRouter", openrouter_model="openai/gpt-5.6-luna")
        self.assertEqual(llm.model_name, "openai/gpt-5.6-luna")
        self.assertEqual(str(llm.openai_api_base), "https://openrouter.ai/api/v1")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported LLM provider"):
            create_llm("unknown")


if __name__ == "__main__":
    unittest.main()
