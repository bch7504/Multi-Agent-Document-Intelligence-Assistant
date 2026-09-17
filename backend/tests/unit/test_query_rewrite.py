import unittest

from backend.app.services.query_rewrite import (
    MAX_HISTORY_CHARACTERS,
    _bounded_history,
    rewrite_query,
)


class _StructuredLlm:
    def __init__(self, response):
        self.response = response
        self.schema = None
        self.messages = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages, config=None):
        self.messages = messages
        return self.response


class QueryRewriteTests(unittest.TestCase):
    def test_without_history_returns_original_without_calling_llm(self):
        llm = _StructuredLlm({"query": "unused"})

        query = rewrite_query("  What is RAG?  ", [], llm)

        self.assertEqual(query, "What is RAG?")
        self.assertIsNone(llm.messages)

    def test_follow_up_is_rewritten_as_standalone_query(self):
        llm = _StructuredLlm(
            {"query": "How does StackAI Sliding Window memory store messages?"}
        )

        query = rewrite_query(
            "How does it store messages?",
            [
                {"role": "user", "content": "What memory modes does StackAI have?"},
                {"role": "assistant", "content": "It supports Sliding Window."},
            ],
            llm,
        )

        self.assertEqual(
            query,
            "How does StackAI Sliding Window memory store messages?",
        )
        self.assertIn("What memory modes", llm.messages[1][1])
        self.assertIn("How does it store messages?", llm.messages[1][1])

    def test_history_is_role_filtered_and_bounded(self):
        history = [
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "x" * (MAX_HISTORY_CHARACTERS + 100)},
        ]

        bounded = _bounded_history(history)

        self.assertEqual(len(bounded), 1)
        self.assertEqual(bounded[0]["role"], "user")
        self.assertEqual(len(bounded[0]["content"]), MAX_HISTORY_CHARACTERS)


if __name__ == "__main__":
    unittest.main()
