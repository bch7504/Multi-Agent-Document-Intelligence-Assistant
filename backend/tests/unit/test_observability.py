import unittest

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from backend.app.core.observability import TokenUsageCallbackHandler


class TokenUsageCallbackHandlerTests(unittest.TestCase):
    def test_collects_standard_usage_metadata(self):
        handler = TokenUsageCallbackHandler()
        response = LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="ok",
                            usage_metadata={
                                "input_tokens": 10,
                                "output_tokens": 4,
                                "total_tokens": 14,
                            },
                        )
                    )
                ]
            ]
        )

        handler.on_llm_end(response)

        self.assertEqual(handler.input_tokens, 10)
        self.assertEqual(handler.output_tokens, 4)
        self.assertEqual(handler.total_tokens, 14)

    def test_collects_openrouter_structured_output_metadata(self):
        handler = TokenUsageCallbackHandler()
        response = LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="{}",
                            response_metadata={
                                "token_usage": {
                                    "prompt_tokens": 21,
                                    "completion_tokens": 7,
                                    "total_tokens": 28,
                                }
                            },
                        )
                    )
                ]
            ]
        )

        handler.on_llm_end(response)

        self.assertEqual(handler.input_tokens, 21)
        self.assertEqual(handler.output_tokens, 7)
        self.assertEqual(handler.total_tokens, 28)


if __name__ == "__main__":
    unittest.main()
