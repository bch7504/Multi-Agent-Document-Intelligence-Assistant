import unittest
from uuid import uuid4

from langchain_core.documents import Document

from backend.app.graph.graph import create_assistant_runtime
from backend.app.graph.state import MAX_CHECKPOINT_MESSAGES, merge_history
from backend.app.schemas.assistant import AssistantRunRequest


class FakeRetriever:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def invoke_scoped(self, query, document_ids):
        self.queries.append((query, tuple(document_ids)))
        return self.documents


class FakeStructuredModel:
    def __init__(self, owner, schema):
        self.owner = owner
        self.schema = schema

    def invoke(self, messages, config=None):
        self.owner.calls.append((self.schema.__name__, messages))
        return self.owner.response_for(self.schema.__name__)


class FakeLlm:
    def __init__(self, chunk_id, auto_task="summary", review_decisions=None):
        self.chunk_id = chunk_id
        self.auto_task = auto_task
        self.review_decisions = list(review_decisions or [{"status": "pass"}])
        self.calls = []

    def with_structured_output(self, schema):
        return FakeStructuredModel(self, schema)

    def response_for(self, schema_name):
        if schema_name == "TaskResolution":
            return {"task": self.auto_task}
        if schema_name == "RewrittenQuery":
            return {"query": "Standalone follow-up about RAG"}
        if schema_name == "GroundedAnswerDraft":
            return {
                "answer": "RAG retrieves evidence before generation.",
                "cited_chunk_ids": [str(self.chunk_id)],
            }
        if schema_name == "SummaryMapDraft":
            return {
                "summary": "The document explains grounded retrieval.",
                "cited_chunk_ids": [str(self.chunk_id)],
            }
        if schema_name == "SummaryDraft":
            return {
                "answer": "The document summarizes grounded retrieval.",
                "cited_chunk_ids": [str(self.chunk_id)],
            }
        if schema_name == "QuizDraft":
            return {
                "questions": [
                    {
                        "question": "What does RAG do before generation?",
                        "options": ["Retrieves evidence", "Deletes evidence"],
                        "correct_option_index": 0,
                        "explanation": "The document says RAG retrieves evidence.",
                        "cited_chunk_ids": [str(self.chunk_id)],
                    }
                ]
            }
        if schema_name == "GroundingReviewDecision":
            if len(self.review_decisions) > 1:
                return self.review_decisions.pop(0)
            return self.review_decisions[0]
        raise AssertionError(f"Unexpected schema: {schema_name}")


class AssistantGraphTests(unittest.TestCase):
    def setUp(self):
        self.document_id = uuid4()
        self.chunk_id = uuid4()
        self.retriever = FakeRetriever(
            [
                Document(
                    page_content="RAG retrieves evidence before generation.",
                    metadata={
                        "document_id": str(self.document_id),
                        "chunk_id": str(self.chunk_id),
                        "source_name": "rag.pdf",
                        "page_number": 2,
                    },
                )
            ]
        )
        self.llm = FakeLlm(self.chunk_id)
        self.runtime = create_assistant_runtime(self.retriever, self.llm)

    def request(self, task, message="What is RAG?", conversation_id=None):
        return AssistantRunRequest(
            conversation_id=conversation_id or uuid4(),
            document_ids=[self.document_id],
            task=task,
            message=message,
        )

    def test_explicit_qa_skips_task_resolver_and_returns_trace_and_citation(self):
        response = self.runtime.invoke(self.request("qa"))

        trace_ids = [step.id for step in response.trace]
        self.assertEqual(response.task, "qa")
        self.assertNotIn("resolve_task", trace_ids)
        self.assertEqual(
            trace_ids,
            [
                "rewrite_query",
                "retrieve_qa",
                "answer_qa",
                "validate_output",
                "review_output",
                "finalize",
                "total",
            ],
        )
        self.assertEqual(response.citations[0].chunk_id, self.chunk_id)
        self.assertNotIn("TaskResolution", [name for name, _ in self.llm.calls])

    def test_auto_summary_uses_resolver_and_map_reduce(self):
        response = self.runtime.invoke(self.request("auto", "Summarize this document"))

        trace_ids = [step.id for step in response.trace]
        self.assertEqual(response.task, "summary")
        self.assertEqual(
            trace_ids,
            [
                "resolve_task",
                "resolve_summary_scope",
                "retrieve_summary",
                "map_summary",
                "reduce_summary",
                "validate_output",
                "review_output",
                "finalize",
                "total",
            ],
        )
        schemas = [name for name, _ in self.llm.calls]
        self.assertIn("TaskResolution", schemas)
        self.assertIn("SummaryMapDraft", schemas)
        self.assertIn("SummaryDraft", schemas)
        self.assertEqual(response.citations[0].chunk_id, self.chunk_id)

    def test_checkpointer_uses_conversation_history_for_follow_up(self):
        conversation_id = uuid4()
        self.runtime.invoke(self.request("qa", conversation_id=conversation_id))
        self.runtime.invoke(
            self.request(
                "qa",
                message="How does it work?",
                conversation_id=conversation_id,
            )
        )

        self.assertEqual(self.retriever.queries[-1][0], "Standalone follow-up about RAG")
        self.assertIn("RewrittenQuery", [name for name, _ in self.llm.calls])

    def test_quiz_returns_one_valid_answer_explanation_and_citation(self):
        response = self.runtime.invoke(self.request("quiz", "Create a quiz"))

        self.assertEqual(response.task, "quiz")
        self.assertEqual(response.review.status, "pass")
        self.assertIsNotNone(response.quiz)
        question = response.quiz.questions[0]
        self.assertEqual(question.correct_option_id, "A")
        self.assertTrue(question.explanation)
        self.assertEqual(question.citations[0].chunk_id, self.chunk_id)

    def test_auto_task_can_route_to_quiz(self):
        self.llm.auto_task = "quiz"

        response = self.runtime.invoke(self.request("auto", "Create a quiz"))

        self.assertEqual(response.task, "quiz")
        self.assertIsNotNone(response.quiz)
        self.assertEqual(response.trace[0].id, "resolve_task")

    def test_reviewer_feedback_retries_once_then_passes(self):
        llm = FakeLlm(
            self.chunk_id,
            review_decisions=[
                {
                    "status": "fail",
                    "feedback": "Make the answer more directly grounded.",
                    "retry_target": "generation",
                },
                {"status": "pass"},
            ],
        )
        runtime = create_assistant_runtime(self.retriever, llm)

        response = runtime.invoke(self.request("qa"))

        self.assertEqual(response.review.status, "pass")
        self.assertEqual(response.review.retry_count, 1)
        self.assertEqual(
            [step.id for step in response.trace].count("prepare_retry"),
            1,
        )

    def test_invalid_citations_are_blocked_after_two_retries(self):
        runtime = create_assistant_runtime(
            self.retriever,
            FakeLlm(uuid4()),
        )

        response = runtime.invoke(self.request("qa"))

        self.assertEqual(response.review.status, "fail")
        self.assertEqual(response.review.retry_count, 2)
        self.assertEqual(response.citations, [])
        self.assertIn("Unable to produce", response.answer)
        self.assertEqual(
            [step.id for step in response.trace].count("answer_qa"),
            3,
        )

    def test_checkpoint_history_is_bounded(self):
        existing = [
            {"role": "user", "content": str(index)}
            for index in range(MAX_CHECKPOINT_MESSAGES)
        ]

        merged = merge_history(
            existing,
            [{"role": "assistant", "content": "new"}],
        )

        self.assertEqual(len(merged), MAX_CHECKPOINT_MESSAGES)
        self.assertEqual(merged[-1]["content"], "new")
        self.assertEqual(merged[0]["content"], "1")


if __name__ == "__main__":
    unittest.main()
