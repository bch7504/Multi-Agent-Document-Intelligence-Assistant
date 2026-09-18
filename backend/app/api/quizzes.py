"""Saved quiz library and attempt endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.schemas.quizzes import (
    QuizAttemptCreate,
    QuizAttemptList,
    QuizAttemptRead,
    QuizList,
    QuizRead,
)
from backend.app.services.quizzes import (
    InvalidQuizAttemptError,
    QuizNotFoundError,
    QuizService,
)


router = APIRouter(prefix="/quizzes", tags=["quizzes"])


def get_quiz_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> QuizService:
    return QuizService(session)


@router.get("", response_model=QuizList)
def list_quizzes(
    service: Annotated[QuizService, Depends(get_quiz_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuizList:
    items, total = service.list(limit, offset)
    return QuizList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{quiz_id}", response_model=QuizRead)
def get_quiz(
    quiz_id: UUID,
    service: Annotated[QuizService, Depends(get_quiz_service)],
) -> QuizRead:
    try:
        return service.get(quiz_id)
    except QuizNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/{quiz_id}/attempts", response_model=QuizAttemptRead, status_code=status.HTTP_201_CREATED)
def create_quiz_attempt(
    quiz_id: UUID,
    payload: QuizAttemptCreate,
    service: Annotated[QuizService, Depends(get_quiz_service)],
) -> QuizAttemptRead:
    try:
        return service.create_attempt(quiz_id, payload.answers)
    except QuizNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidQuizAttemptError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.get("/{quiz_id}/attempts", response_model=QuizAttemptList)
def list_quiz_attempts(
    quiz_id: UUID,
    service: Annotated[QuizService, Depends(get_quiz_service)],
) -> QuizAttemptList:
    try:
        items = service.attempts(quiz_id)
    except QuizNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return QuizAttemptList(items=items, total=len(items))


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: UUID,
    service: Annotated[QuizService, Depends(get_quiz_service)],
) -> Response:
    try:
        service.delete(quiz_id)
    except QuizNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
