"""Safe model-catalog contracts exposed to the frontend."""

from enum import Enum

from pydantic import Field

from backend.app.schemas.base import ApiModel


class ModelProvider(str, Enum):
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class ModelChoice(ApiModel):
    provider: ModelProvider
    model: str = Field(min_length=1, max_length=255)


class ProviderCatalog(ApiModel):
    provider: ModelProvider
    label: str
    runtime: str
    configured: bool
    chat_models: list[str]
    embedding_models: list[str]


class ModelCatalog(ApiModel):
    active_chat: ModelChoice
    active_embedding: ModelChoice
    providers: list[ProviderCatalog]
    embedding_change_requires_reindex: bool = True
