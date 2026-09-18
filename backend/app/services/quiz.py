"""Quiz draft contracts and deterministic conversion to the public schema."""

import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.app.rag.schemas import RetrievedChunk
from backend.app.schemas.assistant import QuizOption, QuizQuestion, QuizResult
from backend.app.services.citations import citations_from_chunks, validate_citations
from backend.app.services.summary import select_cited_chunks


DEFAULT_QUIZ_QUESTION_COUNT = 5
MAX_QUIZ_QUESTION_COUNT = 20

_QUESTION_COUNT_PATTERN = re.compile(
    r"(?<!\d)(\d{1,3})[\s-]*(?:câu(?:\s+hỏi)?|questions?)\b",
    re.IGNORECASE,
)
_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "một": 1,
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "bon": 4,
    "năm": 5,
    "nam": 5,
    "sáu": 6,
    "sau": 6,
    "bảy": 7,
    "bay": 7,
    "tám": 8,
    "tam": 8,
    "chín": 9,
    "chin": 9,
    "mười": 10,
    "muoi": 10,
}
_WORD_COUNT_PATTERN = re.compile(
    rf"(?<!\w)({'|'.join(sorted(map(re.escape, _COUNT_WORDS), key=len, reverse=True))})"
    r"[\s-]+(?:câu(?:\s+hỏi)?|questions?)\b",
    re.IGNORECASE,
)


def resolve_quiz_question_count(request: str) -> int:
    """Extract an explicit requested count, otherwise use the product default."""

    numeric = _QUESTION_COUNT_PATTERN.search(request)
    if numeric:
        return min(max(int(numeric.group(1)), 1), MAX_QUIZ_QUESTION_COUNT)
    word = _WORD_COUNT_PATTERN.search(request)
    if word:
        return _COUNT_WORDS[word.group(1).casefold()]
    return DEFAULT_QUIZ_QUESTION_COUNT


class QuizQuestionDraft(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_option_index: int = Field(ge=0, le=5)
    explanation: str = Field(min_length=1, max_length=2_000)
    cited_chunk_ids: list[UUID] = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def options_must_be_unique(cls, options: list[str]) -> list[str]:
        cleaned = [option.strip() for option in options]
        if any(not option for option in cleaned):
            raise ValueError("quiz options must not be blank")
        if len({option.casefold() for option in cleaned}) != len(cleaned):
            raise ValueError("quiz options must be unique")
        return cleaned


class QuizDraft(BaseModel):
    questions: list[QuizQuestionDraft] = Field(min_length=1, max_length=20)


def build_quiz_result(
    draft: QuizDraft,
    chunks: list[RetrievedChunk],
    allowed_document_ids: list[UUID],
) -> QuizResult:
    questions: list[QuizQuestion] = []
    for question_index, item in enumerate(draft.questions, start=1):
        if item.correct_option_index >= len(item.options):
            raise ValueError("correct_option_index is outside the options list")
        cited_chunks = select_cited_chunks(chunks, item.cited_chunk_ids)
        citations = citations_from_chunks(cited_chunks)
        validate_citations(citations, chunks, allowed_document_ids)
        options = [
            QuizOption(id=chr(65 + option_index), text=text)
            for option_index, text in enumerate(item.options)
        ]
        questions.append(
            QuizQuestion(
                id=f"q{question_index}",
                question=item.question.strip(),
                options=options,
                correct_option_id=options[item.correct_option_index].id,
                explanation=item.explanation.strip(),
                citations=citations,
            )
        )
    return QuizResult(questions=questions)
