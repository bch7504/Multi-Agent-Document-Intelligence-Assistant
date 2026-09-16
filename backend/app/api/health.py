"""Liveness and external-dependency readiness endpoints."""

from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pymilvus import MilvusClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.database.postgres import get_db_session
from backend.app.schemas.health import HealthResponse, ReadinessResponse


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


def get_milvus_client() -> Generator[MilvusClient, None, None]:
    try:
        client = MilvusClient(uri=get_settings().milvus_uri)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "dependencies": {"milvus": "unavailable"},
            },
        ) from error
    try:
        yield client
    finally:
        client.close()


@router.get("/ready", response_model=ReadinessResponse)
def readiness(
    session: Annotated[Session, Depends(get_db_session)],
    milvus: Annotated[MilvusClient, Depends(get_milvus_client)],
) -> ReadinessResponse:
    checks: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as error:
        checks["postgres"] = "unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": checks},
        ) from error

    try:
        milvus.list_collections()
        checks["milvus"] = "ok"
    except Exception as error:
        checks["milvus"] = "unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": checks},
        ) from error

    return ReadinessResponse(status="ready", dependencies=checks)
