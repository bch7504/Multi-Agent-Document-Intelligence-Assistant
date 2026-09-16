"""Document upload, status, listing, and deletion endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.schemas.documents import DocumentList, DocumentRead
from backend.app.services.documents import (
    DocumentNotFoundError,
    DocumentService,
    UnsupportedDocumentError,
    build_document_service,
)
from backend.app.storage.local import UploadTooLargeError


router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentService:
    return build_document_service(session)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF document")],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentRead:
    try:
        record = await service.create_from_upload(file)
    except UnsupportedDocumentError as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    except UploadTooLargeError as error:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return DocumentRead.model_validate(record)


@router.get("", response_model=DocumentList)
def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    items, total = service.list(limit=limit, offset=offset)
    return DocumentList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: UUID,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentRead:
    try:
        return DocumentRead.model_validate(service.get(document_id))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Response:
    try:
        service.delete(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
