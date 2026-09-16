"""Health endpoint contracts."""

from typing import Literal

from backend.app.schemas.base import ApiModel


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str


class ReadinessResponse(ApiModel):
    status: str
    dependencies: dict[str, str]
