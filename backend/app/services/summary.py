"""Bounded map-reduce helpers for grounded document summaries."""

import os
from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.rag.schemas import RetrievedChunk
from backend.app.services.citations import CitationValidationError


DEFAULT_SUMMARY_CHUNKS = 12
DEFAULT_SUMMARY_CHARACTERS = 48_000
DEFAULT_MAP_BATCH_CHARACTERS = 10_000


class SummaryMapDraft(BaseModel):
    summary: str = Field(min_length=1)
    cited_chunk_ids: list[UUID] = Field(min_length=1)


class SummaryDraft(BaseModel):
    answer: str = Field(min_length=1)
    cited_chunk_ids: list[UUID] = Field(min_length=1)


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def select_summary_context(chunks: Iterable[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep a ranked, unique, bounded set of chunks for map-reduce."""
    max_chunks = _positive_int_env("SUMMARY_MAX_CHUNKS", DEFAULT_SUMMARY_CHUNKS)
    character_budget = _positive_int_env(
        "SUMMARY_MAX_CHARACTERS",
        DEFAULT_SUMMARY_CHARACTERS,
    )
    selected: list[RetrievedChunk] = []
    seen: set[UUID] = set()
    used_characters = 0
    for chunk in sorted(chunks, key=lambda item: item.rank):
        if chunk.chunk_id in seen:
            continue
        if selected and used_characters + len(chunk.content) > character_budget:
            continue
        selected.append(chunk)
        seen.add(chunk.chunk_id)
        used_characters += len(chunk.content)
        if len(selected) >= max_chunks:
            break
    return selected


def summary_batches(chunks: list[RetrievedChunk]) -> list[list[RetrievedChunk]]:
    """Group chunks into prompt-sized batches without splitting evidence."""
    budget = _positive_int_env(
        "SUMMARY_MAP_BATCH_CHARACTERS",
        DEFAULT_MAP_BATCH_CHARACTERS,
    )
    batches: list[list[RetrievedChunk]] = []
    current: list[RetrievedChunk] = []
    current_size = 0
    for chunk in chunks:
        if current and current_size + len(chunk.content) > budget:
            batches.append(current)
            current = []
            current_size = 0
        current.append(chunk)
        current_size += len(chunk.content)
    if current:
        batches.append(current)
    return batches


def format_summary_evidence(chunks: Iterable[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for chunk in chunks:
        page = str(chunk.page_number) if chunk.page_number is not None else "n/a"
        blocks.append(
            "\n".join(
                (
                    f'<evidence chunk_id="{chunk.chunk_id}" '
                    f'document_id="{chunk.document_id}" page="{page}">',
                    chunk.content,
                    "</evidence>",
                )
            )
        )
    return "\n\n".join(blocks)


def select_cited_chunks(
    chunks: Iterable[RetrievedChunk],
    cited_chunk_ids: Iterable[UUID],
) -> list[RetrievedChunk]:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    unique_ids = list(dict.fromkeys(cited_chunk_ids))
    unknown = [chunk_id for chunk_id in unique_ids if chunk_id not in by_id]
    if unknown:
        raise CitationValidationError(
            "Summary selected chunk IDs that were not retrieved: "
            + ", ".join(str(chunk_id) for chunk_id in unknown)
        )
    if not unique_ids:
        raise CitationValidationError("Summary must cite at least one retrieved chunk")
    return [by_id[chunk_id] for chunk_id in unique_ids]
