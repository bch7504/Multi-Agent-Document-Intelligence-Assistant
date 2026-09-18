"""Environment-backed application settings without external service access."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    )


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    api_v1_prefix: str
    cors_origins: tuple[str, ...]
    database_url: str
    document_storage_path: str
    max_upload_bytes: int
    milvus_uri: str
    document_collection_name: str
    memory_max_messages: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv(
            "APP_NAME",
            "Multi-Agent Document Intelligence Assistant",
        ),
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        environment=os.getenv("APP_ENV", "development"),
        api_v1_prefix=os.getenv("API_V1_PREFIX", "/api/v1"),
        cors_origins=_csv_env("CORS_ORIGINS", "http://localhost:5173"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://document_assistant:document_assistant_dev@localhost:5432/document_assistant",
        ),
        document_storage_path=os.getenv("DOCUMENT_STORAGE_PATH", "data/uploads"),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(75 * 1024 * 1024))),
        milvus_uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
        document_collection_name=os.getenv(
            "DOCUMENT_COLLECTION_NAME",
            "document_chunks",
        ),
        memory_max_messages=int(os.getenv("MEMORY_MAX_MESSAGES", "12")),
    )
