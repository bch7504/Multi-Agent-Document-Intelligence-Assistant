"""Model catalog without exposing API keys to the browser."""

import os

from fastapi import APIRouter

from backend.app.core.llm import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    create_llm,
)
from backend.app.services.indexing import (
    DEFAULT_GEMINI_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    DEFAULT_OPENROUTER_EMBEDDING_MODEL,
    _get_embeddings,
)
from backend.app.schemas.models import (
    ModelCatalog,
    ModelChoice,
    ModelCheckResult,
    ModelProvider,
    ModelValidationRequest,
    ModelValidationResponse,
    ProviderCatalog,
)


router = APIRouter(prefix="/models", tags=["models"])


def _failure_message(error: Exception) -> str:
    if isinstance(error, ValueError):
        return str(error)
    return f"{type(error).__name__}: provider rejected the model or could not be reached"


def _validate_chat(choice: ModelChoice) -> ModelCheckResult:
    try:
        model = create_llm(
            llm_choice=choice.provider.value,
            model_name=choice.model,
            streaming=False,
        )
        model.invoke("Reply with OK only. This is a model availability check.")
    except Exception as error:  # Provider SDKs expose different exception types.
        return ModelCheckResult(usable=False, message=_failure_message(error))
    return ModelCheckResult(usable=True, message="Chat model responded successfully")


def _validate_embedding(choice: ModelChoice) -> ModelCheckResult:
    try:
        vector = _get_embeddings(choice.provider.value, choice.model).embed_query(
            "model availability check"
        )
        if not vector:
            raise ValueError("Embedding provider returned an empty vector")
    except Exception as error:  # Provider SDKs expose different exception types.
        return ModelCheckResult(usable=False, message=_failure_message(error))
    return ModelCheckResult(
        usable=True,
        message=f"Embedding model responded with {len(vector)} dimensions",
    )


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


@router.post("/validate", response_model=ModelValidationResponse)
def validate_model_selection(request: ModelValidationRequest) -> ModelValidationResponse:
    """Verify selected model IDs without returning credentials to the browser."""

    chat = _validate_chat(request.chat)
    embedding = _validate_embedding(request.embedding)
    return ModelValidationResponse(
        usable=chat.usable and embedding.usable,
        chat=chat,
        embedding=embedding,
    )
