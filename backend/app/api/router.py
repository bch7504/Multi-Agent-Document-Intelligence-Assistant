"""Top-level API v1 router."""

from fastapi import APIRouter

from backend.app.api.assistant import router as assistant_router
from backend.app.api.documents import router as documents_router
from backend.app.api.health import router as health_router
from backend.app.api.models import router as models_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(models_router)
api_router.include_router(documents_router)
api_router.include_router(assistant_router)
