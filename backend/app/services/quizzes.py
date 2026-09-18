"""Quiz library and scored attempt operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.models.quiz import QuizAttemptRecord, QuizRecord
from backend.app.schemas.assistant import QuizQuestion
from backend.app.schemas.quizzes import QuizAttemptRead, QuizRead, QuizSummary


class QuizNotFoundError(LookupError):
    pass


class InvalidQuizAttemptError(ValueError):
    pass


class QuizService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _get(self, quiz_id: UUID) -> QuizRecord:
        record = self.session.get(QuizRecord, quiz_id)
        if record is None:
            raise QuizNotFoundError(f"Quiz '{quiz_id}' was not found")
        return record

    @staticmethod
    def _questions(record: QuizRecord) -> list[QuizQuestion]:
        return [QuizQuestion.model_validate(item) for item in record.questions]

    def list(self, limit: int, offset: int) -> tuple[list[QuizSummary], int]:
        records = list(
            self.session.scalars(
                select(QuizRecord)
                .order_by(QuizRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        items: list[QuizSummary] = []
        for record in records:
            attempts = list(
                self.session.scalars(
                    select(QuizAttemptRecord).where(
                        QuizAttemptRecord.quiz_id == record.id
                    )
                )
            )
            scores = [
                attempt.correct_count / attempt.total_questions * 100
                for attempt in attempts
                if attempt.total_questions
            ]
            items.append(
                QuizSummary(
                    id=record.id,
                    run_id=record.run_id,
                    conversation_id=record.conversation_id,
                    title=record.title,
                    question_count=len(record.questions),
                    attempt_count=len(attempts),
                    best_score_percent=round(max(scores), 2) if scores else None,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            )
        total = self.session.scalar(select(func.count()).select_from(QuizRecord)) or 0
        return items, int(total)

    def get(self, quiz_id: UUID) -> QuizRead:
        record = self._get(quiz_id)
        return QuizRead(
            id=record.id,
            run_id=record.run_id,
            conversation_id=record.conversation_id,
            title=record.title,
            questions=self._questions(record),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def create_attempt(
        self,
        quiz_id: UUID,
        answers: dict[str, str],
    ) -> QuizAttemptRead:
        record = self._get(quiz_id)
        questions = self._questions(record)
        expected_ids = {question.id for question in questions}
        if set(answers) != expected_ids:
            raise InvalidQuizAttemptError(
                "An answer is required for every quiz question"
            )
        for question in questions:
            option_ids = {option.id for option in question.options}
            if answers[question.id] not in option_ids:
                raise InvalidQuizAttemptError(
                    f"Invalid option for question '{question.id}'"
                )
        correct = sum(
            answers[question.id] == question.correct_option_id
            for question in questions
        )
        attempt = QuizAttemptRecord(
            quiz_id=record.id,
            answers=answers,
            correct_count=correct,
            total_questions=len(questions),
        )
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return self._attempt_read(attempt)

    def attempts(self, quiz_id: UUID) -> list[QuizAttemptRead]:
        self._get(quiz_id)
        records = list(
            self.session.scalars(
                select(QuizAttemptRecord)
                .where(QuizAttemptRecord.quiz_id == quiz_id)
                .order_by(QuizAttemptRecord.created_at.desc())
            )
        )
        return [self._attempt_read(record) for record in records]

    @staticmethod
    def _attempt_read(record: QuizAttemptRecord) -> QuizAttemptRead:
        return QuizAttemptRead(
            id=record.id,
            quiz_id=record.quiz_id,
            answers=record.answers,
            correct_count=record.correct_count,
            total_questions=record.total_questions,
            score_percent=round(
                record.correct_count / record.total_questions * 100,
                2,
            ),
            created_at=record.created_at,
        )

    def delete(self, quiz_id: UUID) -> None:
        record = self._get(quiz_id)
        self.session.execute(
            delete(QuizAttemptRecord).where(QuizAttemptRecord.quiz_id == quiz_id)
        )
        self.session.delete(record)
        self.session.commit()
