"""Retrieval specialist built on the current tool-calling RAG workflow."""

from typing import Any, Iterable

from langchain.agents import create_agent
from langchain_core.tools import create_retriever_tool

from backend.app.agents.retrieval.prompt import SYSTEM_PROMPT
from backend.app.core.llm import create_llm
from backend.app.schemas.assistant import AssistantRunRequest, AssistantRunResponse
from backend.app.services.qa import answer_question


def run_grounded_qa(
    request: AssistantRunRequest,
    retriever: Any,
    llm_choice: str | None = None,
    openrouter_model: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AssistantRunResponse:
    """Run the citation-safe QA baseline with the configured provider."""
    llm = create_llm(llm_choice, openrouter_model=openrouter_model)
    kwargs = {"request": request, "retriever": retriever, "llm": llm}
    if history is not None:
        kwargs["history"] = history
    return answer_question(**kwargs)

def get_llm_and_agent(
    retriever: Any,
    llm_choice: str | None = None,
    openrouter_model: str | None = None,
) -> Any:
    """Create a LangChain 1.x agent with a retrieval tool."""
    tool = create_retriever_tool(
        retriever,
        "find_stack_ai_information",
        "Search the indexed Stack AI documentation for facts relevant to the question.",
    )
    return create_agent(
        model=create_llm(llm_choice, openrouter_model=openrouter_model),
        tools=[tool],
        system_prompt=SYSTEM_PROMPT,
    )


def _message_content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return str(content)


def invoke_agent(agent_executor: Any, messages: Iterable[dict[str, str]]) -> str:
    """Invoke a LangChain 1.x agent and return the final assistant text."""
    normalized_messages = []
    for message in messages:
        role = "user" if message.get("role") == "human" else message.get("role")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")
        normalized_messages.append({"role": role, "content": message.get("content", "")})

    response = agent_executor.invoke({"messages": normalized_messages})
    response_messages = response.get("messages")
    if not response_messages:
        raise RuntimeError("The agent returned no messages")

    output = _message_content_as_text(response_messages[-1].content)
    if not output:
        raise RuntimeError("The agent returned an empty response")
    return output
