"""Local-volume storage adapter used by the synchronous MVP ingestion flow."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile


class UploadTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    key: str
    path: Path
    checksum: str
    size_bytes: int


class LocalDocumentStorage:
    def __init__(self, root: str | Path, max_upload_bytes: int) -> None:
        self.root = Path(root).resolve()
        self.max_upload_bytes = max_upload_bytes
        if max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be positive")

    def _path_for(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    async def save_pdf(self, document_id: UUID, upload: UploadFile) -> StoredFile:
        key = f"{document_id}.pdf"
        target = self._path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".uploading")
        digest = sha256()
        size = 0

        try:
            with temporary.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise UploadTooLargeError(
                            f"PDF exceeds the {self.max_upload_bytes} byte upload limit"
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise ValueError("Uploaded PDF is empty")
            with temporary.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise ValueError("Uploaded content is not a valid PDF file")
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        return StoredFile(
            key=key,
            path=target,
            checksum=digest.hexdigest(),
            size_bytes=size,
        )

    def resolve(self, key: str) -> Path:
        return self._path_for(key)

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)
