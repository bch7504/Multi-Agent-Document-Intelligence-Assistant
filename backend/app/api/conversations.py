"""Conversation history endpoints for the single-user MVP."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.schemas.conversations import (
    ConversationList,
    ConversationSummary,
    ConversationUpdate,
    MessageList,
    MessageRead,
)
from backend.app.services.conversations import (
    ConversationNotFoundError,
    ConversationService,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_conversation_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> ConversationService:
    return ConversationService(session)


@router.get("", response_model=ConversationList)
def list_conversations(
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationList:
    items, total = service.list(limit, offset)
    return ConversationList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{conversation_id}/messages", response_model=MessageList)
def get_conversation_messages(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> MessageList:
    try:
        records = service.messages(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    items = [MessageRead.model_validate(record) for record in records]
    return MessageList(items=items, total=len(items))


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationSummary:
    try:
        record = service.rename(conversation_id, payload.title)
        count = len(service.messages(conversation_id))
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return ConversationSummary(
        id=record.id,
        title=record.title,
        message_count=count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> Response:
    try:
        service.delete(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
