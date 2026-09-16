"""Storage adapters for uploaded source files."""

from backend.app.storage.local import LocalDocumentStorage, StoredFile

__all__ = ["LocalDocumentStorage", "StoredFile"]
