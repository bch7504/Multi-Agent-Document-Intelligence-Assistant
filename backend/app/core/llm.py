"""Factories for the supported chat model providers."""

import os
from typing import Any

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


load_dotenv()

DEFAULT_OPENROUTER_MODEL = "openai/gpt-5.6-luna"
DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_OLLAMA_CHAT_MODEL = "qwen3:8b"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
SUPPORTED_LLM_PROVIDERS = {
    "gemini",
    "ollama",
    "openai",
    "openrouter",
}


def _required_env(name: str, provider: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required when using {provider}")
    return value


def create_llm(
    llm_choice: str | None = None,
    openrouter_model: str | None = None,
    streaming: bool = True,
    model_name: str | None = None,
) -> Any:
    """Build one provider without requiring credentials for the others."""
    selected_provider = llm_choice or os.getenv("LLM_PROVIDER")
    if not selected_provider or not selected_provider.strip():
        raise ValueError(
            "LLM_PROVIDER must be selected: gemini, openrouter, openai, or ollama"
        )
    provider = selected_provider.strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            temperature=0,
            streaming=streaming,
            google_api_key=_required_env("GOOGLE_API_KEY", "Gemini"),
        )

    if provider == "ollama":
        kwargs: dict[str, Any] = {
            "model": model_name or os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_CHAT_MODEL),
            "temperature": 0,
            "streaming": streaming,
        }
        if base_url := os.getenv("OLLAMA_BASE_URL"):
            kwargs["base_url"] = base_url
        if num_ctx := os.getenv("OLLAMA_NUM_CTX"):
            kwargs["num_ctx"] = int(num_ctx)
        return ChatOllama(**kwargs)

    if provider == "openai":
        return ChatOpenAI(
            model=model_name or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            api_key=_required_env("OPENAI_API_KEY", "OpenAI"),
            temperature=0,
            streaming=streaming,
            stream_usage=streaming,
        )

    headers: dict[str, str] = {}
    if site_url := os.getenv("OPENROUTER_SITE_URL"):
        headers["HTTP-Referer"] = site_url
    if app_name := os.getenv("OPENROUTER_APP_NAME"):
        headers["X-OpenRouter-Title"] = app_name

    return ChatOpenAI(
        model=(
            openrouter_model
            or model_name
            or os.getenv("OPENROUTER_MODEL")
            or DEFAULT_OPENROUTER_MODEL
        ),
        api_key=_required_env("OPENROUTER_API_KEY", "OpenRouter"),
        base_url=OPENROUTER_BASE_URL,
        default_headers=headers or None,
        temperature=0,
        streaming=streaming,
        stream_usage=streaming,
    )
