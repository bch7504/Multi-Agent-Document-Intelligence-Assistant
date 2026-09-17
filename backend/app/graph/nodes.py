"""Node implementations for QA, summary, quiz, review, and retry workflows."""

from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel
from langchain_core.runnables import RunnableConfig

from backend.app.agents.quiz.prompt import QUIZ_SYSTEM_PROMPT, build_quiz_prompt
from backend.app.agents.retrieval.qa_prompt import QA_SYSTEM_PROMPT, build_qa_prompt
from backend.app.agents.summarizer.prompt import (
    SUMMARY_MAP_SYSTEM_PROMPT,
    SUMMARY_REDUCE_SYSTEM_PROMPT,
    build_summary_map_prompt,
    build_summary_reduce_prompt,
)
from backend.app.agents.supervisor.prompt import (
    TASK_RESOLVER_SYSTEM_PROMPT,
    build_task_resolver_prompt,
)
from backend.app.graph.state import AssistantGraphState, merge_history
from backend.app.guardrails.output import review_grounding
from backend.app.schemas.assistant import (
    AssistantRunResponse,
    ResolvedAssistantTask,
    ReviewResult,
    ReviewStatus,
    TraceStatus,
    TraceStep,
)
from backend.app.services.citations import (
    CitationValidationError,
    citations_from_chunks,
    validate_citations,
)
from backend.app.services.qa import (
    GroundedAnswerDraft,
    InsufficientContextError,
    _format_evidence,
    _select_context,
)
from backend.app.services.query_rewrite import rewrite_query
from backend.app.services.quiz import QuizDraft, build_quiz_result
from backend.app.services.retrieval import retrieve_chunks
from backend.app.services.summary import (
    SummaryDraft,
    SummaryMapDraft,
    format_summary_evidence,
    select_cited_chunks,
    select_summary_context,
    summary_batches,
)


class TaskResolution(BaseModel):
    task: Literal["qa", "summary", "quiz"]


def _trace(
    state: AssistantGraphState,
    node_id: str,
    label: str,
    detail: str,
    started: float,
    status: TraceStatus = TraceStatus.COMPLETE,
) -> list[TraceStep]:
    return [
        *state.get("trace", []),
        TraceStep(
            id=node_id,
            label=label,
            detail=detail,
            duration_ms=round((perf_counter() - started) * 1_000),
            status=status,
        ),
    ]


class AssistantGraphNodes:
    def __init__(self, retriever: Any, llm: Any) -> None:
        self.retriever = retriever
        self.llm = llm

    def resolve_task(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        request = state["request"]
        raw = self.llm.with_structured_output(TaskResolution).invoke(
            [
                ("system", TASK_RESOLVER_SYSTEM_PROMPT),
                ("human", build_task_resolver_prompt(request.message)),
            ],
            config=config,
        )
        decision = TaskResolution.model_validate(raw)
        task = ResolvedAssistantTask(decision.task)
        return {
            "resolved_task": task,
            "trace": _trace(
                state,
                "resolve_task",
                "Task resolver",
                f"Resolved auto request to {task.value}",
                started,
            ),
        }

    def rewrite_qa_query(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        request = state["request"]
        history = state.get("history", [])
        query = request.message
        detail = "No prior conversation context; original query retained"
        if history:
            query = rewrite_query(request.message, history, self.llm, config=config)
            detail = f"Standalone retrieval query: {query}"
        return {
            "resolved_task": ResolvedAssistantTask.QA,
            "retrieval_query": query,
            "trace": _trace(state, "rewrite_query", "Query rewrite", detail, started),
        }

    def retrieve_qa(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        request = state["request"]
        chunks = _select_context(
            retrieve_chunks(
                self.retriever,
                state["retrieval_query"],
                document_ids=request.document_ids,
            )
        )
        if not chunks:
            raise InsufficientContextError(
                "No retrieved evidence belongs to the selected documents"
            )
        return {
            "chunks": chunks,
            "trace": _trace(
                state,
                "retrieve_qa",
                "Scoped retrieval",
                f"Selected {len(chunks)} QA chunks",
                started,
            ),
        }

    def answer_qa(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        request = state["request"]
        raw = self.llm.with_structured_output(GroundedAnswerDraft).invoke(
            [
                ("system", QA_SYSTEM_PROMPT),
                (
                    "human",
                    build_qa_prompt(
                        request.message,
                        _format_evidence(state["chunks"]),
                        state.get("review_feedback"),
                    ),
                ),
            ],
            config=config,
        )
        draft = GroundedAnswerDraft.model_validate(raw)
        return {
            "answer": draft.answer.strip(),
            "cited_chunk_ids": draft.cited_chunk_ids,
            "quiz": None,
            "trace": _trace(
                state,
                "answer_qa",
                "Grounded QA",
                "Generated structured answer with evidence IDs",
                started,
            ),
        }

    def resolve_summary_scope(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        message = state["request"].message
        query = (
            "main topics key facts conclusions document overview"
            if message.casefold() in {"summary", "summarize", "tóm tắt", "tom tat"}
            else message
        )
        return {
            "resolved_task": ResolvedAssistantTask.SUMMARY,
            "retrieval_query": query,
            "trace": _trace(
                state,
                "resolve_summary_scope",
                "Summary scope",
                f"Summary focus prepared for {len(state['request'].document_ids)} documents",
                started,
            ),
        }

    def retrieve_summary(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        request = state["request"]
        chunks = select_summary_context(
            retrieve_chunks(
                self.retriever,
                state["retrieval_query"],
                document_ids=request.document_ids,
            )
        )
        if not chunks:
            raise InsufficientContextError(
                "No retrieved evidence belongs to the selected documents"
            )
        return {
            "chunks": chunks,
            "trace": _trace(
                state,
                "retrieve_summary",
                "Summary retrieval",
                f"Selected {len(chunks)} chunks for map-reduce",
                started,
            ),
        }

    def map_summary(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        drafts: list[SummaryMapDraft] = []
        structured_llm = self.llm.with_structured_output(SummaryMapDraft)
        for batch in summary_batches(state["chunks"]):
            raw = structured_llm.invoke(
                [
                    ("system", SUMMARY_MAP_SYSTEM_PROMPT),
                    (
                        "human",
                        build_summary_map_prompt(
                            state["request"].message,
                            format_summary_evidence(batch),
                        ),
                    ),
                ],
                config=config,
            )
            drafts.append(SummaryMapDraft.model_validate(raw))
        return {
            "map_drafts": drafts,
            "trace": _trace(
                state,
                "map_summary",
                "Map summaries",
                f"Generated {len(drafts)} partial summaries",
                started,
            ),
        }

    def reduce_summary(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        blocks = []
        for index, draft in enumerate(state["map_drafts"], start=1):
            ids = ",".join(str(chunk_id) for chunk_id in draft.cited_chunk_ids)
            blocks.append(
                f'<partial_summary index="{index}" chunk_ids="{ids}">\n'
                f"{draft.summary}\n</partial_summary>"
            )
        raw = self.llm.with_structured_output(SummaryDraft).invoke(
            [
                ("system", SUMMARY_REDUCE_SYSTEM_PROMPT),
                (
                    "human",
                    build_summary_reduce_prompt(
                        state["request"].message,
                        "\n\n".join(blocks),
                        state.get("review_feedback"),
                    ),
                ),
            ],
            config=config,
        )
        draft = SummaryDraft.model_validate(raw)
        return {
            "answer": draft.answer.strip(),
            "cited_chunk_ids": draft.cited_chunk_ids,
            "quiz": None,
            "trace": _trace(
                state,
                "reduce_summary",
                "Reduce summary",
                "Combined partial summaries into a grounded result",
                started,
            ),
        }

    def resolve_quiz_scope(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        message = state["request"].message
        return {
            "resolved_task": ResolvedAssistantTask.QUIZ,
            "retrieval_query": f"quiz learning objectives key facts {message}",
            "trace": _trace(
                state,
                "resolve_quiz_scope",
                "Quiz scope",
                f"Quiz scope prepared for {len(state['request'].document_ids)} documents",
                started,
            ),
        }

    def retrieve_quiz(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        request = state["request"]
        chunks = select_summary_context(
            retrieve_chunks(
                self.retriever,
                state["retrieval_query"],
                document_ids=request.document_ids,
            )
        )
        if not chunks:
            raise InsufficientContextError(
                "No retrieved evidence belongs to the selected documents"
            )
        return {
            "chunks": chunks,
            "trace": _trace(
                state,
                "retrieve_quiz",
                "Quiz retrieval",
                f"Selected {len(chunks)} chunks for quiz generation",
                started,
            ),
        }

    def generate_quiz(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        raw = self.llm.with_structured_output(QuizDraft).invoke(
            [
                ("system", QUIZ_SYSTEM_PROMPT),
                (
                    "human",
                    build_quiz_prompt(
                        state["request"].message,
                        format_summary_evidence(state["chunks"]),
                        state.get("review_feedback"),
                    ),
                ),
            ],
            config=config,
        )
        draft = QuizDraft.model_validate(raw)
        return {
            "quiz_draft": draft,
            "answer": f"Generated {len(draft.questions)} grounded quiz question(s).",
            "cited_chunk_ids": [
                chunk_id
                for question in draft.questions
                for chunk_id in question.cited_chunk_ids
            ],
            "trace": _trace(
                state,
                "generate_quiz",
                "Quiz generation",
                f"Generated {len(draft.questions)} structured question(s)",
                started,
            ),
        }

    def validate_output(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        try:
            quiz = None
            if state["resolved_task"] == ResolvedAssistantTask.QUIZ:
                quiz = build_quiz_result(
                    state["quiz_draft"],
                    state["chunks"],
                    state["request"].document_ids,
                )
            cited_chunks = select_cited_chunks(
                state["chunks"],
                state["cited_chunk_ids"],
            )
            citations = citations_from_chunks(cited_chunks)
            validate_citations(
                citations,
                state["chunks"],
                state["request"].document_ids,
            )
        except (CitationValidationError, ValueError) as error:
            return {
                "citations": [],
                "quiz": None,
                "validation_passed": False,
                "review_status": "fail",
                "review_feedback": str(error),
                "retry_target": "generation",
                "trace": _trace(
                    state,
                    "validate_output",
                    "Deterministic validation",
                    f"FAIL · {error}",
                    started,
                    TraceStatus.FAILED,
                ),
            }
        return {
            "citations": citations,
            "quiz": quiz,
            "validation_passed": True,
            "trace": _trace(
                state,
                "validate_output",
                "Deterministic validation",
                f"PASS · {len(citations)} citations",
                started,
            ),
        }

    def review_output(
        self,
        state: AssistantGraphState,
        config: RunnableConfig | None = None,
    ) -> dict:
        started = perf_counter()
        decision = review_grounding(state, self.llm, config=config)
        status = TraceStatus.COMPLETE if decision.status == "pass" else TraceStatus.FAILED
        detail = decision.status.upper()
        if decision.feedback:
            detail = f"{detail} · {decision.feedback}"
        return {
            "review_status": decision.status,
            "review_feedback": decision.feedback,
            "retry_target": decision.retry_target,
            "trace": _trace(
                state,
                "review_output",
                "Grounding reviewer",
                detail,
                started,
                status,
            ),
        }

    def prepare_retry(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        retry_count = state.get("retry_count", 0) + 1
        return {
            "retry_count": retry_count,
            "trace": _trace(
                state,
                "prepare_retry",
                "Bounded retry",
                f"Retry {retry_count}/2 via {state.get('retry_target', 'generation')}",
                started,
            ),
        }

    def finalize(self, state: AssistantGraphState) -> dict:
        started = perf_counter()
        passed = (
            state.get("validation_passed", False)
            and state.get("review_status") == "pass"
        )
        answer = state.get("answer", "")
        citations = state.get("citations", [])
        quiz = state.get("quiz")
        if not passed:
            answer = "Unable to produce a fully grounded response after 2 retries."
            citations = []
            quiz = None

        current_trace = _trace(
            state,
            "finalize",
            "Finalize response",
            (
                f"Completed {state['resolved_task'].value} workflow"
                if passed
                else "Blocked output that did not pass grounding checks"
            ),
            started,
            TraceStatus.COMPLETE if passed else TraceStatus.FAILED,
        )
        current_trace.append(
            TraceStep(
                id="total",
                label="Total",
                detail="Assistant graph completed",
                duration_ms=round((perf_counter() - state["started_at"]) * 1_000),
                status=TraceStatus.COMPLETE if passed else TraceStatus.FAILED,
            )
        )
        retry_count = state.get("retry_count", 0)
        response = AssistantRunResponse(
            run_id=uuid4(),
            task=state["resolved_task"],
            answer=answer,
            citations=citations,
            quiz=quiz,
            review=ReviewResult(
                status=ReviewStatus.PASS if passed else ReviewStatus.FAIL,
                retry_count=retry_count,
                feedback=state.get("review_feedback"),
            ),
            trace=current_trace,
        )
        history = merge_history(
            state.get("history", []),
            [
                {"role": "user", "content": state["request"].message},
                {"role": "assistant", "content": answer},
            ],
        )
        return {"trace": current_trace, "response": response, "history": history}
