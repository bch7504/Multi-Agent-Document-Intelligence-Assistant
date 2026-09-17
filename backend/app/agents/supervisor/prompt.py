"""Prompt for resolving an automatic assistant task."""

TASK_RESOLVER_SYSTEM_PROMPT = """You route document-assistant requests.
Choose exactly one supported task:
- qa: answer a question or explain facts from selected documents
- summary: summarize, outline, or extract the main ideas from selected documents
- quiz: create questions, exercises, or a knowledge check from selected documents

Do not answer the request. Return only the structured task decision.
"""


def build_task_resolver_prompt(message: str) -> str:
    return f"Classify this request as qa, summary, or quiz:\n\n{message.strip()}"
