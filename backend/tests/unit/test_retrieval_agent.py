import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from backend.app.agents.retrieval.agent import invoke_agent, run_grounded_qa
from backend.app.core.llm import create_llm


class RecordingAgent:
    def __init__(self):
        self.payload = None

    def invoke(self, payload):
        self.payload = payload
        return {"messages": [AIMessage(content="Câu trả lời thử nghiệm")]}


class AgentTests(unittest.TestCase):
    @patch("backend.app.agents.retrieval.agent.answer_question")
    @patch("backend.app.agents.retrieval.agent.create_llm")
    def test_grounded_qa_uses_configured_llm_and_qa_service(
        self,
        create_llm_mock,
        answer_question_mock,
    ):
        request = object()
        retriever = object()
        llm = object()
        expected = object()
        create_llm_mock.return_value = llm
        answer_question_mock.return_value = expected

        result = run_grounded_qa(
            request,
            retriever,
            llm_choice="ollama",
            openrouter_model="unused",
        )

        self.assertIs(result, expected)
        create_llm_mock.assert_called_once_with(
            "ollama",
            openrouter_model="unused",
        )
        answer_question_mock.assert_called_once_with(
            request=request,
            retriever=retriever,
            llm=llm,
        )

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
            self.assertEqual(ollama.model, "qwen3:8b")

    def test_provider_must_be_selected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "LLM_PROVIDER must be selected"):
                create_llm()

    def test_openrouter_client_uses_selected_model(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            llm = create_llm("OpenRouter", openrouter_model="openai/gpt-5.6-luna")
        self.assertEqual(llm.model_name, "openai/gpt-5.6-luna")
        self.assertEqual(str(llm.openai_api_base), "https://openrouter.ai/api/v1")

    def test_openai_client_uses_selected_model(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-5.6-luna"},
            clear=True,
        ):
            llm = create_llm("openai")
        self.assertEqual(llm.model_name, "gpt-5.6-luna")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported LLM provider"):
            create_llm("unknown")


if __name__ == "__main__":
    unittest.main()
