"""Conditional routes for explicit and automatically resolved tasks."""

from typing import Literal

from backend.app.graph.state import AssistantGraphState
from backend.app.schemas.assistant import AssistantTask, ResolvedAssistantTask


class UnsupportedAssistantTaskError(ValueError):
    """Raised when a task is not available in the current sprint."""


MAX_GRAPH_RETRIES = 2

EntryRoute = Literal["resolve_task", "qa", "summary", "quiz"]
ResolvedRoute = Literal["qa", "summary", "quiz"]


def route_entry(state: AssistantGraphState) -> EntryRoute:
    """Explicit tasks skip the LLM task resolver."""
    task = state["request"].task
    if task == AssistantTask.QA:
        return "qa"
    if task == AssistantTask.SUMMARY:
        return "summary"
    if task == AssistantTask.QUIZ:
        return "quiz"
    if task == AssistantTask.AUTO:
        return "resolve_task"
    raise UnsupportedAssistantTaskError(f"Unsupported task: {task}")


def route_resolved_task(state: AssistantGraphState) -> ResolvedRoute:
    task = state["resolved_task"]
    if task == ResolvedAssistantTask.QA:
        return "qa"
    if task == ResolvedAssistantTask.SUMMARY:
        return "summary"
    if task == ResolvedAssistantTask.QUIZ:
        return "quiz"
    raise UnsupportedAssistantTaskError(f"Unsupported resolved task: {task}")


def route_after_validation(state: AssistantGraphState) -> Literal["review", "retry", "finalize"]:
    if state.get("validation_passed", False):
        return "review"
    if state.get("retry_count", 0) < MAX_GRAPH_RETRIES:
        return "retry"
    return "finalize"


def route_after_review(state: AssistantGraphState) -> Literal["retry", "finalize"]:
    if state.get("review_status") == "pass":
        return "finalize"
    if state.get("retry_count", 0) < MAX_GRAPH_RETRIES:
        return "retry"
    return "finalize"


def route_retry_target(
    state: AssistantGraphState,
) -> Literal[
    "retrieve_qa",
    "answer_qa",
    "retrieve_summary",
    "reduce_summary",
    "retrieve_quiz",
    "generate_quiz",
]:
    task = state["resolved_task"]
    retrieval = state.get("retry_target", "generation") == "retrieval"
    if task == ResolvedAssistantTask.QA:
        return "retrieve_qa" if retrieval else "answer_qa"
    if task == ResolvedAssistantTask.SUMMARY:
        return "retrieve_summary" if retrieval else "reduce_summary"
    if task == ResolvedAssistantTask.QUIZ:
        return "retrieve_quiz" if retrieval else "generate_quiz"
    raise UnsupportedAssistantTaskError(f"Unsupported retry task: {task}")
