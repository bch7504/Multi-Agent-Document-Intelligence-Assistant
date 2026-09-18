import unittest
import os
from unittest.mock import patch
from uuid import uuid4

from langchain_core.documents import Document

from backend.app.graph.graph import create_assistant_runtime
from backend.app.graph.state import MAX_CHECKPOINT_MESSAGES, merge_history
from backend.app.schemas.assistant import AssistantRunRequest
from backend.app.services.quiz import resolve_quiz_question_count


class FakeRetriever:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []
        self.full_document_scopes = []

    def invoke_scoped(self, query, document_ids):
        self.queries.append((query, tuple(document_ids)))
        return self.documents

    def invoke_all_scoped(self, document_ids):
        self.full_document_scopes.append(tuple(document_ids))
        return self.documents


class FakeStructuredModel:
    def __init__(self, owner, schema):
        self.owner = owner
        self.schema = schema

    def invoke(self, messages, config=None):
        self.owner.calls.append((self.schema.__name__, messages))
        return self.owner.response_for(self.schema.__name__)


class FakeLlm:
    def __init__(
        self,
        chunk_id,
        auto_task="summary",
        review_decisions=None,
        quiz_question_count=1,
    ):
        self.chunk_id = chunk_id
        self.auto_task = auto_task
        self.review_decisions = list(review_decisions or [{"status": "pass"}])
        self.quiz_question_count = quiz_question_count
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
                        "question": f"Question {index}: What does RAG do before generation?",
                        "options": ["Retrieves evidence", "Deletes evidence"],
                        "correct_option_index": 0,
                        "explanation": "The document says RAG retrieves evidence.",
                        "cited_chunk_ids": [str(self.chunk_id)],
                    }
                    for index in range(1, self.quiz_question_count + 1)
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

    def test_auto_summary_uses_adaptive_single_pass(self):
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
        self.assertNotIn("SummaryDraft", schemas)
        self.assertEqual(response.citations[0].chunk_id, self.chunk_id)
        self.assertEqual(self.retriever.full_document_scopes, [(self.document_id,)])
        self.assertEqual(self.retriever.queries, [])

    def test_large_summary_keeps_map_reduce_path(self):
        second_chunk_id = uuid4()
        retriever = FakeRetriever(
            [
                self.retriever.documents[0],
                Document(
                    page_content="A second section describes access controls.",
                    metadata={
                        "document_id": str(self.document_id),
                        "chunk_id": str(second_chunk_id),
                        "source_name": "rag.pdf",
                        "page_number": 3,
                    },
                ),
            ]
        )
        llm = FakeLlm(self.chunk_id)
        runtime = create_assistant_runtime(retriever, llm)

        with patch.dict(
            os.environ,
            {
                "SUMMARY_SINGLE_PASS_CHARACTERS": "1",
                "SUMMARY_FULL_DOCUMENT_BATCH_CHARACTERS": "1",
                "SUMMARY_MAP_BATCH_CHARACTERS": "1",
            },
        ):
            response = runtime.invoke(self.request("summary", "Summarize this document"))

        schemas = [name for name, _ in llm.calls]
        self.assertEqual(schemas.count("SummaryMapDraft"), 2)
        self.assertIn("SummaryDraft", schemas)
        self.assertEqual(response.review.status, "pass")

    def test_summary_review_retry_does_not_reload_full_document(self):
        llm = FakeLlm(
            self.chunk_id,
            auto_task="summary",
            review_decisions=[
                {
                    "status": "fail",
                    "feedback": "Revise the final summary.",
                    "retry_target": "retrieval",
                },
                {"status": "pass"},
            ],
        )
        runtime = create_assistant_runtime(self.retriever, llm)

        response = runtime.invoke(self.request("summary", "Summarize this document"))

        self.assertEqual(response.review.status, "pass")
        self.assertEqual(response.review.retry_count, 1)
        self.assertEqual(len(self.retriever.full_document_scopes), 1)
        schemas = [name for name, _ in llm.calls]
        self.assertEqual(schemas.count("SummaryMapDraft"), 1)
        self.assertEqual(schemas.count("SummaryDraft"), 1)

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
        response = self.runtime.invoke(self.request("quiz", "Create a 1-question quiz"))

        self.assertEqual(response.task, "quiz")
        self.assertEqual(response.review.status, "pass")
        self.assertIsNotNone(response.quiz)
        question = response.quiz.questions[0]
        self.assertEqual(question.correct_option_id, "A")
        self.assertTrue(question.explanation)
        self.assertEqual(question.citations[0].chunk_id, self.chunk_id)

    def test_quiz_uses_question_count_requested_by_user(self):
        llm = FakeLlm(self.chunk_id, quiz_question_count=3)
        runtime = create_assistant_runtime(self.retriever, llm)

        response = runtime.invoke(self.request("quiz", "Tạo quiz gồm 3 câu hỏi"))

        self.assertEqual(response.review.status, "pass")
        self.assertEqual(len(response.quiz.questions), 3)
        quiz_call = next(messages for name, messages in llm.calls if name == "QuizDraft")
        self.assertIn("Return exactly 3 questions", quiz_call[1][1])

    def test_quiz_defaults_to_five_questions_when_count_is_omitted(self):
        llm = FakeLlm(self.chunk_id, quiz_question_count=5)
        runtime = create_assistant_runtime(self.retriever, llm)

        response = runtime.invoke(self.request("quiz", "Create a quiz about RAG"))

        self.assertEqual(response.review.status, "pass")
        self.assertEqual(len(response.quiz.questions), 5)

    def test_quiz_count_understands_common_vietnamese_and_english_requests(self):
        self.assertEqual(resolve_quiz_question_count("Tạo 7 câu hỏi"), 7)
        self.assertEqual(resolve_quiz_question_count("Create a three-question quiz"), 3)
        self.assertEqual(resolve_quiz_question_count("Tạo năm câu về RAG"), 5)
        self.assertEqual(resolve_quiz_question_count("Create a quiz"), 5)
        self.assertEqual(resolve_quiz_question_count("Create 50 questions"), 20)

    def test_auto_task_can_route_to_quiz(self):
        self.llm.auto_task = "quiz"
        self.llm.quiz_question_count = 5

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
