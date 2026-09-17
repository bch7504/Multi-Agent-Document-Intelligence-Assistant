"""Conversation-aware standalone retrieval query rewriting."""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig


MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARACTERS = 6_000


class RewrittenQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)


QUERY_REWRITE_SYSTEM_PROMPT = """Rewrite the latest user question into one standalone search query.
Resolve pronouns and references using only the supplied conversation. Preserve the user's language.
Do not answer the question, add facts, or include commentary. Return the original question when it is
already standalone."""


def _bounded_history(messages: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})

    selected: list[dict[str, str]] = []
    used = 0
    for message in reversed(normalized[-MAX_HISTORY_TURNS:]):
        remaining = MAX_HISTORY_CHARACTERS - used
        if remaining <= 0:
            break
        content = message["content"][-remaining:]
        selected.append({"role": message["role"], "content": content})
        used += len(content)
    return list(reversed(selected))


def rewrite_query(
    question: str,
    history: Iterable[dict[str, str]],
    llm: Any,
    config: RunnableConfig | None = None,
) -> str:
    question = question.strip()
    if not question:
        raise ValueError("Question must not be blank")
    bounded = _bounded_history(history)
    if not bounded:
        return question

    transcript = "\n".join(
        f"{message['role'].upper()}: {message['content']}" for message in bounded
    )
    structured_llm = llm.with_structured_output(RewrittenQuery)
    raw = structured_llm.invoke(
        [
            ("system", QUERY_REWRITE_SYSTEM_PROMPT),
            (
                "human",
                f"<conversation>\n{transcript}\n</conversation>\n"
                f"<latest_question>{question}</latest_question>",
            ),
        ],
        config=config,
    )
    return RewrittenQuery.model_validate(raw).query.strip()
