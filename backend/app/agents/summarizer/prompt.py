"""Prompts for map-reduce document summarization."""

SUMMARY_MAP_SYSTEM_PROMPT = """You summarize document evidence faithfully.
Use only the supplied evidence. Preserve important facts, qualifications, and
relationships. Return the chunk IDs that directly support the partial summary.
Never invent a chunk ID.
"""

SUMMARY_REDUCE_SYSTEM_PROMPT = """You combine partial document summaries into
one grounded answer. Follow the user's requested focus, remove repetition, and
use only the supplied partial summaries. Return the supporting chunk IDs shown
in those summaries. Never invent a chunk ID.
"""


def build_summary_map_prompt(focus: str, evidence: str) -> str:
    return (
        f"Summary focus:\n{focus.strip()}\n\n"
        f"Evidence batch:\n{evidence}\n\n"
        "Cover every major point in this batch, remove repetition, and produce "
        "a concise partial summary with only its directly supporting chunk IDs."
    )


def build_summary_reduce_prompt(
    focus: str,
    partial_summaries: str,
    feedback: str | None = None,
) -> str:
    retry = f"\nReviewer feedback to fix:\n{feedback}\n" if feedback else ""
    return (
        f"Summary focus:\n{focus.strip()}\n\n"
        f"Partial summaries:\n{partial_summaries}\n\n"
        f"{retry}\n"
        "Produce a concise, well-structured final summary that covers the major "
        "points across all partial summaries and return supporting chunk IDs."
    )
