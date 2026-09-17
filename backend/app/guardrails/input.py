"""Deterministic input checks before document access or model calls."""

import re

from backend.app.schemas.assistant import AssistantRunRequest


class InputGuardrailError(ValueError):
    pass


_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|system)\s+instructions?\b", re.I),
    re.compile(r"\breveal\s+(the\s+)?(system|developer)\s+prompt\b", re.I),
    re.compile(r"\bact\s+as\s+the\s+system\b", re.I),
)


def validate_assistant_input(request: AssistantRunRequest) -> None:
    message = request.message
    if "\x00" in message:
        raise InputGuardrailError("Message contains unsupported control characters")
    if any(pattern.search(message) for pattern in _PROMPT_INJECTION_PATTERNS):
        raise InputGuardrailError(
            "Request attempts to override assistant instructions"
        )
