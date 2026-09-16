"""Run the retrieval benchmark against an indexed Milvus collection."""

import argparse
import json
from pathlib import Path

from backend.app.evaluation.retrieval import evaluate_retrieval, load_cases
from backend.app.rag.hybrid_search import RetrievalProfile, get_retriever
from backend.app.services.retrieval import retrieve_chunks


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "stack_ai_retrieval_v2.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--collection", default="data_test")
    parser.add_argument("--milvus-uri", default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--profile",
        choices=tuple(profile.value for profile in RetrievalProfile),
        default=RetrievalProfile.HYBRID_RRF.value,
    )
    parser.add_argument(
        "--compare-all",
        action="store_true",
        help="Run dense-only, BM25-only, and hybrid RRF on the same dataset",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Omit per-case results from JSON output",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=("openrouter", "openai", "gemini", "ollama"),
        default=None,
        help="Override EMBEDDING_PROVIDER for this benchmark run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.dataset)
    profiles = list(RetrievalProfile) if args.compare_all else [RetrievalProfile(args.profile)]
    reports = {}
    for profile in profiles:
        retriever = get_retriever(
            collection_name=args.collection,
            embedding_provider=args.embedding_provider,
            milvus_uri=args.milvus_uri,
            profile=profile,
        )
        report = evaluate_retrieval(
            cases,
            retrieve=lambda question, current=retriever: retrieve_chunks(current, question),
            retrieve_scoped=lambda question, document_ids, current=retriever: retrieve_chunks(
                current,
                question,
                document_ids=document_ids,
            ),
            k=args.k,
        )
        report_payload = report.to_dict()
        if args.summary_only:
            report_payload["zero_hit_case_ids"] = [
                case.id for case in report.cases if case.hit_at_k == 0
            ]
            report_payload.pop("cases", None)
        reports[profile.value] = report_payload
    payload = {
        "collection": args.collection,
        "dataset": str(args.dataset),
        "profiles": reports,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
