import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.retrieval import (
    RetrievalCase,
    evaluate_retrieval,
    load_cases,
)
from backend.app.rag.schemas import RetrievedChunk


def chunk(content: str, rank: int, chunk_id=None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid4(),
        document_id=uuid4(),
        content=content,
        source_name="test",
        rank=rank,
    )


class RetrievalEvaluationTests(unittest.TestCase):
    def test_active_silver_phrases_exist_in_current_corpus(self):
        repository_root = Path(__file__).resolve().parents[3]
        cases = load_cases(
            repository_root
            / "backend"
            / "app"
            / "evaluation"
            / "datasets"
            / "stack_ai_retrieval_v2.json"
        )
        corpus_path = repository_root / "data" / "stack_ai.json"
        if not corpus_path.exists():
            self.skipTest("Optional local Stack AI corpus is not available")
        documents = json.loads(
            corpus_path.read_text(encoding="utf-8")
        )
        corpus = "\n".join(document["page_content"] for document in documents).casefold()

        silver_cases = [case for case in cases if not case.relevant_chunk_ids]
        missing = {
            case.id: [
                phrase
                for phrase in case.expected_phrases
                if phrase.casefold() not in corpus
            ]
            for case in silver_cases
        }
        missing = {case_id: phrases for case_id, phrases in missing.items() if phrases}

        self.assertEqual(len(silver_cases), 20)
        self.assertEqual(missing, {})

    def test_calculates_hit_recall_and_reciprocal_rank(self):
        cases = [
            RetrievalCase(
                id="case-1",
                question="question",
                expected_phrases=("alpha", "beta"),
            )
        ]

        report = evaluate_retrieval(
            cases,
            retrieve=lambda _question: [
                chunk("irrelevant", rank=1),
                chunk("alpha and beta are here", rank=2),
            ],
            k=2,
        )

        self.assertEqual(report.hit_rate_at_k, 1.0)
        self.assertEqual(report.mean_recall_at_k, 1.0)
        self.assertEqual(report.mean_reciprocal_rank, 0.5)
        self.assertEqual(report.silver_case_count, 1)
        self.assertEqual(report.gold_case_count, 0)
        self.assertIsNone(report.gold_metrics)
        self.assertEqual(report.silver_metrics.case_count, 1)
        self.assertGreater(report.mean_ndcg_at_k, 0)

    def test_k_limits_evidence_considered(self):
        cases = [RetrievalCase("case-1", "question", ("answer",))]

        report = evaluate_retrieval(
            cases,
            retrieve=lambda _question: [
                chunk("irrelevant", rank=1),
                chunk("answer", rank=2),
            ],
            k=1,
        )

        self.assertEqual(report.hit_rate_at_k, 0.0)
        self.assertEqual(report.mean_reciprocal_rank, 0.0)

    def test_silver_ndcg_never_exceeds_one_for_repeated_phrase(self):
        cases = [RetrievalCase("case-1", "question", ("answer",))]

        report = evaluate_retrieval(
            cases,
            retrieve=lambda _question: [
                chunk("answer", rank=1),
                chunk("answer repeated", rank=2),
                chunk("another answer", rank=3),
            ],
            k=3,
        )

        self.assertEqual(report.mean_ndcg_at_k, 1.0)
        self.assertLessEqual(report.mean_ndcg_at_k, 1.0)

    def test_load_cases_rejects_duplicate_ids(self):
        payload = [
            {"id": "same", "question": "one", "expected_phrases": ["a"]},
            {"id": "same", "question": "two", "expected_phrases": ["b"]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate benchmark id"):
                load_cases(path)

    def test_gold_qrels_calculate_precision_recall_and_ndcg(self):
        first_id = uuid4()
        second_id = uuid4()
        cases = [
            RetrievalCase(
                id="gold-1",
                question="question",
                relevant_chunk_ids=(first_id, second_id),
            )
        ]

        report = evaluate_retrieval(
            cases,
            retrieve=lambda _question: [
                chunk("irrelevant", rank=1),
                chunk("relevant", rank=2, chunk_id=first_id),
            ],
            k=2,
        )

        self.assertEqual(report.gold_case_count, 1)
        self.assertEqual(report.mean_precision_at_k, 0.5)
        self.assertEqual(report.mean_recall_at_k, 0.5)
        self.assertEqual(report.mean_reciprocal_rank, 0.5)
        self.assertEqual(report.gold_metrics.case_count, 1)
        self.assertIsNone(report.silver_metrics)


if __name__ == "__main__":
    unittest.main()
