"""Run a versioned end-to-end RAGAS evaluation over grounded QA."""

import argparse
import hashlib
import json
import os
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from uuid import UUID, uuid4

from backend.app.core.config import get_settings
from backend.app.core.llm import create_llm
from backend.app.rag.hybrid_search import get_retriever
from backend.app.schemas.assistant import AssistantRunRequest
from backend.app.services.indexing import _get_embeddings
from backend.app.services.qa import _select_context, answer_question
from backend.app.services.retrieval import retrieve_chunks


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "stack_ai_ragas_v1.json"
DEFAULT_OUTPUT = Path("docs/reports/evaluation/ragas_stack_ai_v1.json")
METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "factual_correctness",
    "llm_context_precision_without_reference",
)


def _metric_value(row: dict, metric: str) -> float | None:
    value = row.get(metric)
    if value is None:
        value = next(
            (item for key, item in row.items() if key.startswith(f"{metric}(")),
            None,
        )
    return float(value) if value is not None else None


@dataclass(frozen=True)
class RagasCase:
    id: str
    question: str
    reference: str
    document_ids: tuple[UUID, ...]


def load_ragas_cases(path: Path) -> list[RagasCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("RAGAS dataset must be a non-empty JSON list")
    cases: list[RagasCase] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        case_id = str(item.get("id", "")).strip()
        question = str(item.get("question", "")).strip()
        reference = str(item.get("reference", "")).strip()
        document_ids = tuple(UUID(str(value)) for value in item.get("document_ids", []))
        if not case_id or not question or not reference or not document_ids:
            raise ValueError(f"RAGAS case at index {index} is incomplete")
        if case_id in seen:
            raise ValueError(f"Duplicate RAGAS case id: {case_id}")
        seen.add(case_id)
        cases.append(RagasCase(case_id, question, reference, document_ids))
    return cases


def _install_ragas_vertex_compatibility() -> None:
    """Bridge a removed optional LangChain module imported eagerly by RAGAS 0.4."""
    module_name = "langchain_community.chat_models.vertexai"
    try:
        __import__(module_name)
        return
    except ModuleNotFoundError:
        pass
    from langchain_core.language_models import BaseChatModel

    module = types.ModuleType(module_name)
    module.ChatVertexAI = type(
        "ChatVertexAI",
        (BaseChatModel,),
        {
            "_generate": lambda *args, **kwargs: None,
            "_llm_type": property(lambda self: "ragas-compatibility-placeholder"),
        },
    )
    sys.modules[module_name] = module


def _ragas_imports():
    _install_ragas_vertex_compatibility()
    import ragas
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics._answer_relevance import ResponseRelevancy
    from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
    from ragas.metrics._factual_correctness import FactualCorrectness
    from ragas.metrics._faithfulness import Faithfulness

    return {
        "ragas": ragas,
        "EvaluationDataset": EvaluationDataset,
        "SingleTurnSample": SingleTurnSample,
        "evaluate": evaluate,
        "LangchainEmbeddingsWrapper": LangchainEmbeddingsWrapper,
        "LangchainLLMWrapper": LangchainLLMWrapper,
        "metric_types": (
            Faithfulness,
            ResponseRelevancy,
            FactualCorrectness,
            LLMContextPrecisionWithoutReference,
        ),
    }


def run_evaluation(
    dataset_path: Path,
    output_path: Path,
    collection_name: str,
    max_cases: int | None,
) -> dict:
    imports = _ragas_imports()
    cases = load_ragas_cases(dataset_path)
    if max_cases is not None:
        if max_cases < 1:
            raise ValueError("--max-cases must be positive")
        cases = cases[:max_cases]

    settings = get_settings()
    retriever = get_retriever(
        collection_name=collection_name,
        milvus_uri=settings.milvus_uri,
    )
    llm = create_llm(streaming=False)
    samples = []
    case_metadata = []
    for case in cases:
        chunks = _select_context(
            retrieve_chunks(retriever, case.question, document_ids=case.document_ids)
        )
        response = answer_question(
            AssistantRunRequest(
                conversation_id=uuid4(),
                document_ids=list(case.document_ids),
                task="qa",
                message=case.question,
            ),
            retriever,
            llm,
        )
        samples.append(
            imports["SingleTurnSample"](
                user_input=case.question,
                retrieved_contexts=[chunk.content for chunk in chunks],
                response=response.answer,
                reference=case.reference,
            )
        )
        case_metadata.append({"id": case.id, "run_id": str(response.run_id)})

    ragas_llm = imports["LangchainLLMWrapper"](llm)
    ragas_embeddings = imports["LangchainEmbeddingsWrapper"](_get_embeddings())
    metric_types = imports["metric_types"]
    metrics = [
        metric_types[0](llm=ragas_llm),
        metric_types[1](llm=ragas_llm, embeddings=ragas_embeddings),
        metric_types[2](llm=ragas_llm),
        metric_types[3](llm=ragas_llm),
    ]
    result = imports["evaluate"](
        dataset=imports["EvaluationDataset"](samples=samples),
        metrics=metrics,
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        experiment_name="document_assistant_ragas_v1",
        raise_exceptions=False,
        show_progress=True,
    )
    rows = json.loads(result.to_pandas().to_json(orient="records"))
    aggregate = {}
    for metric in METRIC_NAMES:
        values = [value for row in rows if (value := _metric_value(row, metric)) is not None]
        if values:
            aggregate[metric] = round(mean(values), 4)
    case_results = []
    for metadata, row in zip(case_metadata, rows):
        case_results.append(
            {
                **metadata,
                "user_input": row.get("user_input"),
                "response": row.get("response"),
                "reference": row.get("reference"),
                "retrieved_context_count": len(row.get("retrieved_contexts") or []),
                "scores": {
                    metric: value
                    for metric in METRIC_NAMES
                    if (value := _metric_value(row, metric)) is not None
                },
            }
        )
    dataset_bytes = dataset_path.read_bytes()
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ragas_version": imports["ragas"].__version__,
        "dataset": str(dataset_path),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "collection": collection_name,
        "case_count": len(cases),
        "configuration": {
            "llm_provider": os.getenv("LLM_PROVIDER", ""),
            "embedding_provider": os.getenv("EMBEDDING_PROVIDER", ""),
            "metrics": list(METRIC_NAMES),
        },
        "aggregate": aggregate,
        "cases": case_results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--collection", default="data_test")
    parser.add_argument("--max-cases", type=int)
    args = parser.parse_args()
    report = run_evaluation(
        args.dataset,
        args.output,
        args.collection,
        args.max_cases,
    )
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
