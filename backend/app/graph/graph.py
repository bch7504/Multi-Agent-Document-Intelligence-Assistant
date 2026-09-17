"""Compile and invoke the bounded multi-agent assistant LangGraph."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from backend.app.graph.nodes import AssistantGraphNodes
from backend.app.graph.routes import (
    route_after_review,
    route_after_validation,
    route_entry,
    route_resolved_task,
    route_retry_target,
)
from backend.app.graph.state import AssistantGraphState
from backend.app.core.observability import TokenUsageCallbackHandler
from backend.app.schemas.assistant import (
    AssistantRunRequest,
    AssistantRunResponse,
    UsageStats,
)


CHECKPOINT_ALLOWED_TYPES = [
    ("backend.app.rag.schemas", "RetrievedChunk"),
    ("backend.app.schemas.assistant", "AssistantRunRequest"),
    ("backend.app.schemas.assistant", "AssistantRunResponse"),
    ("backend.app.schemas.assistant", "AssistantTask"),
    ("backend.app.schemas.assistant", "Citation"),
    ("backend.app.schemas.assistant", "QuizOption"),
    ("backend.app.schemas.assistant", "QuizQuestion"),
    ("backend.app.schemas.assistant", "QuizResult"),
    ("backend.app.schemas.assistant", "ResolvedAssistantTask"),
    ("backend.app.schemas.assistant", "ReviewResult"),
    ("backend.app.schemas.assistant", "ReviewStatus"),
    ("backend.app.schemas.assistant", "TraceStatus"),
    ("backend.app.schemas.assistant", "TraceStep"),
    ("backend.app.schemas.assistant", "UsageStats"),
    ("backend.app.schemas.models", "ModelProvider"),
    ("backend.app.services.summary", "SummaryMapDraft"),
    ("backend.app.services.quiz", "QuizDraft"),
    ("backend.app.services.quiz", "QuizQuestionDraft"),
]


def create_checkpointer() -> InMemorySaver:
    return InMemorySaver(
        serde=JsonPlusSerializer(
            allowed_msgpack_modules=CHECKPOINT_ALLOWED_TYPES,
        )
    )


def build_assistant_graph(
    retriever: Any,
    llm: Any,
    checkpointer: Any | None = None,
):
    nodes = AssistantGraphNodes(retriever, llm)
    builder = StateGraph(AssistantGraphState)
    builder.add_node("resolve_task", nodes.resolve_task)
    builder.add_node("rewrite_query", nodes.rewrite_qa_query)
    builder.add_node("retrieve_qa", nodes.retrieve_qa)
    builder.add_node("answer_qa", nodes.answer_qa)
    builder.add_node("resolve_summary_scope", nodes.resolve_summary_scope)
    builder.add_node("retrieve_summary", nodes.retrieve_summary)
    builder.add_node("map_summary", nodes.map_summary)
    builder.add_node("reduce_summary", nodes.reduce_summary)
    builder.add_node("resolve_quiz_scope", nodes.resolve_quiz_scope)
    builder.add_node("retrieve_quiz", nodes.retrieve_quiz)
    builder.add_node("generate_quiz", nodes.generate_quiz)
    builder.add_node("validate_output", nodes.validate_output)
    builder.add_node("review_output", nodes.review_output)
    builder.add_node("prepare_retry", nodes.prepare_retry)
    builder.add_node("finalize", nodes.finalize)

    builder.add_conditional_edges(
        START,
        route_entry,
        {
            "resolve_task": "resolve_task",
            "qa": "rewrite_query",
            "summary": "resolve_summary_scope",
            "quiz": "resolve_quiz_scope",
        },
    )
    builder.add_conditional_edges(
        "resolve_task",
        route_resolved_task,
        {
            "qa": "rewrite_query",
            "summary": "resolve_summary_scope",
            "quiz": "resolve_quiz_scope",
        },
    )
    builder.add_edge("rewrite_query", "retrieve_qa")
    builder.add_edge("retrieve_qa", "answer_qa")
    builder.add_edge("answer_qa", "validate_output")
    builder.add_edge("resolve_summary_scope", "retrieve_summary")
    builder.add_edge("retrieve_summary", "map_summary")
    builder.add_edge("map_summary", "reduce_summary")
    builder.add_edge("reduce_summary", "validate_output")
    builder.add_edge("resolve_quiz_scope", "retrieve_quiz")
    builder.add_edge("retrieve_quiz", "generate_quiz")
    builder.add_edge("generate_quiz", "validate_output")
    builder.add_conditional_edges(
        "validate_output",
        route_after_validation,
        {
            "review": "review_output",
            "retry": "prepare_retry",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "review_output",
        route_after_review,
        {"retry": "prepare_retry", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "prepare_retry",
        route_retry_target,
        {
            "retrieve_qa": "retrieve_qa",
            "answer_qa": "answer_qa",
            "retrieve_summary": "retrieve_summary",
            "reduce_summary": "reduce_summary",
            "retrieve_quiz": "retrieve_quiz",
            "generate_quiz": "generate_quiz",
        },
    )
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer or create_checkpointer())


@dataclass
class AssistantGraphRuntime:
    graph: Any

    def invoke(
        self,
        request: AssistantRunRequest,
        history: list[dict[str, str]] | None = None,
    ) -> AssistantRunResponse:
        graph_input: dict[str, Any] = {
            "request": request,
            "started_at": perf_counter(),
            "trace": [],
            "retry_count": 0,
        }
        if history is not None:
            graph_input["history"] = history
        usage_callback = TokenUsageCallbackHandler()
        result = self.graph.invoke(
            graph_input,
            config={
                "configurable": {"thread_id": str(request.conversation_id)},
                "recursion_limit": 40,
                "callbacks": [usage_callback],
            },
        )
        response = AssistantRunResponse.model_validate(result["response"])
        return response.model_copy(
            update={
                "usage": UsageStats(
                    input_tokens=usage_callback.input_tokens,
                    output_tokens=usage_callback.output_tokens,
                    total_tokens=usage_callback.total_tokens,
                )
            }
        )


def create_assistant_runtime(retriever: Any, llm: Any) -> AssistantGraphRuntime:
    return AssistantGraphRuntime(build_assistant_graph(retriever, llm))
