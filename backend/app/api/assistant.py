"""Unified assistant execution and run-audit API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.graph.routes import UnsupportedAssistantTaskError
from backend.app.guardrails.input import InputGuardrailError
from backend.app.schemas.assistant import (
    AssistantRunAudit,
    AssistantRunRequest,
    AssistantRunResponse,
)
from backend.app.services.assistant import (
    AssistantDocumentNotFoundError,
    AssistantDocumentNotReadyError,
    AssistantEmbeddingMismatchError,
    AssistantRunNotFoundError,
    AssistantService,
)
from backend.app.services.citations import CitationValidationError
from backend.app.services.qa import InsufficientContextError


router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_assistant_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> AssistantService:
    return AssistantService(session)


@router.post("/runs", response_model=AssistantRunResponse)
def run_assistant(
    request: AssistantRunRequest,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantRunResponse:
    try:
        return service.run(request)
    except AssistantDocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except AssistantDocumentNotReadyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except AssistantEmbeddingMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except InputGuardrailError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except UnsupportedAssistantTaskError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except (InsufficientContextError, CitationValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.get("/runs/{run_id}", response_model=AssistantRunAudit)
def get_assistant_run(
    run_id: UUID,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantRunAudit:
    try:
        return service.get_run(run_id)
    except AssistantRunNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
