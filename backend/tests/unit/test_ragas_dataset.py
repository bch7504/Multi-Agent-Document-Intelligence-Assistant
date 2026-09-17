import json
import tempfile
import unittest
from pathlib import Path

from backend.app.evaluation.run_ragas import (
    DEFAULT_DATASET,
    _metric_value,
    load_ragas_cases,
)


class RagasDatasetTests(unittest.TestCase):
    def test_versioned_dataset_is_valid(self):
        cases = load_ragas_cases(DEFAULT_DATASET)
        self.assertEqual(len(cases), 3)
        self.assertEqual(len({case.id for case in cases}), 3)
        self.assertTrue(all(case.reference for case in cases))

    def test_incomplete_case_is_rejected_without_running_ragas(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps([{"id": "missing-fields"}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                load_ragas_cases(path)

    def test_metric_value_normalizes_parameterized_ragas_column(self):
        self.assertEqual(
            _metric_value({"factual_correctness(mode=f1)": 0.75}, "factual_correctness"),
            0.75,
        )


if __name__ == "__main__":
    unittest.main()
