"""Model catalog without exposing API keys to the browser."""

import os

from fastapi import APIRouter

from backend.app.core.llm import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENROUTER_MODEL,
)
from backend.app.services.indexing import (
    DEFAULT_GEMINI_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    DEFAULT_OPENROUTER_EMBEDDING_MODEL,
)
from backend.app.schemas.models import (
    ModelCatalog,
    ModelChoice,
    ModelProvider,
    ProviderCatalog,
)


router = APIRouter(prefix="/models", tags=["models"])


def _value(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def _unique(*values: str) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


@router.get("", response_model=ModelCatalog)
def get_model_catalog() -> ModelCatalog:
    chat_provider = ModelProvider(
        _value("LLM_PROVIDER", ModelProvider.OPENROUTER.value).lower()
    )
    embedding_provider = ModelProvider(
        _value("EMBEDDING_PROVIDER", ModelProvider.OPENROUTER.value).lower()
    )
    chat_models = {
        ModelProvider.OPENROUTER: _value("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
        ModelProvider.OPENAI: _value("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        ModelProvider.GEMINI: _value("GEMINI_MODEL", "gemini-2.5-flash"),
        ModelProvider.OLLAMA: _value("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_CHAT_MODEL),
    }
    embedding_models = {
        ModelProvider.OPENROUTER: _value(
            "OPENROUTER_EMBEDDING_MODEL", DEFAULT_OPENROUTER_EMBEDDING_MODEL
        ),
        ModelProvider.OPENAI: _value(
            "OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL
        ),
        ModelProvider.GEMINI: _value(
            "GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL
        ),
        ModelProvider.OLLAMA: _value(
            "OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL
        ),
    }
    providers = [
        ProviderCatalog(
            provider=ModelProvider.OPENROUTER,
            label="OpenRouter",
            runtime="cloud",
            configured=bool(os.getenv("OPENROUTER_API_KEY", "").strip()),
            chat_models=_unique(chat_models[ModelProvider.OPENROUTER]),
            embedding_models=_unique(
                embedding_models[ModelProvider.OPENROUTER],
                "openai/text-embedding-3-small",
                "openai/text-embedding-3-large",
            ),
        ),
        ProviderCatalog(
            provider=ModelProvider.OPENAI,
            label="OpenAI",
            runtime="cloud",
            configured=bool(os.getenv("OPENAI_API_KEY", "").strip()),
            chat_models=_unique(chat_models[ModelProvider.OPENAI]),
            embedding_models=_unique(
                embedding_models[ModelProvider.OPENAI],
                "text-embedding-3-small",
                "text-embedding-3-large",
            ),
        ),
        ProviderCatalog(
            provider=ModelProvider.GEMINI,
            label="Gemini",
            runtime="cloud",
            configured=bool(os.getenv("GOOGLE_API_KEY", "").strip()),
            chat_models=_unique(chat_models[ModelProvider.GEMINI]),
            embedding_models=_unique(embedding_models[ModelProvider.GEMINI]),
        ),
        ProviderCatalog(
            provider=ModelProvider.OLLAMA,
            label="Ollama",
            runtime="local",
            configured=_value("OLLAMA_ENABLED", "false").lower()
            in {"1", "true", "yes", "on"},
            chat_models=_unique(
                chat_models[ModelProvider.OLLAMA], "qwen3:4b", "qwen3:8b", "qwen3:14b"
            ),
            embedding_models=_unique(embedding_models[ModelProvider.OLLAMA]),
        ),
    ]
    return ModelCatalog(
        active_chat=ModelChoice(
            provider=chat_provider,
            model=chat_models[chat_provider],
        ),
        active_embedding=ModelChoice(
            provider=embedding_provider,
            model=embedding_models[embedding_provider],
        ),
        providers=providers,
    )
